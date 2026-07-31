"""Parse human date bounds into unix seconds.

Calendar ``YYYY-MM-DD`` values are midnight in the chosen timezone (default UTC).
Unix timestamps are left as-is (already absolute).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# +3, +03, +03:00, UTC+3, GMT-5:30, etc.
_OFFSET_RE = re.compile(
    r"^(?:UTC|GMT)?\s*([+-])(\d{1,2})(?::?(\d{2}))?\s*$",
    re.IGNORECASE,
)


def parse_timezone(value: str | None) -> timezone | ZoneInfo:
    """Resolve a timezone string to a ``tzinfo``.

    Accepts:
      - empty / None / ``UTC`` / ``GMT`` → UTC
      - numeric offsets: ``+3``, ``+03:00``, ``UTC+3``, ``-5:30``
      - IANA names: ``Africa/Khartoum``, ``Asia/Riyadh``, ``America/New_York``
    """
    if value is None:
        return timezone.utc
    text = str(value).strip()
    if not text or text.upper() in ("UTC", "GMT", "Z"):
        return timezone.utc

    m = _OFFSET_RE.match(text)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        hours = int(m.group(2))
        minutes = int(m.group(3) or 0)
        if hours > 14 or minutes > 59:
            raise ValueError(f"invalid timezone offset {value!r}")
        return timezone(sign * timedelta(hours=hours, minutes=minutes))

    try:
        return ZoneInfo(text)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            f"invalid timezone {value!r}: use UTC, an offset like +03:00, "
            "or an IANA name like Africa/Khartoum"
        ) from exc


def parse_time_bound(
    value: str | int | float | None,
    *,
    tz: str | timezone | ZoneInfo | None = None,
) -> int | None:
    """Parse a unix timestamp or ``YYYY-MM-DD`` into unix seconds.

    Empty / None → None. Digits (or an int/float) → unix seconds (timezone ignored).
    Date strings → midnight of that calendar day in ``tz`` (default UTC).
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

    if isinstance(tz, (timezone, ZoneInfo)):
        tzinfo = tz
    else:
        tzinfo = parse_timezone(tz)

    try:
        dt = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=tzinfo)
    except ValueError as exc:
        raise ValueError(
            f"invalid time bound {value!r}: use unix seconds or YYYY-MM-DD"
        ) from exc
    return int(dt.timestamp())
