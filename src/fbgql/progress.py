"""Lightweight progress reporting for long-running scrape steps.

Callers (CLI, Apify) set ``ScrapeJob.on_progress``; engines/runner call
:func:`emit` so the user sees activity instead of a silent hang.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ScrapeJob

ProgressFn = Callable[[str], None]


def emit(job: ScrapeJob | None, message: str) -> None:
    """Send a progress line if the job has an ``on_progress`` callback."""
    if job is None:
        return
    fn = getattr(job, "on_progress", None)
    if fn is not None:
        fn(message)
