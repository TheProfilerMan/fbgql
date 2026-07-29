"""Apify actor entrypoint — a thin adapter over fbgql.Scraper.

Reads the actor input, builds a ScrapeJob, and streams post results to the default
Dataset. Free to use — no developer fee; users only pay Apify platform usage.
All scraping logic lives in the fbgql core package.
"""

from __future__ import annotations

from apify import Actor

from fbgql import Account, Profile, ScrapeJob, Scraper, SessionInvalid

# Heuristic: treat inputs that look like a permalink as a single-post job.
_POST_MARKERS = ("/posts/", "story_fbid", "/permalink/", "/videos/", "pfbid")


def _is_post_url(value: str) -> bool:
    return value.startswith("http") and any(m in value for m in _POST_MARKERS)


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}

        page_or_url = inp.get("pageOrUrl")
        if not page_or_url:
            raise ValueError("Input 'pageOrUrl' is required")

        # This actor is anonymous-only: it scrapes logged-out public content as actor 0
        # and takes no Facebook credentials. A public actor must never ask users to paste
        # a session cookie jar into its input. Authenticated scraping still exists in the
        # library/CLI (``Account(cookies=…)`` / ``--cookies``) for gated content.
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

        account = Account.anonymous_account(proxy=proxy_url)
        is_post = _is_post_url(page_or_url)
        job = ScrapeJob(
            page=None if is_post else page_or_url,
            post_url=page_or_url if is_post else None,
            max_posts=int(inp.get("maxPosts", 1)),
            profile=Profile(inp.get("profile", "default")),
            engine=inp.get("engine", "async"),
            workers=inp.get("workers"),
            reply_fb_cap=inp.get("replyFbCap", -1),
            accounts=[account],
            anonymous=True,
            min_interval_sec=float(inp.get("minIntervalSec", 1.0)),
            mega_threshold=inp.get("megaThreshold"),
        )

        Actor.log.info(
            f"Scraping {page_or_url} (engine={job.engine}, profile={inp.get('profile')}, "
            "access=anonymous)"
        )

        scraped = 0
        try:
            async for post in Scraper().astream(job):
                await Actor.push_data(post.to_dict())
                scraped += 1
        except SessionInvalid as exc:
            # No credentials are involved, so this means Facebook served a login wall —
            # typically a blocked/flagged IP or a target that isn't publicly visible.
            await Actor.fail(
                status_message=(
                    "Facebook served a login wall for this target — it may be private, "
                    f"or this IP is blocked (try a residential proxy). ({exc})"
                )
            )
            return
        except ValueError as exc:
            await Actor.fail(status_message=str(exc))
            return

        if scraped == 0 and not is_post:
            await Actor.fail(
                status_message=(
                    f"No posts found for {page_or_url!r}. Common causes: (1) residential "
                    "proxy country/IP blocked by Facebook — switch Apify proxy country to "
                    "match the audience (or try another country); (2) private / "
                    "login-gated profile or group; (3) pass the numeric id or a direct "
                    "post URL. See the Actor README troubleshooting section."
                )
            )
            return

        Actor.log.info(f"Done. Pushed {scraped} posts to the dataset.")
