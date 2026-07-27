"""Transport protocol + shared HTTP concerns (headers, error classification).

Two implementations exist — sync (requests) and async (httpx) — but they share the
same interface and the same rules for what counts as "blocked" vs "retryable". The
GraphQL retry loop (the 1675012 case) lives in the engine, not here; this layer only
handles transport-level failures (timeouts, proxy errors, 5xx, throttling).
"""

from __future__ import annotations

from typing import Protocol

from .. import config

# Body markers that indicate the session/IP is blocked or logged out.
_BLOCK_MARKERS = ("checkpoint", "login_required", "not logged in", "please log in")
_SESSION_DEAD_MARKERS = ("login_required", "checkpoint")


def friendly_headers(friendly_name: str, referer: str | None = None) -> dict[str, str]:
    headers = dict(config.BASE_HEADERS)
    headers["x-fb-friendly-name"] = friendly_name
    headers["origin"] = "https://www.facebook.com"
    headers["referer"] = referer or config.HOME_URL
    return headers


def proxies_dict(proxy: str | None) -> dict[str, str] | None:
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


def is_blocked(status_code: int, body: str) -> bool:
    """True if the response indicates throttling/blocking (retry after backoff)."""
    if status_code in (403, 429, 503):
        return True
    low = body[:2000].lower()
    return any(m in low for m in _BLOCK_MARKERS)


def is_session_dead(status_code: int, body: str) -> bool:
    """True if the failure is specifically an invalid/expired session (do not retry)."""
    low = body[:2000].lower()
    return any(m in low for m in _SESSION_DEAD_MARKERS)


class Transport(Protocol):
    """Minimal transport surface used by engines and auth."""

    def post_form(
        self,
        headers: dict[str, str],
        data: dict[str, str],
        cookies: dict[str, str],
        proxy: str | None = None,
    ) -> str:
        """POST form-encoded data to the GraphQL endpoint; return the raw body."""
        ...

    def get(
        self,
        url: str,
        cookies: dict[str, str],
        proxy: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        """GET a page (used to derive fb_dtsg); return the raw body."""
        ...
