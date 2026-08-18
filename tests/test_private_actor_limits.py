# tests/test_private_actor_limits.py
from __future__ import annotations

import importlib.util
from pathlib import Path

from fbgql.models import ScrapeJob


def _load_monitoring_patch():
    module_path = Path(__file__).parents[1] / "apify" / "src" / "monitoring_patch.py"
    spec = importlib.util.spec_from_file_location("private_monitoring_patch", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _private_job(*, posts_only: bool, max_comments: int | None) -> ScrapeJob:
    job = ScrapeJob(
        page="example",
        posts_only=posts_only,
        max_comments=max_comments,
    )
    job.monitoring_mode = True
    return job


def test_comment_enabled_run_defaults_to_ten_and_disables_replies():
    patch = _load_monitoring_patch()
    job = _private_job(posts_only=False, max_comments=None)

    patch._apply_private_actor_limits(job)

    assert job.max_comments == 10
    assert job.reply_fb_cap == 0


def test_comment_enabled_run_clamps_requested_limit_to_ten():
    patch = _load_monitoring_patch()
    job = _private_job(posts_only=False, max_comments=100)

    patch._apply_private_actor_limits(job)

    assert job.max_comments == 10
    assert job.reply_fb_cap == 0


def test_comment_enabled_run_allows_lower_limit():
    patch = _load_monitoring_patch()
    job = _private_job(posts_only=False, max_comments=5)

    patch._apply_private_actor_limits(job)

    assert job.max_comments == 5
    assert job.reply_fb_cap == 0


def test_posts_only_run_does_not_enable_comment_work():
    patch = _load_monitoring_patch()
    job = _private_job(posts_only=True, max_comments=None)
    original_reply_cap = job.reply_fb_cap

    patch._apply_private_actor_limits(job)

    assert job.posts_only is True
    assert job.max_comments is None
    assert job.reply_fb_cap == original_reply_cap
