"""Runtime patch for cost-controlled feed pagination in the private Actor fork.

The upstream library intentionally ignores max_posts when a date window is used.
This private Actor needs different economics: maxPosts is a hard ceiling, and daily
monitoring should stop as soon as a previously-seen post or exact timestamp boundary
is reached.

Keeping this in the Actor layer makes the fork easy to rebase onto upstream fbgql.
"""

from __future__ import annotations

import time

import fbgql.runner as runner


_INSTALLED = False
_ORIGINAL_PAGINATE_FEED = runner._paginate_feed


def _append_candidate(
    posts,
    post,
    job,
    *,
    monitoring: bool,
    stop_ids: set[str],
    stop_after_time: int | None,
    max_posts: int,
) -> bool:
    """Append one post and return True when pagination must stop."""
    if post.post_id in {existing.post_id for existing in posts}:
        return False

    posts.append(post)

    if monitoring and post.post_id in stop_ids:
        job.monitor_boundary_found = True
        job.monitor_boundary_method = "post_id"
        job.monitor_overlap_post_id = post.post_id
        runner.emit(job, f"Known post {post.post_id} reached — stopping at one overlap.")
        return True

    if (
        monitoring
        and stop_after_time is not None
        and post.created_time is not None
        and post.created_time <= stop_after_time
    ):
        job.monitor_boundary_found = True
        job.monitor_boundary_method = "time"
        job.monitor_overlap_post_id = post.post_id
        runner.emit(
            job,
            f"Exact timestamp boundary reached at post {post.post_id} "
            f"({post.created_time} <= {stop_after_time}) — stopping."
        )
        return True

    if len(posts) >= max_posts:
        job.monitor_hit_cap = True
        runner.emit(job, f"Hard maxPosts ceiling reached ({max_posts}) — stopping.")
        return True

    return False


def _cost_controlled_paginate_feed(fetch_page, ids: list[str], job):
    """Feed pagination with a real maxPosts ceiling and optional monitoring boundary."""
    monitoring = bool(getattr(job, "monitoring_mode", False))
    stop_ids = {
        str(value).strip()
        for value in getattr(job, "stop_post_ids", [])
        if str(value).strip()
    }
    stop_after_time = getattr(job, "stop_after_time", None)
    max_posts = max(1, min(int(job.max_posts), 50))

    job.monitor_boundary_found = False
    job.monitor_boundary_method = None
    job.monitor_overlap_post_id = None
    job.monitor_hit_cap = False

    posts = []
    chosen = None
    cursor = None
    feed_page = 0
    stopped = False

    def process_page(page_posts) -> bool:
        nonlocal stopped

        if monitoring:
            candidates = page_posts
        else:
            candidates = [
                post
                for post in page_posts
                if runner._post_in_date_range(post, job)
            ]

        for post in candidates:
            if len(posts) >= max_posts:
                job.monitor_hit_cap = True
                stopped = True
                return True

            if _append_candidate(
                posts,
                post,
                job,
                monitoring=monitoring,
                stop_ids=stop_ids,
                stop_after_time=stop_after_time,
                max_posts=max_posts,
            ):
                stopped = True
                return True

        if not monitoring and runner._past_date_window(page_posts, job):
            runner.emit(job, "Reached end of date window — stopping feed pagination.")
            stopped = True
            return True

        return False

    for uid in ids:
        runner.emit(job, f"Probing feed id {uid}…")
        page_posts, cursor = fetch_page(uid, None)
        feed_page += 1

        if page_posts:
            chosen = uid
            process_page(page_posts)
            runner.emit(
                job,
                f"Feed page {feed_page}: got {len(page_posts)} posts, "
                f"kept {len(posts)} total, cursor={'yes' if cursor else 'end'}"
            )
            if stopped:
                cursor = None
            break

        runner.emit(job, f"Feed id {uid}: no posts")

    if chosen is None:
        return [], (ids[0] if ids else None)

    empty_pages = 0

    while cursor and not stopped and len(posts) < max_posts:
        time.sleep(1)

        try:
            runner.emit(job, f"Fetching feed page {feed_page + 1}…")
            page_posts, cursor = fetch_page(chosen, cursor)
            feed_page += 1
        except (
            runner.SessionInvalid,
            runner.RequestRejected,
            runner.TransportError,
        ) as exc:
            runner.emit(
                job,
                f"Feed pagination stopped ({type(exc).__name__}); "
                f"keeping {len(posts)} posts"
            )
            break

        if not page_posts:
            empty_pages += 1
            runner.emit(job, f"Feed page {feed_page}: empty ({empty_pages}/3)")
            if empty_pages >= 3 or not cursor:
                break
            time.sleep(2)
            continue

        empty_pages = 0
        process_page(page_posts)

        runner.emit(
            job,
            f"Feed page {feed_page}: got {len(page_posts)} posts, "
            f"kept {len(posts)} total"
        )

    if len(posts) >= max_posts and not job.monitor_boundary_found:
        job.monitor_hit_cap = True

    return posts[:max_posts], chosen


def install_monitoring_patch() -> None:
    """Install the private Actor pagination policy once per process."""
    global _INSTALLED

    if _INSTALLED:
        return

    runner._paginate_feed = _cost_controlled_paginate_feed
    _INSTALLED = True
