"""Optional engine: asyncio + httpx (engine="async").

Behaviorally identical to the threaded engine (same payloads, parsing, policy,
backoff) but built for streaming — the Apify actor drives ``astream`` to push posts
to its Dataset as they complete.

Note: ``run()`` uses ``asyncio.run`` and must not be called from inside an already
running event loop. In async contexts (the actor) use ``astream`` directly.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterator

from .. import config, parsing, payloads, policy
from ..errors import RequestRejected, SessionInvalid, TransportError
from ..models import Comment, Post, PostResult, Result, ScrapeJob, Session
from ..runner import ExecutionPlan
from ..transport import friendly_headers
from ..transport.async_http import AsyncTransport
from . import base


class AsyncEngine:
    def __init__(self) -> None:
        self.transport = AsyncTransport()

    # -- public API --------------------------------------------------------

    def run(self, plan: ExecutionPlan) -> Result:
        return asyncio.run(self._run(plan))

    async def _run(self, plan: ExecutionPlan) -> Result:
        t0 = time.perf_counter()
        results = [r async for r in self.astream(plan)]
        return base.assemble_result(plan.job, plan, results, time.perf_counter() - t0)

    def stream(self, plan: ExecutionPlan) -> Iterator[PostResult]:
        # Sync convenience: run to completion, then yield. For true streaming in an
        # async context, use astream().
        yield from self.run(plan).posts

    async def astream(self, plan: ExecutionPlan) -> AsyncIterator[PostResult]:
        job = plan.job
        reply_sem = asyncio.Semaphore(max(1, job.reply_concurrency))
        out: asyncio.Queue = asyncio.Queue()
        buckets = plan.assignment.buckets
        expected = sum(len(b) for b in buckets)

        async def worker_run(w: int, posts: list[Post], session: Session) -> None:
            # One result per post even on unexpected failure (no consumer deadlock).
            for post in posts:
                try:
                    result = await self._scrape_post(post, session, job, reply_sem, w)
                except Exception as exc:  # noqa: BLE001
                    result = base.build_post_result(
                        post, [], replies_skipped=True, elapsed_sec=0.0,
                        worker=w, error=f"{type(exc).__name__}: {exc}",
                    )
                await out.put(result)

        tasks = [
            asyncio.create_task(worker_run(w, b, plan.worker_sessions[w]))
            for w, b in enumerate(buckets)
            if b
        ]

        done = 0
        while done < expected:
            yield await out.get()
            done += 1
        await asyncio.gather(*tasks)

    # -- per-post ----------------------------------------------------------

    async def _scrape_post(self, post: Post, session: Session, job: ScrapeJob,
                           reply_sem: asyncio.Semaphore, worker: int) -> PostResult:
        t0 = time.perf_counter()
        _workers, cap = job.resolved_policy()
        do_replies = policy.want_replies(cap, post.comment_count)
        try:
            comments, tokens = await self._fetch_comments(post, session, job)
        except Exception as exc:  # noqa: BLE001 - isolate a bad post
            return base.build_post_result(
                post, [], replies_skipped=True, elapsed_sec=time.perf_counter() - t0,
                worker=worker, error=f"{type(exc).__name__}: {exc}",
            )

        if do_replies:
            for comment, (fb_id, expansion) in zip(comments, tokens):  # noqa: B905
                try:
                    replies = await self._fetch_replies(fb_id, expansion, session, job, reply_sem)
                except Exception:  # noqa: BLE001 - a bad reply must not lose the tops
                    replies = []
                comment.replies = replies
                comment.reply_count = len(replies)

        return base.build_post_result(
            post, comments, replies_skipped=not do_replies,
            elapsed_sec=time.perf_counter() - t0, worker=worker,
        )

    async def _fetch_comments(self, post: Post, session: Session, job: ScrapeJob):
        registry = config.DocIdRegistry()
        doc_id = registry.get("comments")
        headers = friendly_headers(config.FRIENDLY_COMMENTS, referer=post.permalink or config.HOME_URL)

        comments: list[Comment] = []
        tokens: list[tuple[str | None, str | None]] = []
        cursor: str | None = None
        page_index = 0
        empty_retries = 0

        while True:
            data = payloads.comments_payload(
                feedback_id=post.feedback_id, cursor=cursor, c_user=session.c_user,
                fb_dtsg=session.fb_dtsg, doc_id=doc_id,
            )
            try:
                body = await self.transport.post_form(headers, data, session.cookies, session.proxy)
                payload_json = parsing.fb_json(body)
                parsing.raise_if_rejected(payload_json, "comments")
                parsing.raise_if_doc_id_stale(payload_json, "comments", doc_id)
                page = parsing.parse_comments_page(payload_json)
            except (SessionInvalid, RequestRejected, TransportError):
                # Blocked mid-pagination — keep comments so far; re-raise only if the
                # first page failed (nothing to salvage) so the error is reported.
                if comments:
                    break
                raise

            if not page.comments:
                if policy.should_retry_empty_page(page.critical_codes, empty_retries, page_index):
                    empty_retries += 1
                    await asyncio.sleep(policy.empty_page_backoff_seconds(empty_retries))
                    continue
                break

            comments.extend(page.comments)
            tokens.extend(page.reply_tokens)
            page_index += 1
            empty_retries = 0

            cursor = page.page_info.end_cursor
            if not cursor:
                break
            await asyncio.sleep(job.min_interval_sec)

        return comments, tokens

    async def _fetch_replies(self, comment_fb_id, expansion, session: Session, job: ScrapeJob,
                             reply_sem: asyncio.Semaphore):
        if not comment_fb_id or not expansion:
            return []
        registry = config.DocIdRegistry()
        doc_id = registry.get("replies")
        headers = friendly_headers(config.FRIENDLY_REPLIES)
        data = payloads.replies_payload(
            comment_feedback_id=comment_fb_id, expansion_token=expansion,
            c_user=session.c_user, fb_dtsg=session.fb_dtsg, doc_id=doc_id,
        )
        async with reply_sem:
            body = await self.transport.post_form(headers, data, session.cookies, session.proxy)
        return parsing.parse_replies(parsing.fb_json(body))
