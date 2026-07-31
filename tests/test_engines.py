"""End-to-end engine wiring + threads-vs-async parity, with a fake transport.

No network: we build an ExecutionPlan by hand and swap in a transport that returns
the fixtures. This locks in pagination, empty-page stop, reply gating, coverage math,
streaming, error isolation, and that both engines agree.
"""

from __future__ import annotations

import json

from fbgql import config, policy
from fbgql.engine.asyncio_engine import AsyncEngine
from fbgql.engine.threaded import ThreadedEngine
from fbgql.models import Account, Post, Profile, ScrapeJob, Session
from fbgql.runner import ExecutionPlan
from tests import fixtures

_EMPTY_END = json.dumps({"data": {"node": {"comment_rendering_instance_for_feed_location": {
    "comments": {"edges": [], "page_info": {"end_cursor": None, "has_next_page": False}}}}}})


def _respond(headers, data):
    if headers.get("x-fb-friendly-name") == config.FRIENDLY_REPLIES:
        return fixtures.REPLIES_PAGE
    cursor = json.loads(data["variables"]).get("commentsAfterCursor")
    return fixtures.COMMENTS_PAGE if cursor is None else _EMPTY_END


class _FakeSync:
    def post_form(self, headers, data, cookies, proxy=None):
        return _respond(headers, data)

    def get(self, *a, **k):
        return ""


class _FakeAsync:
    async def post_form(self, headers, data, cookies, proxy=None):
        return _respond(headers, data)

    async def get(self, *a, **k):
        return ""


class _BoomSync(_FakeSync):
    def post_form(self, headers, data, cookies, proxy=None):
        raise RuntimeError("boom")


def _plan(posts=None, workers=2):
    session = Session(cookies={"c_user": "1"}, fb_dtsg="x", c_user="1", role="primary")
    posts = posts or [
        Post(post_id="A", feedback_id="fA", text="", permalink=None, comment_count=10),
        Post(post_id="B", feedback_id="fB", text="", permalink=None, comment_count=4),
    ]
    assignment = policy.assign_posts(posts, n_workers=workers)
    job = ScrapeJob(page="x", profile=Profile.DEFAULT, min_interval_sec=0,
                    accounts=[Account(cookies={"c_user": "1"})])
    return ExecutionPlan(
        job=job, posts=posts, assignment=assignment,
        worker_sessions=[session] * len(assignment.buckets), registry=config.DocIdRegistry(),
    )


def _summary(result):
    return {p.post.post_id: (p.tops, p.replies, p.total_scraped, round(p.coverage, 3))
            for p in result.posts}


def test_threaded_engine_end_to_end():
    engine = ThreadedEngine()
    engine.transport = _FakeSync()
    result = engine.run(_plan())
    # 2 tops per post; comment 1 has an expansion token -> 1 reply, comment 2 none.
    assert _summary(result) == {"A": (2, 1, 3, 0.3), "B": (2, 1, 3, 0.75)}
    assert round(result.weighted_coverage, 3) == 0.429


def test_async_engine_matches_threaded():
    te = ThreadedEngine()
    te.transport = _FakeSync()
    ae = AsyncEngine()
    ae.transport = _FakeAsync()
    assert _summary(te.run(_plan())) == _summary(ae.run(_plan()))


def test_streaming_yields_every_post():
    engine = ThreadedEngine()
    engine.transport = _FakeSync()
    streamed = list(engine.stream(_plan()))
    assert len(streamed) == 2


def test_failing_post_is_isolated_not_deadlocked():
    # A transport that always raises must still yield one (error) result per post.
    engine = ThreadedEngine()
    engine.transport = _BoomSync()
    results = list(engine.stream(_plan()))
    assert len(results) == 2
    assert all(r.error and "boom" in r.error for r in results)
    assert all(r.total_scraped == 0 for r in results)


def test_max_comments_caps_tops_not_skips():
    engine = ThreadedEngine()
    engine.transport = _FakeSync()
    plan = _plan(posts=[
        Post(post_id="A", feedback_id="fA", text="", permalink=None, comment_count=10),
    ], workers=1)
    plan.job.max_comments = 1
    plan.job.reply_fb_cap = 0  # tops only — cap applies to tops
    result = engine.run(plan)
    assert len(result.posts) == 1
    pr = result.posts[0]
    assert pr.error is None
    assert pr.tops == 1
    assert pr.total_scraped == 1
