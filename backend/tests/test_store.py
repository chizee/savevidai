import pytest

from app.analytics.store import SqliteStore, _raise_on_pipeline_errors


def test_schema_and_roundtrip():
    s = SqliteStore(":memory:")
    s.init_schema()
    s.execute_many([
        ("INSERT INTO events (ts, type, outcome, country, visitor) VALUES (?,?,?,?,?)",
         ["2026-07-17 10:00:00", "fetch", "ok", "BD", "abc123"]),
        ("INSERT INTO events (ts, type, outcome, country, visitor) VALUES (?,?,?,?,?)",
         ["2026-07-17 10:01:00", "download", "1080p", None, "abc123"]),
    ])
    rows = s.query("SELECT type, outcome, country, visitor FROM events ORDER BY id", [])
    assert rows[0] == {"type": "fetch", "outcome": "ok", "country": "BD", "visitor": "abc123"}
    assert rows[1]["outcome"] == "1080p"
    assert rows[1]["country"] is None


def test_query_with_args():
    s = SqliteStore(":memory:")
    s.init_schema()
    s.execute_many([
        ("INSERT INTO events (ts, type, outcome, country, visitor) VALUES (?,?,?,?,?)",
         ["2026-07-17 10:00:00", "fetch", "ok", None, "v1"]),
        ("INSERT INTO events (ts, type, outcome, country, visitor) VALUES (?,?,?,?,?)",
         ["2026-07-17 10:00:00", "visit", None, None, "v2"]),
    ])
    rows = s.query("SELECT COUNT(*) AS n FROM events WHERE type = ?", ["fetch"])
    assert rows[0]["n"] == 1


def test_raise_on_pipeline_errors_raises():
    results = [
        {"type": "ok", "response": {}},
        {"type": "error", "error": {"message": "no such table: events"}},
    ]
    with pytest.raises(RuntimeError, match="no such table: events"):
        _raise_on_pipeline_errors(results)


def test_raise_on_pipeline_errors_missing_message():
    with pytest.raises(RuntimeError, match="unknown Turso error"):
        _raise_on_pipeline_errors([{"type": "error"}])


def test_raise_on_pipeline_errors_success_no_raise():
    results = [{"type": "ok", "response": {}}, {"type": "ok", "response": {}}]
    _raise_on_pipeline_errors(results)
