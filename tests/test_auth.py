from __future__ import annotations

import base64
import json

import pytest

from fbgql import auth, payloads, runner
from fbgql.cli import _load_session
from fbgql.errors import SessionInvalid
from fbgql.models import Account, ScrapeJob


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


def test_anonymous_session_shape():
    """Logged-out session is actor 0 with no fb_dtsg — verified against live FB 2026-07-28."""
    s = auth.anonymous_session()
    assert s.c_user == "0"
    assert s.fb_dtsg == ""
    assert s.cookies == {}


def test_anonymous_session_keeps_proxy_and_cookies():
    acct = Account.anonymous_account(proxy="http://p:1", cookies={"datr": "d"})
    s = auth.anonymous_session(acct)
    assert (s.c_user, s.fb_dtsg, s.proxy, s.cookies) == ("0", "", "http://p:1", {"datr": "d"})


def test_resolve_session_anonymous_flag_skips_c_user_gate():
    s = auth.resolve_session(Account(cookies={}, anonymous=True))
    assert s.c_user == "0"


def test_resolve_session_missing_c_user_still_fails_loudly():
    """A session that merely LOST c_user is dead, not anonymous — must not degrade silently."""
    with pytest.raises(SessionInvalid, match="anonymous"):
        auth.resolve_session(Account(cookies={"datr": "d"}))


def test_anonymous_payload_shape_matches_logged_out_client():
    """av/__user must be "0" and fb_dtsg empty — the shape proven to work anonymously."""
    form = payloads.comments_payload(
        feedback_id="ZmVlZGJhY2s6MQ==", cursor=None,
        c_user=auth.anonymous_session().c_user,
        fb_dtsg=auth.anonymous_session().fb_dtsg, doc_id="123",
    )
    assert form["av"] == "0"
    assert form["__user"] == "0"
    assert form["fb_dtsg"] == ""


def test_feedback_id_is_base64_of_feedback_colon_post_id():
    """The anonymous path needs no bootstrap: feedback_id is derivable from post_id alone."""
    assert runner.feedback_id_for_post("1543860544451858") == (
        base64.b64encode(b"feedback:1543860544451858").decode()
    )


def test_anonymous_job_needs_no_accounts():
    primary, mega = runner._resolve_sessions(ScrapeJob(page="x", anonymous=True), transport=None)
    assert primary.c_user == "0"
    assert mega is None


def test_no_accounts_defaults_to_anonymous():
    """Anonymous is the DEFAULT: a job with no accounts runs logged-out, not an error."""
    primary, mega = runner._resolve_sessions(ScrapeJob(page="x"), transport=None)
    assert primary.c_user == "0"
    assert primary.fb_dtsg == ""
    assert mega is None


def test_anonymous_flag_overrides_supplied_accounts():
    """anonymous=True forces logged-out even when a session was configured."""
    job = ScrapeJob(page="x", anonymous=True,
                    accounts=[Account(cookies={"c_user": "1", "xs": "y"}, proxy="http://p:1")])
    primary, _ = runner._resolve_sessions(job, transport=None)
    assert primary.c_user == "0"
    assert primary.proxy == "http://p:1"   # proxy is still honoured


def test_supplied_account_missing_c_user_still_raises():
    """The safety property survives the default flip: a dead session is not anonymous."""
    job = ScrapeJob(page="x", accounts=[Account(cookies={"datr": "d"})])
    with pytest.raises(SessionInvalid, match="anonymous"):
        runner._resolve_sessions(job, transport=None)


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
