"""Default engine: ThreadPoolExecutor + requests. Reproduces the measured policy.

Each worker owns a bucket of posts (assigned by bin-packing) and processes them
sequentially. A shared semaphore caps concurrent reply requests across all workers —
the main anti-throttle lever. Completed posts are streamed out via a queue.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

from .. import config, parsing, payloads, policy
from ..errors import RequestRejected, SessionInvalid, TransportError
from ..models import Comment, Post, PostResult, Result, ScrapeJob, Session
from ..runner import ExecutionPlan
from ..transport import friendly_headers
from ..transport.sync_http import SyncTransport
from . import base

_SENTINEL = object()


class ThreadedEngine:
    def __init__(self) -> None:
        self.transport = SyncTransport()

    # -- public API --------------------------------------------------------

    def run(self, plan: ExecutionPlan) -> Result:
        t0 = time.perf_counter()
        results = list(self.stream(plan))
        return base.assemble_result(plan.job, plan, results, time.perf_counter() - t0)

    def stream(self, plan: ExecutionPlan) -> Iterator[PostResult]:
        job = plan.job
        reply_sem = threading.Semaphore(max(1, job.reply_concurrency))
        out: queue.Queue = queue.Queue()

        buckets = plan.assignment.buckets
        active = sum(1 for b in buckets if b)

        def worker_run(worker_idx: int, posts: list[Post], session: Session) -> None:
            # Guarantee exactly one result per post, even on unexpected failure, so
            # the consumer's count is always reached (no deadlock on a raised worker).
            for post in posts:
                try:
                    result = self._scrape_post(post, session, job, reply_sem, worker_idx)
                except Exception as exc:  # noqa: BLE001
                    result = base.build_post_result(
                        post, [], replies_skipped=True, elapsed_sec=0.0,
                        worker=worker_idx, error=f"{type(exc).__name__}: {exc}",
                    )
                out.put(result)

        with ThreadPoolExecutor(max_workers=max(1, active)) as pool:
            for w, bucket in enumerate(buckets):
                if not bucket:
                    continue
                pool.submit(worker_run, w, bucket, plan.worker_sessions[w])

            done = 0
            expected = sum(len(b) for b in buckets)
            while done < expected:
                item = out.get()
                if item is _SENTINEL:  # pragma: no cover
                    break
                done += 1
                yield item

    # -- per-post ----------------------------------------------------------

    def _scrape_post(self, post: Post, session: Session, job: ScrapeJob,
                     reply_sem: threading.Semaphore, worker: int) -> PostResult:
        t0 = time.perf_counter()
        _workers, cap = job.resolved_policy()
        do_replies = policy.want_replies(cap, post.comment_count)
        try:
            comments, tokens = self._fetch_comments(post, session, job)
        except Exception as exc:  # noqa: BLE001 - isolate a bad post, keep the run going
            return base.build_post_result(
                post, [], replies_skipped=True, elapsed_sec=time.perf_counter() - t0,
                worker=worker, error=f"{type(exc).__name__}: {exc}",
            )

        if do_replies:
            for comment, (fb_id, expansion) in zip(comments, tokens):  # noqa: B905
                try:
                    replies = self._fetch_replies(fb_id, expansion, session, job, reply_sem)
                except Exception:  # noqa: BLE001 - a bad reply must not lose the tops
                    replies = []
                comment.replies = replies
                comment.reply_count = len(replies)

        return base.build_post_result(
            post, comments, replies_skipped=not do_replies,
            elapsed_sec=time.perf_counter() - t0, worker=worker,
        )

    def _fetch_comments(self, post: Post, session: Session, job: ScrapeJob):
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
                body = self.transport.post_form(headers, data, session.cookies, session.proxy)
                payload_json = parsing.fb_json(body)
                parsing.raise_if_rejected(payload_json, "comments")
                parsing.raise_if_doc_id_stale(payload_json, "comments", doc_id)
                page = parsing.parse_comments_page(payload_json)
            except (SessionInvalid, RequestRejected, TransportError):
                # Blocked mid-pagination — keep comments gathered so far; on the very
                # first page (nothing yet) re-raise so the failure is reported.
                if comments:
                    break
                raise

            if not page.comments:
                if policy.should_retry_empty_page(page.critical_codes, empty_retries, page_index):
                    empty_retries += 1
                    time.sleep(policy.empty_page_backoff_seconds(empty_retries))
                    continue
                break

            comments.extend(page.comments)
            tokens.extend(page.reply_tokens)
            page_index += 1
            empty_retries = 0

            cursor = page.page_info.end_cursor
            if not cursor:
                break
            time.sleep(job.min_interval_sec)

        return comments, tokens

    def _fetch_replies(self, comment_fb_id, expansion, session: Session, job: ScrapeJob,
                       reply_sem: threading.Semaphore):
        if not comment_fb_id or not expansion:
            return []
        registry = config.DocIdRegistry()
        doc_id = registry.get("replies")
        headers = friendly_headers(config.FRIENDLY_REPLIES)
        data = payloads.replies_payload(
            comment_feedback_id=comment_fb_id, expansion_token=expansion,
            c_user=session.c_user, fb_dtsg=session.fb_dtsg, doc_id=doc_id,
        )
        with reply_sem:
            body = self.transport.post_form(headers, data, session.cookies, session.proxy)
        return parsing.parse_replies(parsing.fb_json(body))
