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
