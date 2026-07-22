from datetime import datetime, time, timedelta, timezone

import pytest

from app.analytics.stats import compute_stats, parse_tz
from app.analytics.store import SqliteStore


def test_parse_tz_valid():
    assert parse_tz("360") == 360
    assert parse_tz(-300) == -300
    assert parse_tz(0) == 0


def test_parse_tz_rejects():
    for bad in ["abc", "841", "-841", "1); DROP TABLE events;--", None, ""]:
        with pytest.raises(ValueError):
            parse_tz(bad)


def test_parse_tz_rejects_non_integer_float():
    # A non-HTTP caller could pass a real float; int(3.5) would silently
    # truncate to 3 instead of rejecting it. String "3.5" already raises
    # via int(), this covers the float-arrives-directly path.
    with pytest.raises(ValueError):
        parse_tz(3.5)
    with pytest.raises(ValueError):
        parse_tz(-3.5)


def test_parse_tz_boundary_inclusive():
    assert parse_tz(840) == 840
    assert parse_tz(-840) == -840
    assert parse_tz("840") == 840
    assert parse_tz("-840") == -840


def _seeded():
    s = SqliteStore(":memory:")
    s.init_schema()
    rows = [
        ("2026-07-17 03:00:00", "visit", None, "BD", "v1"),
        ("2026-07-17 03:01:00", "fetch", "ok", "BD", "v1"),
        ("2026-07-17 03:02:00", "download", "1080p", "BD", "v1"),
        ("2026-07-17 04:00:00", "visit", None, "US", "v2"),
        ("2026-07-17 04:01:00", "fetch", "no_video", "US", "v2"),
        ("2026-07-18 03:00:00", "visit", None, "BD", "v1b"),
        ("2026-07-18 03:01:00", "fetch", "ok", "BD", "v1b"),
    ]
    s.execute_many([
        ("INSERT INTO events (ts,type,outcome,country,visitor) VALUES (?,?,?,?,?)", list(r))
        for r in rows
    ])
    return s


def test_compute_stats_shape_and_values():
    stats = compute_stats(_seeded(), days=30, tz=0)
    assert stats["totals"]["fetches"]["all_time"] == 3
    assert stats["totals"]["downloads"]["all_time"] == 1
    assert stats["totals"]["visits"]["all_time"] == 3
    # countries
    countries = {c["country"]: c["count"] for c in stats["countries"]}
    assert countries["BD"] >= 1 and countries["US"] >= 1
    # qualities
    assert stats["qualities"] == [{"quality": "1080p", "count": 1}]
    # errors (non-ok fetch outcomes)
    errs = {e["code"]: e["count"] for e in stats["errors"]}
    assert errs["no_video"] == 1
    # series has per-day rows
    assert len(stats["series"]) >= 2
    # conversion = fetch-visitor-days / visitor-days on a daily-unique basis
    assert 0.0 <= stats["totals"]["conversion"] <= 1.0


def test_countries_always_includes_unknown_bucket():
    # Spec: "top 10 plus an unknown bucket" - the unknown/null-country bucket
    # must always be present, not just when it ranks in the combined top 11.
    s = SqliteStore(":memory:")
    s.init_schema()
    rows = [
        ("2026-07-18 03:00:00", "visit", None, "BD", "v1"),
        ("2026-07-18 03:01:00", "visit", None, "US", "v2"),
    ]
    s.execute_many([
        ("INSERT INTO events (ts,type,outcome,country,visitor) VALUES (?,?,?,?,?)", list(r))
        for r in rows
    ])
    stats = compute_stats(s, days=30, tz=0)
    countries = {c["country"]: c["count"] for c in stats["countries"]}
    assert "unknown" in countries
    assert countries["unknown"] == 0


def test_conversion_is_sum_of_daily_distinct_not_cross_day_distinct():
    # 3 days, same visitor (v1) appears on two different days, v2 appears on
    # every day, v3 fetches without ever "visiting", v4 visits but never
    # fetches. A correct sum-of-daily-distinct conversion differs from a
    # cross-day COUNT(DISTINCT) implementation, which would instead compute
    # 3/4 = 0.75 (global-distinct fetchers over global-distinct visitors).
    s = SqliteStore(":memory:")
    s.init_schema()
    rows = [
        # day 1 (2026-07-16): v1 visits only, v2 visits + fetches
        ("2026-07-16 03:00:00", "visit", None, "BD", "v1"),
        ("2026-07-16 03:05:00", "visit", None, "US", "v2"),
        ("2026-07-16 03:06:00", "fetch", "ok", "US", "v2"),
        # day 2 (2026-07-17): v1 fetches (no visit event needed), v3 fetches only
        ("2026-07-17 03:00:00", "fetch", "ok", "BD", "v1"),
        ("2026-07-17 03:01:00", "fetch", "ok", "US", "v3"),
        # day 3 (2026-07-18): v2 fetches only, v4 visits and never fetches
        ("2026-07-18 03:00:00", "fetch", "ok", "US", "v2"),
        ("2026-07-18 03:01:00", "visit", None, "BD", "v4"),
    ]
    s.execute_many([
        ("INSERT INTO events (ts,type,outcome,country,visitor) VALUES (?,?,?,?,?)", list(r))
        for r in rows
    ])
    stats = compute_stats(s, days=30, tz=0)
    # visitor-days = 6: (v1,v2) day1, (v1,v3) day2, (v2,v4) day3
    # fetch-visitor-days = 4: v2 day1, v1+v3 day2, v2 day3
    assert stats["totals"]["conversion"] == round(4 / 6, 3)


def test_compute_stats_nonzero_tz_window_not_truncated_and_hour_shift():
    # Regression for: the multi-day window used a fixed UTC instant while
    # series/hours/uniq bucket by LOCAL date. For tz != 0 that truncates the
    # oldest local day. Uses a real Dhaka-style offset (+360 min).
    tz = 360
    days = 30

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    local_now = now + timedelta(minutes=tz)
    earliest_local_day = (local_now - timedelta(days=days)).date()
    earliest_local_midnight_utc = datetime.combine(earliest_local_day, time.min) - timedelta(minutes=tz)

    # The OLD buggy filter was `ts >= datetime('now', '-{days} days')`, a
    # fixed UTC instant. Its local-time representation is exactly
    # (local_now - days), i.e. earliest_local_day at local_now's
    # time-of-day - NOT local midnight. Anything between local midnight and
    # that instant would be wrongly excluded even though it belongs to a day
    # that should be fully included.
    buggy_cutoff = now - timedelta(days=days)
    gap = buggy_cutoff - earliest_local_midnight_utc
    assert gap > timedelta(0), "test must not run exactly at local midnight"

    boundary_event_ts = earliest_local_midnight_utc + gap / 2
    assert boundary_event_ts < buggy_cutoff
    assert (boundary_event_ts + timedelta(minutes=tz)).date() == earliest_local_day

    # A second event: UTC 22:00 on some day comfortably inside the window
    # rolls forward to the *next* local day at local hour 04:00.
    shift_utc_day = earliest_local_day + timedelta(days=5)
    shift_utc = datetime.combine(shift_utc_day, time(22, 0, 0))
    shift_local = shift_utc + timedelta(minutes=tz)
    assert shift_local.date() == shift_utc_day + timedelta(days=1)
    assert shift_local.hour == 4

    boundary_local_hour = (boundary_event_ts + timedelta(minutes=tz)).hour
    expected_hour4_count = 1 + (1 if boundary_local_hour == 4 else 0)

    def fmt(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    s = SqliteStore(":memory:")
    s.init_schema()
    s.execute_many([
        ("INSERT INTO events (ts,type,outcome,country,visitor) VALUES (?,?,?,?,?)",
         [fmt(boundary_event_ts), "visit", None, "BD", "boundary-visitor"]),
        ("INSERT INTO events (ts,type,outcome,country,visitor) VALUES (?,?,?,?,?)",
         [fmt(shift_utc), "fetch", "ok", "BD", "shift-visitor"]),
    ])

    stats = compute_stats(s, days=days, tz=tz)
    series_by_day = {row["day"]: row for row in stats["series"]}

    earliest_day_str = earliest_local_day.isoformat()
    assert earliest_day_str in series_by_day, "earliest local day missing/truncated by the window filter"
    assert series_by_day[earliest_day_str]["visit"] == 1

    shift_local_day_str = (shift_utc_day + timedelta(days=1)).isoformat()
    assert shift_local_day_str in series_by_day
    assert series_by_day[shift_local_day_str]["fetch"] == 1

    hours_by_hour = {row["hour"]: row["count"] for row in stats["hours"]}
    assert hours_by_hour.get(4) == expected_hour4_count


def test_stats_platforms_breakdown():
    from app.analytics.stats import compute_stats
    from app.analytics.store import SqliteStore
    s = SqliteStore(":memory:")
    s.init_schema()
    rows = [
        ("2026-07-20 10:00:00", "fetch", "ok", None, "v1", "twitter"),
        ("2026-07-20 10:01:00", "fetch", "ok", None, "v2", "tiktok"),
        ("2026-07-20 10:02:00", "download", "hd", None, "v2", "tiktok"),
    ]
    s.execute_many([("INSERT INTO events (ts,type,outcome,country,visitor,platform) VALUES (?,?,?,?,?,?)", list(r)) for r in rows])
    out = compute_stats(s, days=30, tz=0)
    by = {p["platform"]: p for p in out["platforms"]}
    assert by["twitter"]["fetches"] == 1
    assert by["tiktok"]["fetches"] == 1
    assert by["tiktok"]["downloads"] == 1
