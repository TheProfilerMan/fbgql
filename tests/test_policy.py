from __future__ import annotations

from fbgql import policy
from fbgql.config import EMPTY_PAGE_RETRY_CODE
from fbgql.models import Post


def test_want_replies_semantics():
    assert policy.want_replies(None, 99999) is True      # None = always
    assert policy.want_replies(0, 1) is False            # 0 = never
    assert policy.want_replies(1500, 1499) is True       # under cap
    assert policy.want_replies(1500, 1500) is False      # at/over cap


def test_trim_to_max_comments():
    comments = list("abcdef")
    tokens = list(range(6))
    c, t, hit = policy.trim_to_max_comments(comments, tokens, None)
    assert (c, t, hit) == (comments, tokens, False)
    c, t, hit = policy.trim_to_max_comments(comments, tokens, 6)
    assert (c, t, hit) == (comments, tokens, False)
    c, t, hit = policy.trim_to_max_comments(comments, tokens, 3)
    assert c == list("abc") and t == [0, 1, 2] and hit is True
    c, t, hit = policy.trim_to_max_comments(comments, tokens, 0)
    assert c == [] and t == [] and hit is True


def test_backoff_schedules():
    assert policy.empty_page_backoff_seconds(1) == 3
    assert policy.empty_page_backoff_seconds(20) == 30   # capped
    assert policy.transport_backoff_seconds(1) == 2
    assert policy.transport_backoff_seconds(100) == 20   # capped


def test_should_retry_empty_page():
    # First page empty is never retried.
    assert policy.should_retry_empty_page([EMPTY_PAGE_RETRY_CODE], 0, page_index=0) is False
    # Mid-pagination with the retry code, under ceiling.
    assert policy.should_retry_empty_page([EMPTY_PAGE_RETRY_CODE], 1, page_index=2) is True
    # Different code -> no retry.
    assert policy.should_retry_empty_page([9999], 1, page_index=2) is False
    # Over the ceiling -> stop.
    assert policy.should_retry_empty_page([EMPTY_PAGE_RETRY_CODE], policy.MAX_EMPTY_RETRIES, 2) is False


def _posts(counts):
    return [Post(post_id=str(i), feedback_id=None, text="", permalink=None, comment_count=c)
            for i, c in enumerate(counts)]


def test_assign_posts_balances_load():
    a = policy.assign_posts(_posts([100, 90, 80, 70, 10]), n_workers=2)
    assert len(a.buckets) == 2
    # Every post assigned exactly once.
    assigned = [p for b in a.buckets for p in b]
    assert len(assigned) == 5
    loads = [sum(p.comment_count for p in b) for b in a.buckets]
    assert abs(loads[0] - loads[1]) <= 30  # reasonably balanced


def test_assign_posts_pins_mega():
    a = policy.assign_posts(_posts([5000, 100, 90, 80]), n_workers=3, mega_threshold=3000)
    assert a.mega_worker == 0
    assert a.mega_post_id == "0"
    assert [p.post_id for p in a.buckets[0]] == ["0"]  # mega alone
    # The rest are packed into workers 1 and 2, not worker 0.
    assert a.buckets[1] or a.buckets[2]
