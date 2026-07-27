"""Endpoints, headers, GraphQL constants, and the hot-swappable doc_id registry.

doc_ids are treated as *data*, not constants: Facebook rotates them, so they must be
overridable without a code release (env var or job config). See ``fbgql doctor``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

GRAPHQL_URL = "https://www.facebook.com/api/graphql/"
HOME_URL = "https://www.facebook.com/"

# GraphQL "friendly names" sent as x-fb-friendly-name — some surfaces require them.
FRIENDLY_COMMENTS = "CommentsListComponentsPaginationQuery"
FRIENDLY_REPLIES = "Depth1CommentsListPaginationQuery"
FRIENDLY_TIMELINE = "ProfileCometTimelineFeedRefetchQuery"

# The coverage-critical pagination surface. Permalink dialog reaches far more
# top-level comments than the dedicated commenting surface.
FEED_LOCATION = "POST_PERMALINK_DIALOG"
TIMELINE_FEED_LOCATION = "TIMELINE"
COMMENTS_INTENT_TOKEN = "REVERSE_CHRONOLOGICAL_UNFILTERED_INTENT_V1"

# Critical GraphQL error code returned with empty edges mid-pagination. Retryable.
EMPTY_PAGE_RETRY_CODE = 1675012

# Deliberately a bare UA. Facebook's GraphQL endpoint tolerates a simple script
# client, but a full modern-Chrome UA makes it expect the accompanying browser
# header set (sec-ch-ua, x-asbd-id, sec-fetch-*); without those it rejects the
# request as "couldn't be processed" (error 1357054). The proven reference used
# exactly this bare UA across timeline, comments, and replies.
BASE_HEADERS = {
    "user-agent": "Mozilla/5.0",
    "content-type": "application/x-www-form-urlencoded",
}


# ---------------------------------------------------------------------------
# doc_id registry
# ---------------------------------------------------------------------------

# Shipped defaults. Keys are logical names; values are current Facebook doc_ids.
# Treated as data — Meta rotates them (see `fbgql capture` / `fbgql doctor`).
_DEFAULT_DOC_IDS: dict[str, str] = {
    "comments": "27806180149070312",   # CommentsListComponentsPaginationQuery (captured 2026-07)
    "replies": "27888228590762910",    # Depth1CommentsListPaginationQuery (captured 2026-07)
    "timeline": "27872654765686759",   # ProfileCometTimelineFeedRefetchQuery (captured 2026-07)
}

# Provider vars the current UFI comment + reply queries declare as required (both
# CommentsListComponentsPaginationQuery and Depth1CommentsListPaginationQuery). Omitting
# them yields a server-side ``missing_required_variable_value``. Captured 2026-07.
UFI_COMMENT_PROVIDER_VARS: dict = {
    "__relay_internal__pv__CometUFICommentAutoTranslationTyperelayprovider": "ORIGINAL",
    "__relay_internal__pv__CometUFICommentAvatarStickerAnimatedImagerelayprovider": False,
    "__relay_internal__pv__CometUFICommentActionLinksRewriteEnabledrelayprovider": False,
    "__relay_internal__pv__IsWorkUserrelayprovider": False,
}

# Static half of the timeline query's variables. The live persisted query declares
# all of these (including the __relay_internal__pv__* "provider" booleans) as
# REQUIRED — omitting any yields a server-side ``missing_required_variable_value``.
# Captured from a real browser (fbgql capture); tied to the timeline doc_id above.
# Only ``count``, ``cursor``, and ``id`` vary at runtime and are merged in per request.
TIMELINE_VARIABLES_BASE: dict = {
    "afterTime": None,
    "beforeTime": None,
    "feedLocation": "TIMELINE",
    "feedbackSource": 0,
    "focusCommentID": None,
    "memorializedSplitTimeFilter": None,
    "omitPinnedPost": True,
    "postedBy": {"group": "OWNER"},
    "privacy": None,
    "privacySelectorRenderLocation": "COMET_STREAM",
    "referringStoryRenderLocation": None,
    "renderLocation": "timeline",
    "scale": 2,
    "stream_count": 1,
    "taggedInOnly": None,
    "trackingCode": None,
    "useDefaultActor": False,
    "__relay_internal__pv__GHLShouldChangeAdIdFieldNamerelayprovider": False,
    "__relay_internal__pv__GHLShouldChangeSponsoredDataFieldNamerelayprovider": False,
    "__relay_internal__pv__CometFeedStory_enable_reactor_facepilerelayprovider": False,
    "__relay_internal__pv__CometFeedStory_enable_social_bubblesrelayprovider": False,
    "__relay_internal__pv__CometFeedStory_enable_post_permalink_white_space_clickrelayprovider": False,
    "__relay_internal__pv__CometUFICommentActionLinksRewriteEnabledrelayprovider": True,
    "__relay_internal__pv__CometUFICommentAvatarStickerAnimatedImagerelayprovider": False,
    "__relay_internal__pv__IsWorkUserrelayprovider": False,
    "__relay_internal__pv__TestPilotShouldIncludeDemoAdUseCaserelayprovider": False,
    "__relay_internal__pv__FBReels_deprecate_short_form_video_context_gkrelayprovider": True,
    "__relay_internal__pv__FBReels_enable_view_dubbed_audio_type_gkrelayprovider": True,
    "__relay_internal__pv__CometFeedShareMedia_shouldPrefetchShareImagerelayprovider": False,
    "__relay_internal__pv__CometImmersivePhotoCanUserDisable3DMotionrelayprovider": False,
    "__relay_internal__pv__WorkCometIsEmployeeGKProviderrelayprovider": False,
    "__relay_internal__pv__IsMergQAPollsrelayprovider": False,
    "__relay_internal__pv__FBReelsMediaFooter_comet_enable_reels_ads_gkrelayprovider": True,
    "__relay_internal__pv__CometUFIReactionsEnableShortNamerelayprovider": False,
    "__relay_internal__pv__CometUFICommentAutoTranslationTyperelayprovider": "AUTO_TRANSLATE",
    "__relay_internal__pv__CometUFIShareActionMigrationrelayprovider": True,
    "__relay_internal__pv__CometUFISingleLineUFIrelayprovider": False,
    "__relay_internal__pv__relay_provider_comet_ufi_ssr_seo_deferrelayprovider": True,
    "__relay_internal__pv__CometUFI_dedicated_comment_routable_dialog_gkrelayprovider": False,
    "__relay_internal__pv__ReelsIFUCard_reelsIFULikeCountrelayprovider": False,
    "__relay_internal__pv__FBReelsIFUTileContent_reelsIFUPlayOnHoverrelayprovider": True,
    "__relay_internal__pv__GroupsCometGYSJFeedItemHeightrelayprovider": 206,
    "__relay_internal__pv__ShouldEnableBakedInTextStoriesrelayprovider": False,
    "__relay_internal__pv__StoriesShouldIncludeFbNotesrelayprovider": True,
}


@dataclass
class DocIdRegistry:
    """Resolves logical query names to Facebook doc_ids.

    Resolution order (highest priority first):
      1. ``overrides`` passed at construction (e.g. from ScrapeJob).
      2. ``FBGQL_DOC_ID_<NAME>`` environment variable.
      3. Shipped default.
    """

    overrides: dict[str, str] = field(default_factory=dict)

    def get(self, name: str) -> str:
        if name in self.overrides:
            return self.overrides[name]
        env = os.getenv(f"FBGQL_DOC_ID_{name.upper()}")
        if env:
            return env
        try:
            return _DEFAULT_DOC_IDS[name]
        except KeyError as exc:  # pragma: no cover - programmer error
            raise KeyError(f"Unknown doc_id name: {name!r}") from exc

    def all_names(self) -> list[str]:
        return sorted(set(_DEFAULT_DOC_IDS) | set(self.overrides))
