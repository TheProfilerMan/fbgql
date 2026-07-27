from __future__ import annotations

import json

import pytest

from fbgql import auth
from fbgql.cli import _load_session
from fbgql.errors import SessionInvalid


class _FakeGet:
    def __init__(self, html):
        self.html = html

    def get(self, url, cookies, proxy=None, headers=None):
        return self.html


def test_extract_fb_dtsg_shapes():
    assert auth.extract_fb_dtsg('x=["DTSGInitialData",[],{"token":"AbC:123"}];') == "AbC:123"
    assert auth.extract_fb_dtsg('["DTSGInitData",[],{"token":"tok_99","async":1}]') == "tok_99"
    assert auth.extract_fb_dtsg('<input name="fb_dtsg" value="XyZ_9-8">') == "XyZ_9-8"
    assert auth.extract_fb_dtsg("<html>no token here</html>") is None


def test_derive_fb_dtsg_success():
    t = _FakeGet('<script>["DTSGInitialData",[],{"token":"GOOD:1"}]</script>')
    assert auth.derive_fb_dtsg({"c_user": "1", "xs": "y"}, transport=t) == "GOOD:1"


def test_derive_fb_dtsg_missing_c_user():
    with pytest.raises(SessionInvalid):
        auth.derive_fb_dtsg({"xs": "y"}, transport=_FakeGet("whatever"))


def test_derive_fb_dtsg_logged_out():
    t = _FakeGet('<form id="login_form"><input name="email"></form>')
    with pytest.raises(SessionInvalid, match="logged-out"):
        auth.derive_fb_dtsg({"c_user": "1", "xs": "y"}, transport=t)


def test_load_session_flat(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"c_user": "1", "xs": "y"}))
    cookies, fb_dtsg = _load_session(str(p))
    assert cookies["c_user"] == "1"
    assert fb_dtsg is None


def test_load_session_wrapped(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"cookies": {"c_user": "1", "xs": "y"}, "fb_dtsg": "TOK"}))
    cookies, fb_dtsg = _load_session(str(p))
    assert cookies == {"c_user": "1", "xs": "y"}
    assert fb_dtsg == "TOK"


def test_load_session_selenium_list(tmp_path):
    p = tmp_path / "j.json"
    p.write_text(json.dumps([{"name": "c_user", "value": "1"}, {"name": "xs", "value": "y"}]))
    cookies, fb_dtsg = _load_session(str(p))
    assert cookies == {"c_user": "1", "xs": "y"}
    assert fb_dtsg is None
