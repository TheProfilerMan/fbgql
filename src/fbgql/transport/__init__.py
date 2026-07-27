"""Transport implementations behind a common protocol."""

from __future__ import annotations

from .async_http import AsyncTransport
from .base import Transport, friendly_headers, is_blocked, is_session_dead, proxies_dict
from .sync_http import SyncTransport

__all__ = [
    "Transport",
    "SyncTransport",
    "AsyncTransport",
    "friendly_headers",
    "is_blocked",
    "is_session_dead",
    "proxies_dict",
]
