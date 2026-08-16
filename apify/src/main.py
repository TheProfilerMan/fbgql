"""Apify actor entrypoint — thin adapter over fbgql.Scraper.

This private fork adds cost-controlled page monitoring:
- maxPosts is always a hard ceiling and is capped at 50;
- stopPostIds stops on the first previously-seen Facebook post;
- stopAfterTime is an exact Unix timestamp fallback;
- monitoring results are written to the dataset and OUTPUT key-value record.
"""

from __future__ import annotations

from apify import Actor

from fbgql import Account, Profile, ScrapeJob, Scraper, SessionInvalid
from fbgql.dates import parse_time_bound

from .monitoring_patch import install_monitoring_patch

_POST_MARKERS = ("/posts/", "story_fbid", "/permalink/", "/videos/", "pfbid")


def _is_post_url(value: str) -> bool:
    return value.startswith("http") and any(marker in value for marker in _POST_MARKERS)


def _clean_stop_ids(value) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Input 'stopPostIds' must be an array of Facebook post IDs")
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        post_id = str(item or "").strip()
        if post_id and post_id not in seen:
            seen.add(post_id)
            out.append(post_id)
    return out


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}

        page_or_url = inp.get("pageOrUrl")
        if not page_or_url:
            raise ValueError("Input 'pageOrUrl' is required")

        try:
            requested_max = int(inp.get("maxPosts", 1))
        except (TypeError, ValueError):
            raise ValueError("Input 'maxPosts' must be an integer") from None

        if requested_max < 1:
            raise ValueError("Input 'maxPosts' must be at least 1")

        max_posts = min(requested_max, 50)
        if requested_max > 50:
            Actor.log.warning(
                f"maxPosts={requested_max} exceeds this fork's financial safety ceiling; using 50."
            )

        try:
            stop_post_ids = _clean_stop_ids(inp.get("stopPostIds"))
        except ValueError as exc:
            await Actor.fail(status_message=str(exc))
            return

        stop_after_time_raw = inp.get("stopAfterTime")
        stop_after_time: int | None = None
        if stop_after_time_raw is not None:
            try:
                stop_after_time = int(stop_after_time_raw)
            except (TypeError, ValueError):
                await Actor.fail(
                    status_message="Input 'stopAfterTime' must be a Unix timestamp in seconds."
                )
                return
            if stop_after_time <= 0:
                await Actor.fail(
                    status_message="Input 'stopAfterTime' must be a positive Unix timestamp."
                )
                return

        monitoring_mode = bool(stop_post_ids or stop_after_time is not None)

        if monitoring_mode and any(
            inp.get(name) is not None
            for name in ("afterDate", "beforeDate", "afterTime", "beforeTime")
        ):
            await Actor.fail(
                status_message=(
                    "Monitoring mode uses stopPostIds/stopAfterTime and cannot be combined "
                    "with afterDate, beforeDate, afterTime, or beforeTime. This keeps maxPosts "
                    "as a real hard cost ceiling."
                )
            )
            return

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

        date_tz = inp.get("dateTimezone") or "UTC"
        after_time = None
        before_time = None

        if not monitoring_mode:
            try:
                after_time = parse_time_bound(
                    inp.get("afterDate", inp.get("afterTime")), tz=date_tz
                )
                before_time = parse_time_bound(
                    inp.get("beforeDate", inp.get("beforeTime")), tz=date_tz
                )
            except ValueError as exc:
                await Actor.fail(status_message=str(exc))
                return

            if (after_time is not None or before_time is not None) and after_time is None:
                await Actor.fail(
                    status_message=(
                        "Date filter needs afterDate (lower bound) so pagination knows when to stop."
                    )
                )
                return

        install_monitoring_patch()

        job = ScrapeJob(
            page=None if is_post else page_or_url,
            post_url=page_or_url if is_post else None,
            max_posts=max_posts,
            profile=Profile(inp.get("profile", "default")),
            engine=inp.get("engine", "async"),
            workers=inp.get("workers"),
            reply_fb_cap=inp.get("replyFbCap", -1),
            accounts=[account],
            anonymous=True,
            min_interval_sec=float(inp.get("minIntervalSec", 1.0)),
            mega_threshold=inp.get("megaThreshold"),
            after_time=after_time,
            before_time=before_time,
            posts_only=bool(inp.get("postsOnly", False)),
            max_comments=(
                int(inp["maxComments"]) if inp.get("maxComments") is not None else None
            ),
            on_progress=lambda msg: Actor.log.info(msg),
        )

        # ScrapeJob is a regular dataclass, so monitoring state can be attached without
        # changing the upstream public model. The monkey patch reads and updates these.
        job.stop_post_ids = stop_post_ids
        job.stop_after_time = stop_after_time
        job.monitoring_mode = monitoring_mode
        job.monitor_boundary_found = False
        job.monitor_boundary_method = None
        job.monitor_overlap_post_id = None
        job.monitor_hit_cap = False

        if monitoring_mode:
            Actor.log.info(
                f"Monitoring {page_or_url}: hard max={max_posts}, "
                f"known stop IDs={len(stop_post_ids)}, stopAfterTime={stop_after_time}"
            )
        else:
            tz_note = f", dateTimezone={date_tz}" if after_time or before_time else ""
            Actor.log.info(
                f"Scraping {page_or_url} (engine={job.engine}, profile={inp.get('profile')}, "
                f"access=anonymous{tz_note})"
            )

        scraped = 0
        new_posts = 0
        overlap_posts = 0

        try:
            async for result in Scraper().astream(job):
                payload = result.to_dict()
                post_id = str(result.post.post_id or "")
                is_overlap = bool(
                    monitoring_mode
                    and job.monitor_boundary_found
                    and (
                        post_id == str(job.monitor_overlap_post_id or "")
                        or (
                            job.monitor_boundary_method == "time"
                            and result.post.created_time is not None
                            and stop_after_time is not None
                            and result.post.created_time <= stop_after_time
                        )
                    )
                )

                if is_overlap:
                    overlap_posts += 1
                else:
                    new_posts += 1

                payload["monitoring"] = {
                    "enabled": monitoring_mode,
                    "isOverlap": is_overlap,
                    "boundaryFound": bool(job.monitor_boundary_found),
                    "boundaryMethod": job.monitor_boundary_method,
                    "overlapPostId": job.monitor_overlap_post_id,
                    "hitMaxPosts": bool(job.monitor_hit_cap),
                    "suspectedMissing": bool(
                        monitoring_mode
                        and job.monitor_hit_cap
                        and not job.monitor_boundary_found
                    ),
                }

                await Actor.push_data(payload)
                scraped += 1

        except SessionInvalid as exc:
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
                    f"No posts found for {page_or_url!r}. Common causes: residential proxy "
                    "country/IP blocked by Facebook, a private/login-gated target, or an "
                    "unresolvable page handle."
                )
            )
            return

        summary = {
            "pageOrUrl": page_or_url,
            "monitoringEnabled": monitoring_mode,
            "maxPosts": max_posts,
            "returnedPosts": scraped,
            "newPosts": new_posts,
            "overlapPosts": overlap_posts,
            "boundaryFound": bool(job.monitor_boundary_found),
            "boundaryMethod": job.monitor_boundary_method,
            "overlapPostId": job.monitor_overlap_post_id,
            "hitMaxPosts": bool(job.monitor_hit_cap),
            "suspectedMissing": bool(
                monitoring_mode
                and job.monitor_hit_cap
                and not job.monitor_boundary_found
            ),
            "stopAfterTime": stop_after_time,
            "stopPostIdsSupplied": len(stop_post_ids),
        }
        await Actor.set_value("OUTPUT", summary)

        Actor.log.info(
            "Done. "
            f"returned={scraped}, new={new_posts}, overlap={overlap_posts}, "
            f"boundary_found={summary['boundaryFound']}, "
            f"hit_cap={summary['hitMaxPosts']}, "
            f"suspected_missing={summary['suspectedMissing']}"
        )
