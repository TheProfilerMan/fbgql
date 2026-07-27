"""Apify actor entrypoint — a thin adapter over fbgql.Scraper.

Reads the actor input, builds a ScrapeJob, streams post results to the default
Dataset, and (optionally) charges per scraped post for pay-per-event monetization.
All scraping logic lives in the fbgql core package.
"""

from __future__ import annotations

from apify import Actor

from fbgql import Account, Profile, ScrapeJob, Scraper, SessionInvalid

# Heuristic: treat inputs that look like a permalink as a single-post job.
_POST_MARKERS = ("/posts/", "story_fbid", "/permalink/", "/videos/", "pfbid")


def _is_post_url(value: str) -> bool:
    return value.startswith("http") and any(m in value for m in _POST_MARKERS)


async def _maybe_charge(event: str) -> None:
    """Charge a pay-per-event unit; ignore if monetization isn't configured."""
    try:
        await Actor.charge(event_name=event)
    except Exception as exc:  # noqa: BLE001 - charging is best-effort at runtime
        Actor.log.debug(f"charge({event}) skipped: {exc}")


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}

        page_or_url = inp.get("pageOrUrl")
        if not page_or_url:
            raise ValueError("Input 'pageOrUrl' is required")

        cookies = inp.get("cookies") or {}
        if not cookies:
            raise ValueError("Input 'cookies' is required (mint once with `fbgql mint-session`)")

        # Resolve a proxy URL. On the platform a configured-but-failing proxy is a hard
        # error (falling back to the actor's datacenter IP would defeat the point). For
        # local dev (`apify run` without login) degrade to a direct connection.
        proxy_url = None
        proxy_input = inp.get("proxyConfiguration")
        if proxy_input:
            try:
                proxy_cfg = await Actor.create_proxy_configuration(actor_proxy_input=proxy_input)
                proxy_url = await proxy_cfg.new_url() if proxy_cfg else None
            except Exception as exc:  # noqa: BLE001
                if Actor.is_at_home():
                    raise
                Actor.log.warning(
                    f"Proxy unavailable locally ({exc}); continuing over the direct connection."
                )

        account = Account(cookies=cookies, proxy=proxy_url, role="primary")
        is_post = _is_post_url(page_or_url)
        job = ScrapeJob(
            page=None if is_post else page_or_url,
            post_url=page_or_url if is_post else None,
            max_posts=int(inp.get("maxPosts", 20)),
            profile=Profile(inp.get("profile", "default")),
            engine=inp.get("engine", "async"),
            workers=inp.get("workers"),
            reply_fb_cap=inp.get("replyFbCap", -1),
            accounts=[account],
            min_interval_sec=float(inp.get("minIntervalSec", 1.0)),
            mega_threshold=inp.get("megaThreshold"),
        )

        Actor.log.info(f"Scraping {page_or_url} (engine={job.engine}, profile={inp.get('profile')})")

        scraped = 0
        try:
            async for post in Scraper().astream(job):
                await Actor.push_data(post.to_dict())
                scraped += 1
                await _maybe_charge("post-scraped")
        except SessionInvalid as exc:
            await Actor.fail(
                status_message=f"Session invalid — re-mint cookies and retry. ({exc})"
            )
            return

        Actor.log.info(f"Done. Pushed {scraped} posts to the dataset.")
