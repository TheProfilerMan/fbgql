"""Engine protocol + shared, engine-agnostic result assembly."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from .. import policy
from ..models import Comment, Post, PostResult, Result, ScrapeJob
from ..runner import ExecutionPlan


class Engine(Protocol):
    def run(self, plan: ExecutionPlan) -> Result: ...
    def stream(self, plan: ExecutionPlan) -> Iterator[PostResult]: ...


def build_post_result(
    post: Post,
    comments: list[Comment],
    *,
    nested_replies_on: bool,
    elapsed_sec: float,
    worker: int | None,
    error: str | None = None,
) -> PostResult:
    tops = len(comments)
    replies = sum(len(c.replies) for c in comments)
    total = tops + replies
    return PostResult(
        post=post,
        comments=comments,
        tops=tops,
        replies=replies,
        total_scraped=total,
        coverage=policy.coverage(total, post.comment_count),
        nested_replies_on=nested_replies_on,
        elapsed_sec=elapsed_sec,
        worker=worker,
        error=error,
    )


def assemble_result(job: ScrapeJob, plan: ExecutionPlan, post_results: list[PostResult],
                    elapsed_sec: float) -> Result:
    from ..runner import summarize

    stats = summarize(job, post_results)
    # Preserve discovery order (bin-packing reorders internally).
    order = {p.post_id: i for i, p in enumerate(plan.posts)}
    post_results = sorted(post_results, key=lambda r: order.get(r.post.post_id, 1_000_000))
    return Result(
        page=job.page,
        posts=post_results,
        weighted_coverage=stats["weighted_coverage"],
        median_coverage=stats["median_coverage"],
        total_scraped=stats["total_scraped"],
        total_fb_comments=stats["total_fb_comments"],
        elapsed_sec=elapsed_sec,
    )
