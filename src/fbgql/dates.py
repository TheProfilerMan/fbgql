"""Parse human date bounds into unix seconds (UTC)."""

from __future__ import annotations

from datetime import datetime, timezone


def parse_time_bound(value: str | int | float | None) -> int | None:
    """Parse a unix timestamp or ``YYYY-MM-DD`` (UTC midnight) into unix seconds.

    Empty / None → None. Digits (or an int/float) → unix seconds. Date strings →
    UTC midnight of that day.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"invalid time bound {value!r}: use unix seconds or YYYY-MM-DD")
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    try:
        dt = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(
            f"invalid time bound {value!r}: use unix seconds or YYYY-MM-DD"
        ) from exc
    return int(dt.timestamp())
