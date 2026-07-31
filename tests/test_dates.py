"""Tests for calendar date → unix parsing with timezones."""

from __future__ import annotations

import pytest

from fbgql.dates import parse_time_bound, parse_timezone


def test_utc_midnight_default():
    # 2026-07-31 00:00 UTC
    assert parse_time_bound("2026-07-31") == 1785456000


def test_offset_plus_three():
    # 2026-07-31 00:00 +03:00 == 2026-07-30 21:00 UTC
    assert parse_time_bound("2026-07-31", tz="+3") == 1785456000 - 3 * 3600
    assert parse_time_bound("2026-07-31", tz="+03:00") == 1785456000 - 3 * 3600
    assert parse_time_bound("2026-07-31", tz="UTC+3") == 1785456000 - 3 * 3600


def test_unix_ignores_timezone():
    assert parse_time_bound(1785456000, tz="+3") == 1785456000
    assert parse_time_bound("1785456000", tz="+3") == 1785456000


def test_parse_timezone_rejects_bad():
    with pytest.raises(ValueError, match="invalid timezone"):
        parse_timezone("Not/AZone")


def test_empty_none():
    assert parse_time_bound(None) is None
    assert parse_time_bound("") is None
    assert parse_time_bound("  ") is None
