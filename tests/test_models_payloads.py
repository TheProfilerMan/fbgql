from __future__ import annotations

import json

from fbgql import config, payloads
from fbgql.models import Account, Profile, ScrapeJob


def test_profile_resolution_and_overrides():
    assert ScrapeJob(profile=Profile.DEFAULT).resolved_policy() == (3, 1500)
    assert ScrapeJob(profile=Profile.TOPS_ONLY).resolved_policy() == (1, 0)
    assert ScrapeJob(profile=Profile.FULL_REPLIES).resolved_policy() == (3, None)
    # String profile accepted.
    assert ScrapeJob(profile="default").resolved_policy() == (3, 1500)
    # Explicit overrides win.
    j = ScrapeJob(profile=Profile.DEFAULT, workers=5, reply_fb_cap=0)
    assert j.resolved_policy() == (5, 0)
    # Sentinel -1 means "keep the profile preset".
    assert ScrapeJob(profile=Profile.DEFAULT, reply_fb_cap=-1).resolved_policy() == (3, 1500)


def test_account_c_user():
    assert Account(cookies={"c_user": "42", "xs": "x"}).c_user == "42"
    assert Account(cookies={}).c_user is None


def test_comments_payload_shape():
    p = payloads.comments_payload(feedback_id="FID", cursor="CUR", c_user="42",
                                  fb_dtsg="DTSG", doc_id="DOC")
    assert p["doc_id"] == "DOC"
    assert p["fb_dtsg"] == "DTSG"
    assert p["av"] == "42" and p["__user"] == "42"
    variables = json.loads(p["variables"])
    assert variables["feedLocation"] == config.FEED_LOCATION
    assert variables["commentsAfterCursor"] == "CUR"
    assert variables["id"] == "FID"
    # Request parity with the live query (missing these => missing_required_variable_value).
    assert variables["useDefaultActor"] is False
    assert variables["focusCommentID"] is None
    assert variables["__relay_internal__pv__IsWorkUserrelayprovider"] is False
    assert "__relay_internal__pv__CometUFICommentActionLinksRewriteEnabledrelayprovider" in variables


def test_replies_payload_shape():
    p = payloads.replies_payload(comment_feedback_id="CFID", expansion_token="EXP",
                                 c_user="42", fb_dtsg="D", doc_id="DOC")
    variables = json.loads(p["variables"])
    assert variables["expansionToken"] == "EXP"
    assert variables["id"] == "CFID"
    assert variables["useDefaultActor"] is False
    assert variables["clientKey"] is None
    assert variables["repliesAfterCursor"] is None
    assert variables["__relay_internal__pv__IsWorkUserrelayprovider"] is False


def test_posts_payload_shape():
    p = payloads.posts_payload(user_id="PID", cursor="CUR", c_user="42",
                               fb_dtsg="D", doc_id="DOC")
    variables = json.loads(p["variables"])
    assert variables["id"] == "PID"
    assert variables["cursor"] == "CUR"
    assert variables["count"] == 3
    assert variables["feedLocation"] == config.TIMELINE_FEED_LOCATION
    assert variables["renderLocation"] == "timeline"
    assert variables["useDefaultActor"] is False
    # Modern query requires the provider-var block and postedBy (else 500 on the server).
    assert variables["postedBy"] == {"group": "OWNER"}
    assert variables["omitPinnedPost"] is True
    assert any(k.startswith("__relay_internal__pv__") for k in variables)


def test_doc_id_registry_override(monkeypatch):
    reg = config.DocIdRegistry(overrides={"comments": "OVERRIDDEN"})
    assert reg.get("comments") == "OVERRIDDEN"
    # Env var beats default but not explicit override.
    monkeypatch.setenv("FBGQL_DOC_ID_REPLIES", "FROM_ENV")
    assert config.DocIdRegistry().get("replies") == "FROM_ENV"
