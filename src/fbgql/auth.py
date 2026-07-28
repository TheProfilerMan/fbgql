"""Session resolution — the engine never logs in, it consumes cookies.

Given an :class:`Account` (cookies + optional proxy), derive a live ``fb_dtsg`` token
over plain HTTP (no browser) and validate the session. A dead session raises
:class:`SessionInvalid` so callers can alert a human to re-mint cookies.

Reliability notes:
- Facebook serves a stripped page to requests that don't look like a real browser, and
  the token then isn't present. We send full navigation headers to get the real HTML.
- The token is emitted under several shapes; we try all of them plus a loose fallback.
- The interactive minter (``mint.py``) also captures ``fb_dtsg`` straight from the
  logged-in browser and stores it in the session file, so local runs don't depend on
  headless derivation at all.
"""

from __future__ import annotations

import re

from . import config
from .errors import SessionInvalid
from .models import Account, Session
from .transport.sync_http import SyncTransport

# Facebook's own logged-out web client identifies as actor "0" (av=0 / __user=0).
ANONYMOUS_ACTOR = "0"

# Browser-like navigation headers so Facebook returns the real bootstrapped HTML
# (which contains the DTSG token) rather than a minimal shell.
BROWSER_HEADERS = {
    "user-agent": config.BASE_HEADERS["user-agent"],
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,image/apng,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "max-age=0",
    "upgrade-insecure-requests": "1",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
}

# Token appears in the page bootstrap payload under one of these shapes.
_DTSG_PATTERNS = [
    re.compile(r'"DTSGInitialData"\s*,\s*\[\s*\]\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"'),
    re.compile(r'"DTSGInitData"\s*,\s*\[\s*\]\s*,\s*\{[^}]*?"token"\s*:\s*"([^"]+)"'),
    re.compile(r'name="fb_dtsg"\s+value="([^"]+)"'),
    # Loose fallback: any fb_dtsg-ish token assignment (handles minor markup drift).
    re.compile(r'fb_dtsg\\?["\']?\s*[:=]\s*\\?["\']([0-9A-Za-z:_-]{8,})'),
]

# Markers that mean the page came back logged-out rather than just missing the token.
# An empty DTSGInitialData block is the strongest signal (present on a logged-out shell).
_LOGGED_OUT_MARKERS = (
    'dtsginitialdata",[],{}',
    'name="email"',
    "login_form",
    "loginform",
    "checkpoint",
    "two_step_verification",
)


def extract_fb_dtsg(html: str) -> str | None:
    """Pull the fb_dtsg token out of a page's HTML (used by derive and by the minter)."""
    for pattern in _DTSG_PATTERNS:
        m = pattern.search(html)
        if m:
            return m.group(1)
    return None


def derive_fb_dtsg(cookies: dict[str, str], proxy: str | None = None,
                   transport: SyncTransport | None = None) -> str:
    """Fetch a logged-in page with the given cookies and extract fb_dtsg."""
    if not cookies.get("c_user"):
        raise SessionInvalid("cookies missing c_user — not a logged-in session")

    transport = transport or SyncTransport()
    last_reason = "no token found"
    for url in ("https://www.facebook.com/", "https://www.facebook.com/me/"):
        html = transport.get(url, cookies=cookies, proxy=proxy, headers=BROWSER_HEADERS)
        token = extract_fb_dtsg(html)
        if token:
            return token
        # Scan the whole page (markers can appear well past the head).
        low = html.lower()
        if any(m in low for m in _LOGGED_OUT_MARKERS):
            last_reason = "page rendered logged-out (checkpoint or expired cookies)"

    raise SessionInvalid(
        f"could not locate fb_dtsg — {last_reason}. "
        "Re-mint cookies (fbgql mint-session) or pass fb_dtsg explicitly."
    )


def anonymous_session(account: Account | None = None) -> Session:
    """A logged-out session: actor ``0``, no ``fb_dtsg``, cookies optional.

    Verified 2026-07-28 against the live endpoint: ``www.facebook.com/api/graphql/``
    serves public timeline, comment, and reply queries to ``av=0``/``__user=0`` with an
    empty ``fb_dtsg`` and *no cookies at all*. Facebook's own logged-out web client
    additionally sends an ``lsd`` token; ablation showed it is not required for these
    persisted queries, so we don't bootstrap one. (``SyncTransport`` keeps a persistent
    ``requests.Session``, so any anonymous ``datr``/``sb`` Facebook issues during page-id
    resolution is reused automatically for the rest of the run.)

    Coverage is lower than authenticated mode for login-gated content; see the
    anonymous-access report for measured numbers.
    """
    account = account or Account(anonymous=True)
    return Session(
        cookies=dict(account.cookies),
        fb_dtsg="",
        c_user=ANONYMOUS_ACTOR,
        proxy=account.proxy,
        role=account.role,
    )


def resolve_session(account: Account, transport: SyncTransport | None = None) -> Session:
    """Turn an injected Account into a ready Session (fb_dtsg guaranteed)."""
    if account.anonymous:
        return anonymous_session(account)

    c_user = account.c_user
    if not c_user:
        raise SessionInvalid(
            "account cookies missing c_user — pass Account(anonymous=True) "
            "(or --anonymous) for deliberate logged-out access"
        )

    fb_dtsg = account.fb_dtsg or derive_fb_dtsg(account.cookies, account.proxy, transport)
    return Session(
        cookies=account.cookies,
        fb_dtsg=fb_dtsg,
        c_user=c_user,
        proxy=account.proxy,
        role=account.role,
    )
