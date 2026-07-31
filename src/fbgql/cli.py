"""Command-line interface: ``fbgql scrape | doctor | mint-session``."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import click

from .dates import parse_time_bound
from .models import Account, Profile, ScrapeJob


def _load_session(path: str) -> tuple[dict[str, str], str | None]:
    """Load cookies (+ optional captured fb_dtsg) from a session/cookies file.

    Accepts three shapes:
      - a flat cookie map ``{"c_user": "...", ...}``
      - a Selenium jar ``[{"name": ..., "value": ...}, ...]``
      - a wrapped session ``{"cookies": {...}, "fb_dtsg": "..."}`` (what mint writes)
    """
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    fb_dtsg: str | None = None
    if isinstance(data, dict) and isinstance(data.get("cookies"), dict):
        fb_dtsg = data.get("fb_dtsg")
        data = data["cookies"]
    if isinstance(data, list):  # Selenium-style [{name,value},...]
        data = {c["name"]: c["value"] for c in data}
    if not isinstance(data, dict):
        raise click.ClickException("cookies file must be a JSON object or a list of {name,value}")
    return data, fb_dtsg


def _cli_time_bound(value: str | None) -> int | None:
    try:
        return parse_time_bound(value)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


@click.group()
@click.version_option(package_name="fbgql")
def main() -> None:
    """fbgql — Facebook GraphQL post & comment scraper."""


@main.command()
@click.option("--page", help="Page handle, URL, or numeric id.")
@click.option("--post-url", help="Scrape comments for a single post URL instead of a page.")
@click.option("--posts", "max_posts", default=20, show_default=True,
              help="Max posts to scrape (ignored when --after/--before is set).")
@click.option("--profile", type=click.Choice([p.value for p in Profile]), default="default",
              show_default=True)
@click.option("--engine", type=click.Choice(["threads", "async"]), default="threads",
              show_default=True)
@click.option("--workers", type=int, default=None, help="Override worker count.")
@click.option("--reply-cap", type=int, default=None,
              help="Fetch replies only when a post's FB comment_count < this. 0 = tops only.")
@click.option("--max-comments", type=int, default=None,
              help="Stop after this many top-level comments per post (pagination cap).")
@click.option("--cookies", "cookies_path", default=None,
              help="Path to cookies JSON. Omit to scrape logged-out (the default).")
@click.option("--anonymous", is_flag=True,
              help="Force logged-out scraping even if --cookies is given. Public content "
                   "only; login/age/geo-gated posts and private groups are unreachable.")
@click.option("--fb-dtsg", default=None, help="Optional fb_dtsg (else derived from cookies).")
@click.option("--proxy", default=None, help="Sticky proxy URL for this account.")
@click.option("--min-interval", type=float, default=1.0, show_default=True)
@click.option("--reply-concurrency", type=int, default=2, show_default=True)
@click.option("--mega-threshold", type=int, default=None, help="Pin heaviest post to a mega account.")
@click.option("--after", "after_time", default=None,
              help="Only posts at/after this time (unix seconds or YYYY-MM-DD UTC). "
                   "With a date filter, --posts is ignored and the feed is walked to the window.")
@click.option("--before", "before_time", default=None,
              help="Only posts before this time (unix seconds or YYYY-MM-DD UTC).")
@click.option("--posts-only", is_flag=True,
              help="Discover posts only; skip comment/reply scraping.")
@click.option("--out", "out_path", default=None, help="Write result JSON here (else stdout summary).")
def scrape(page, post_url, max_posts, profile, engine, workers, reply_cap, max_comments,
           cookies_path, anonymous, fb_dtsg, proxy, min_interval, reply_concurrency,
           mega_threshold, after_time, before_time, posts_only, out_path):
    """Scrape a page (or a single post) and write results."""
    from .scraper import Scraper

    if not page and not post_url:
        raise click.ClickException("provide --page or --post-url")

    after_ts = _cli_time_bound(after_time)
    before_ts = _cli_time_bound(before_time)
    if (after_ts is not None or before_ts is not None) and after_ts is None:
        raise click.ClickException(
            "date filter needs --after (lower bound) so pagination knows when to stop; "
            "--posts is ignored while filtering by date"
        )

    # Anonymous by default; pass --cookies to scrape as a real session instead.
    anonymous = anonymous or not cookies_path
    if anonymous:
        accounts = [Account.anonymous_account(proxy=proxy)]
    else:
        cookies, file_fb_dtsg = _load_session(cookies_path)
        accounts = [Account(cookies=cookies, fb_dtsg=fb_dtsg or file_fb_dtsg,
                            proxy=proxy, role="primary")]

    job = ScrapeJob(
        page=page,
        post_url=post_url,
        max_posts=max_posts,
        profile=Profile(profile),
        engine=engine,
        workers=workers,
        reply_fb_cap=reply_cap if reply_cap is not None else -1,
        accounts=accounts,
        anonymous=anonymous,
        min_interval_sec=min_interval,
        reply_concurrency=reply_concurrency,
        mega_threshold=mega_threshold,
        after_time=after_ts,
        before_time=before_ts,
        posts_only=posts_only,
        max_comments=max_comments,
        on_progress=lambda msg: click.echo(msg, err=True),
    )

    mode = "anonymous" if anonymous else "authenticated"
    date_note = ""
    if after_ts is not None or before_ts is not None:
        date_note = " · date-filter (max posts ignored)"
    click.echo(f"Scraping {page or post_url} · engine={engine} · profile={profile} "
               f"· access={mode}"
               f"{' · posts-only' if posts_only else ''}{date_note}…", err=True)

    # Stream per-post progress to stderr so a long run visibly advances instead of
    # looking frozen (a full page can grind through thousands of comments silently).
    state = {"n": 0, "scraped": 0}

    def _on_post(pr) -> None:
        state["n"] += 1
        state["scraped"] += pr.total_scraped
        if posts_only:
            ts = pr.post.created_time
            when = (
                datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                if ts is not None else "?"
            )
            click.echo(
                f"  [{state['n']}] post {pr.post.post_id}: {when} · "
                f"{(pr.post.text or '')[:60]!r}",
                err=True,
            )
            return
        cov = f"{pr.coverage * 100:.0f}%" if pr.post.comment_count else "n/a"
        tag = f" · {pr.error}" if pr.error else ""
        click.echo(
            f"  [{state['n']}] post {pr.post.post_id}: "
            f"{pr.total_scraped} comments (of {pr.post.comment_count} · cov {cov}) "
            f"[{state['scraped']} total, {pr.elapsed_sec:.1f}s]{tag}",
            err=True,
        )

    result = Scraper().run(job, on_post=_on_post)

    if out_path:
        result.to_json(out_path)
        click.echo(f"Wrote {out_path}", err=True)

    # Explain a silent 0-comment outcome (stale comments doc_id, dead session, etc.).
    if not posts_only and result.posts and result.total_scraped == 0:
        err = next((p.error for p in result.posts if p.error), None)
        if err:
            click.echo(f"WARNING: 0 comments scraped — first post error: {err}", err=True)
        else:
            click.echo("WARNING: 0 comments scraped (posts had no comments, or all "
                       "comment pages were empty).", err=True)

    click.echo(json.dumps({
        "page": result.page,
        "posts": len(result.posts),
        "weighted_coverage": round(result.weighted_coverage, 4),
        "median_coverage": round(result.median_coverage, 4),
        "total_scraped": result.total_scraped,
        "total_fb_comments": result.total_fb_comments,
        "elapsed_sec": round(result.elapsed_sec, 1),
    }, indent=2))


@main.command()
@click.option("--cookies", "cookies_path", default=None,
              help="Path to cookies JSON. Omit to check logged-out (the default).")
@click.option("--anonymous", is_flag=True,
              help="Force the logged-out check even if --cookies is given.")
@click.option("--page", default=None, help="Page to validate timeline/comments doc_ids against.")
@click.option("--proxy", default=None)
def doctor(cookies_path, anonymous, page, proxy):
    """Validate the session and that doc_ids still resolve."""
    from .doctor import run_checks

    anonymous = anonymous or not cookies_path
    if anonymous:
        account = Account.anonymous_account(proxy=proxy)
    else:
        cookies, file_fb_dtsg = _load_session(cookies_path)
        account = Account(cookies=cookies, fb_dtsg=file_fb_dtsg, proxy=proxy)
    checks = run_checks(account, page)
    all_ok = True
    for c in checks:
        mark = "✓" if c.ok else "✗"
        all_ok = all_ok and c.ok
        click.echo(f"  {mark} {c.name}: {c.detail}")
    sys.exit(0 if all_ok else 1)


@main.command(name="mint-session")
@click.option("--out", "out_path", default="cookies.json", show_default=True)
@click.option("--headless", is_flag=True, default=False, help="Run browser headless (not recommended).")
@click.option("--timeout", type=int, default=300, show_default=True)
def mint_session(out_path, headless, timeout):
    """Interactive login → cookies JSON (needs the [mint] extra)."""
    from .mint import mint

    mint(out_path, headless=headless, timeout=timeout)


@main.command()
@click.option("--page", required=True, help="Page handle to browse while capturing queries.")
@click.option("--cookies", "cookies_path", default=None,
              help="Cookies JSON to inject (omit to log in interactively).")
@click.option("--out", "out_path", default="captured_queries.json", show_default=True)
@click.option("--headless", is_flag=True, default=False,
              help="Run browser headless (real browser recommended for capture).")
def capture(page, cookies_path, out_path, headless):
    """Record the CURRENT doc_ids + variables from a real browser (needs the [mint] extra).

    Use this when a run fails with a stale-query error (Facebook rotated a doc_id):
    it browses the page and writes the live doc_id + variable schema for timeline,
    comments, and replies so the shipped payloads can be updated.
    """
    from .capture import capture as run_capture

    cookies = None
    if cookies_path:
        cookies, _ = _load_session(cookies_path)
    run_capture(page, cookies, out_path, headless=headless)


if __name__ == "__main__":
    main()
