"""Pure builders for Facebook GraphQL request bodies.

No network, no state — just (identifiers, cursor, tokens) -> form-field dict. Shared
by both the threaded and async engines so request shape is identical across them.
"""

from __future__ import annotations

import json

from . import config


def _base_form(c_user: str, fb_dtsg: str, doc_id: str, variables: dict) -> dict[str, str]:
    return {
        "av": c_user,
        "__user": c_user,
        "__a": "1",
        "fb_dtsg": fb_dtsg or "",
        "doc_id": doc_id,
        "variables": json.dumps(variables, separators=(",", ":")),
    }


def comments_payload(
    *,
    feedback_id: str,
    cursor: str | None,
    c_user: str,
    fb_dtsg: str,
    doc_id: str,
) -> dict[str, str]:
    """Top-level comments pagination body (permalink dialog surface)."""
    variables = {
        "commentsAfterCount": -1,
        "commentsAfterCursor": cursor,
        "commentsBeforeCount": None,
        "commentsBeforeCursor": None,
        "commentsIntentToken": config.COMMENTS_INTENT_TOKEN,
        "feedLocation": config.FEED_LOCATION,
        "focusCommentID": None,
        "scale": 2,
        "useDefaultActor": False,
        "id": feedback_id,
        **config.UFI_COMMENT_PROVIDER_VARS,
    }
    return _base_form(c_user, fb_dtsg, doc_id, variables)


def replies_payload(
    *,
    comment_feedback_id: str,
    expansion_token: str,
    c_user: str,
    fb_dtsg: str,
    doc_id: str,
) -> dict[str, str]:
    """Depth-1 replies body for a single top-level comment."""
    variables = {
        "clientKey": None,
        "expansionToken": expansion_token,
        "feedLocation": config.FEED_LOCATION,
        "focusCommentID": None,
        "repliesAfterCount": None,
        "repliesAfterCursor": None,
        "repliesBeforeCount": None,
        "repliesBeforeCursor": None,
        "scale": 2,
        "useDefaultActor": False,
        "id": comment_feedback_id,
        **config.UFI_COMMENT_PROVIDER_VARS,
    }
    return _base_form(c_user, fb_dtsg, doc_id, variables)


def posts_payload(
    *,
    user_id: str,
    cursor: str | None,
    c_user: str,
    fb_dtsg: str,
    doc_id: str,
    count: int = 3,
) -> dict[str, str]:
    """Page timeline feed pagination body.

    The modern ``ProfileCometTimelineFeedRefetchQuery`` requires a large, mostly
    static variable set (see ``config.TIMELINE_VARIABLES_BASE``); only count/cursor/id
    vary per request.
    """
    variables = {
        **config.TIMELINE_VARIABLES_BASE,
        "count": count,
        "cursor": cursor,
        "id": user_id,
    }
    return _base_form(c_user, fb_dtsg, doc_id, variables)
