from __future__ import annotations

import pytest

from fbgql import runner
from fbgql.models import Session

_SESSION = Session(cookies={"c_user": "111", "xs": "y"}, fb_dtsg="d", c_user="111")


class _FakeGet:
    def __init__(self, html):
        self.html = html
        self.urls: list[str] = []

    def get(self, url, cookies, proxy=None, headers=None):
        self.urls.append(url)
        return self.html


def test_numeric_page_passes_through():
    assert runner._resolve_page_id("100064", _SESSION, _FakeGet("")) == "100064"


def test_resolve_page_id_from_applink_meta():
    html = '<meta property="al:android:url" content="fb://page/?id=987654321" />'
    assert runner._resolve_page_id("ZainSudan", _SESSION, _FakeGet(html)) == "987654321"


def test_resolve_candidates_prefer_feed_owner_over_page_id():
    # The timeline query needs the feed-owner id (userID/profile, 100064…), NOT the
    # classic Page id from delegate_page (which returns an empty node). Both must be
    # offered as candidates, feed-owner first, so the query-probe tries the right one.
    html = '"userID":"100064", ... "delegate_page":{"id":"193805"} ... fb://page/193805'
    cands = runner._resolve_page_id_candidates("ZainSudan", _SESSION, _FakeGet(html))
    assert cands[0] == "100064"          # feed-owner id leads
    assert "193805" in cands             # page id still available as a fallback
    # Back-compat single-id accessor returns the best (feed-owner) candidate.
    assert runner._resolve_page_id("ZainSudan", _SESSION, _FakeGet(html)) == "100064"


def test_resolve_page_id_escaped_slashes():
    html = r'{"url":"fb:\/\/profile\/555000"}'
    assert runner._resolve_page_id("ZainSudan", _SESSION, _FakeGet(html)) == "555000"


def test_resolve_page_id_not_found_tries_about_then_raises():
    fake = _FakeGet("nothing useful here")
    with pytest.raises(ValueError, match="numeric id"):
        runner._resolve_page_id("ZainSudan", _SESSION, fake)
    assert any("/about" in u for u in fake.urls)  # fell back to /about


def test_classify_target_group_url():
    assert runner._classify_target(
        "https://www.facebook.com/groups/2693577247594660"
    ) == ("group", "2693577247594660")
    assert runner._classify_target("groups/2693577247594660") == ("group", "2693577247594660")
    assert runner._classify_target("ronaldo") == ("page", "ronaldo")
    assert runner._classify_target("mohamed.ayuop.5") == ("page", "mohamed.ayuop.5")


def test_resolve_group_candidates_from_group_html():
    html = '"groupID":"2693577247594660","name":"Test Group"'
    fake = _FakeGet(html)
    cands = runner._resolve_page_id_candidates(
        "https://www.facebook.com/groups/AlzeriAlsudani", _SESSION, fake
    )
    assert cands == ["2693577247594660"]
    assert any("/groups/AlzeriAlsudani" in u for u in fake.urls)


def test_numeric_group_url_skips_html():
    fake = _FakeGet("should not be fetched")
    cands = runner._resolve_page_id_candidates(
        "https://www.facebook.com/groups/2693577247594660", _SESSION, fake
    )
    assert cands == ["2693577247594660"]
    assert fake.urls == []


def test_usable_posts_filters_empty_shells():
    from fbgql.models import Post

    posts = [
        Post(post_id="1", feedback_id=None, text="", permalink=None, comment_count=0),
        Post(post_id="2", feedback_id="fid", text="hi", permalink=None, comment_count=1),
    ]
    usable = runner._usable_posts(posts)
    assert [p.post_id for p in usable] == ["2"]
