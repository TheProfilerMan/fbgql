"""Pure policy decisions: retry/backoff schedules, reply gating, and bin-packing.

Both engines call into this so behavior is identical regardless of concurrency model.
No I/O here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import config
from .models import Post

# Max times to re-request the SAME cursor when a page comes back empty with the
# retryable critical code. Kept modest — empty pages are usually throttle, not data.
MAX_EMPTY_RETRIES = 12

# Max transport-level retries (network/proxy/5xx) before giving up on a request.
MAX_TRANSPORT_RETRIES = 12


def empty_page_backoff_seconds(attempt: int) -> int:
    """Backoff before re-requesting the same cursor after an empty page."""
    return min(3 * attempt, 30)


def transport_backoff_seconds(attempt: int) -> int:
    """Backoff between transport-level retries."""
    return min(attempt * 2, 20)


def should_retry_empty_page(critical_codes: list[int], attempt: int, page_index: int) -> bool:
    """Decide whether an empty comments page is worth re-requesting.

    - Never retry an empty *first* page (page_index == 0): that post simply has no
      reachable comments on this surface.
    - Otherwise retry only if the retryable critical code is present and we are under
      the attempt ceiling.
    """
    if page_index == 0:
        return False
    if attempt >= MAX_EMPTY_RETRIES:
        return False
    return config.EMPTY_PAGE_RETRY_CODE in critical_codes


def want_replies(reply_fb_cap: int | None, fb_comment_count: int) -> bool:
    """Reply-cap semantics: None -> always, 0 -> never, N -> only if count < N."""
    if reply_fb_cap is None:
        return True
    if reply_fb_cap == 0:
        return False
    return fb_comment_count < reply_fb_cap


def coverage(scraped: int, fb_count: int) -> float:
    return (scraped / fb_count) if fb_count else 0.0


# ---------------------------------------------------------------------------
# Bin-packing / worker assignment
# ---------------------------------------------------------------------------


@dataclass
class Assignment:
    buckets: list[list[Post]] = field(default_factory=list)
    mega_worker: int | None = None       # worker index pinned to the mega post, if any
    mega_post_id: str | None = None


def assign_posts(posts: list[Post], n_workers: int, mega_threshold: int | None = None) -> Assignment:
    """Greedy least-loaded bin-pack by comment_count.

    If ``mega_threshold`` is set and the heaviest post meets it, that post is pinned
    alone to worker 0 (so a dedicated/"mega" account can own it) and the rest are
    packed across the remaining workers.
    """
    n_workers = max(1, n_workers)
    ordered = sorted(posts, key=lambda p: p.comment_count, reverse=True)
    buckets: list[list[Post]] = [[] for _ in range(n_workers)]
    loads = [0] * n_workers

    a = Assignment(buckets=buckets)
    start = 0
    if mega_threshold is not None and ordered and ordered[0].comment_count >= mega_threshold and n_workers > 1:
        mega = ordered[0]
        buckets[0].append(mega)
        loads[0] += mega.comment_count
        a.mega_worker = 0
        a.mega_post_id = mega.post_id
        ordered = ordered[1:]
        start = 1  # pack the rest into workers 1..n-1

    for post in ordered:
        candidates = range(start, n_workers) if start < n_workers else range(n_workers)
        w = min(candidates, key=lambda i: loads[i])
        buckets[w].append(post)
        loads[w] += post.comment_count

    return a
