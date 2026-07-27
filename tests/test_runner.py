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
