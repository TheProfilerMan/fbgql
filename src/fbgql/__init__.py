"""fbgql — clean-room Facebook GraphQL post & comment scraper.

Public surface. Wrappers, the CLI, and the Apify actor are all just callers of
``Scraper().run(job)`` / ``Scraper().astream(job)``.
"""

from __future__ import annotations

from .errors import (
    DocIdStale,
    RateLimited,
    ScrapeError,
    SessionInvalid,
    TransportError,
)
from .models import (
    SCHEMA_VERSION,
    Account,
    Comment,
    Media,
    Post,
    PostResult,
    Profile,
    Reply,
    Result,
    ScrapeJob,
)
from .scraper import Scraper

__version__ = "0.1.0"

__all__ = [
    "Scraper",
    "ScrapeJob",
    "Account",
    "Profile",
    "Result",
    "PostResult",
    "Post",
    "Comment",
    "Reply",
    "Media",
    "SCHEMA_VERSION",
    # errors
    "ScrapeError",
    "SessionInvalid",
    "DocIdStale",
    "RateLimited",
    "TransportError",
]
