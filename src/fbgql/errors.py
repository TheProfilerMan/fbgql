"""Exception hierarchy for fbgql."""

from __future__ import annotations


class ScrapeError(Exception):
    """Base class for all fbgql errors."""


class SessionInvalid(ScrapeError):
    """The session (cookies) is no longer valid.

    Raised on checkpoint / login_required / missing ``c_user``. An ephemeral worker
    cannot recover from this — a human must re-mint cookies. Callers (wrappers, the
    Apify actor) should catch this and surface a clear "re-authenticate" alert.
    """


class DocIdStale(ScrapeError):
    """A GraphQL ``doc_id`` appears to have been rotated by Facebook.

    The registry value no longer resolves. Refresh via ``FBGQL_DOC_ID_*`` env vars
    or job config; run ``fbgql doctor`` to detect.
    """


class RateLimited(ScrapeError):
    """Facebook is throttling requests (429 / block / repeated empty pages)."""


class RequestRejected(ScrapeError):
    """Facebook rejected the request outright with its error envelope.

    Typically an account restriction, automation flag, or hard rate-limit — the UI may
    still work for normal browsing while programmatic GraphQL is refused.
    """


class TransportError(ScrapeError):
    """A network/transport failure that survived all retries."""
