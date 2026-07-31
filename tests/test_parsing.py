from __future__ import annotations

from fbgql import parsing
from tests import fixtures


def test_fb_json_strips_prefix():
    data = parsing.fb_json(fixtures.COMMENTS_EMPTY_1675012)
    assert "data" in data
    assert data["errors"][0]["code"] == 1675012


def test_parse_comments_page_basic():
    page = parsing.parse_comments_page(parsing.fb_json(fixtures.COMMENTS_PAGE))
    assert len(page.comments) == 2
    assert page.page_info.end_cursor == "CURSOR_1"
    assert page.page_info.has_next_page is True

    first = page.comments[0]
    assert first.comment_id == "111"
    assert first.author == "Alice"
    assert first.text == "hello world"
    assert first.reaction_count == 3
    assert first.created_time == 1690000000
    assert [(r.type, r.count) for r in first.reactions] == [("like", 2), ("love", 1)]
    assert first.reactions[0].name == "Like"
    # reply tokens are index-aligned
    assert page.reply_tokens[0] == ("fb_comment_1", "exp_tok_1")


def test_parse_comments_media_only():
    page = parsing.parse_comments_page(parsing.fb_json(fixtures.COMMENTS_PAGE))
    media_comment = page.comments[1]
    assert media_comment.text == ""
    assert media_comment.media is not None
    assert media_comment.media.type == "photo"
    assert media_comment.media.url == "https://x/p.jpg"
    assert media_comment.reaction_count == 1  # falls back to reactors.count


def test_parse_comments_empty_page_carries_critical_code():
    page = parsing.parse_comments_page(parsing.fb_json(fixtures.COMMENTS_EMPTY_1675012))
    assert page.comments == []
    assert 1675012 in page.critical_codes


def test_parse_replies():
    replies = parsing.parse_replies(parsing.fb_json(fixtures.REPLIES_PAGE))
    assert len(replies) == 1
    assert replies[0].author == "Carol"
    assert replies[0].text == "a reply"


def test_fb_request_error_envelope_detected():
    import json

    import pytest

    from fbgql.errors import RequestRejected

    envelope = json.dumps({
        "error": 1357054,
        "errorSummary": "Your request couldn't be processed",
        "errorDescription": "There was a problem with this request.",
    })
    data = parsing.fb_json(envelope)
    err = parsing.fb_request_error(data)
    assert err["code"] == 1357054
    assert "couldn't be processed" in err["summary"]

    # A normal GraphQL data response is NOT flagged as a rejection.
    assert parsing.fb_request_error(parsing.fb_json(fixtures.COMMENTS_PAGE)) is None

    with pytest.raises(RequestRejected, match="1357054"):
        parsing.raise_if_rejected(data, "timeline")


def test_login_required_envelope_raises_session_invalid():
    import json

    import pytest

    from fbgql.errors import SessionInvalid

    envelope = json.dumps({
        "error": 1357001,
        "errorSummary": "Log in to continue",
        "errorDescription": "Please log in to your account.",
    })
    data = parsing.fb_json(envelope)
    # A logged-out session must surface as SessionInvalid (re-mint), not RequestRejected.
    with pytest.raises(SessionInvalid, match="logged out"):
        parsing.raise_if_rejected(data, "timeline")


def test_parse_posts_and_comment_count():
    posts, cursor = parsing.parse_posts(fixtures.TIMELINE_PAGE, page_name="ZainSudan")
    assert cursor == "NEXT_CURSOR"
    assert len(posts) == 1
    p = posts[0]
    assert p.post_id == "999"
    assert p.feedback_id == "post_fb_1"
    assert p.text == "a post"
    assert p.comment_count == 7
    assert p.page_name == "ZainSudan"
    assert p.created_time == 1785434442
    assert p.reaction_count == 12
    assert p.share_count == 2
    assert [(r.type, r.count) for r in p.reactions] == [("like", 10), ("love", 2)]
