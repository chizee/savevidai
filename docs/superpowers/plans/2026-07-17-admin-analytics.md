# Admin Analytics Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an owner-only `/admin` analytics dashboard showing aggregate, privacy-safe usage (visitors, fetches, downloads, qualities, countries, errors, traffic) backed by Turso, with zero personal data at rest.

**Architecture:** A new `app/analytics/` package: config/enablement gate, HMAC visitor hashing, PBKDF2 cookie auth, a pluggable SQL store (`SqliteStore` for tests/VPS, `TursoStore` over HTTP for Render), a bounded fire-and-forget event queue + background writer, and stats aggregation. A new `app/client_ip.py` fixes a live rate-limiter bug. The frontend gains a visit beacon, a download event, and a separate Vite `admin.html` entry so the public bundle is untouched.

**Tech Stack:** Python 3.12, FastAPI, slowapi, httpx, stdlib `sqlite3`/`hmac`/`hashlib`/`secrets`; TypeScript, React, Vite multi-page build, Vitest.

**Spec:** `docs/superpowers/specs/2026-07-17-admin-analytics-design.md` (read before starting).

## Global Constraints

- Analytics is fully OFF unless **all four** env vars are set: `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `ADMIN_PASSWORD`, `ANALYTICS_SALT`. When off: `/api/event` and `/api/admin/*` return 404, no recording occurs, self-hosters get the zero-config build.
- No raw IP is ever written, logged, or returned. Visitor id = `HMAC-SHA256(key=ANALYTICS_SALT, msg=f"{utc_date}|{ip}")`, hexdigest truncated to 16 chars.
- Event types: `visit` | `fetch` | `download`. Columns: `ts, type, outcome, country, visitor`. `ts` stored as `%Y-%m-%d %H:%M:%S` UTC (space-separated, no `T`/`Z`, so SQLite/libSQL `datetime()` parses it reliably).
- Client IP precedence: `CF-Connecting-IP`, else first hop of `X-Forwarded-For`, else `request.client.host`.
- `tz` query param: parsed as int, clamped/validated to [-840, 840], else HTTP 422. Frontend sends `-new Date().getTimezoneOffset()`.
- Rate limits: `/api/event` 30/min/IP; `/api/admin/login` 5/min/IP; existing `/api/resolve` stays 10/min/IP but keyed by the corrected client IP.
- Admin cookie: signed with a key derived `PBKDF2-HMAC-SHA256(ADMIN_PASSWORD, salt=fixed app pepper, iterations=100_000)`; flags `HttpOnly; Secure; SameSite=Strict; Path=/api/admin`; 30-day expiry embedded and verified.
- Analytics failure (Turso down, queue full) must never slow or break `/api/resolve`, `/api/proxy`, or page loads. Queue cap 1000, drop-oldest with a logged warning.
- Public page bundle, its routes, and Lighthouse score must be unchanged; admin UI ships as a separate Vite entry.
- Conventional commit prefixes. Backend commands from `backend/` with its venv active; frontend from `frontend/`.
- The known-benign pre-existing test warning is the starlette TestClient deprecation; any NEW warning is a finding.

---

### Task 1: Client IP resolution + rate-limiter fix + proxy headers

**Files:**
- Create: `backend/app/client_ip.py`, `backend/tests/test_client_ip.py`
- Modify: `backend/app/limits.py`, `backend/Dockerfile`, `scripts/dev.sh`

**Interfaces:**
- Produces: `client_ip(request: Request) -> str` in `app.client_ip`; `limiter` in `app.limits` now keyed by it.

- [ ] **Step 1: Write the failing test** (`backend/tests/test_client_ip.py`)

```python
from starlette.requests import Request

from app.client_ip import client_ip


def _req(headers: dict, client_host: str | None = "10.0.0.1") -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (client_host, 12345) if client_host else None,
    }
    return Request(scope)


def test_prefers_cf_connecting_ip():
    r = _req({"CF-Connecting-IP": "1.2.3.4", "X-Forwarded-For": "9.9.9.9"})
    assert client_ip(r) == "1.2.3.4"


def test_falls_back_to_first_xff_hop():
    r = _req({"X-Forwarded-For": "5.6.7.8, 10.0.0.1, 172.16.0.1"})
    assert client_ip(r) == "5.6.7.8"


def test_falls_back_to_client_host():
    r = _req({})
    assert client_ip(r) == "10.0.0.1"


def test_unknown_when_no_source():
    r = _req({}, client_host=None)
    assert client_ip(r) == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client_ip.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.client_ip'`

- [ ] **Step 3: Write the implementation** (`backend/app/client_ip.py`)

```python
from fastapi import Request


def client_ip(request: Request) -> str:
    """Real client IP behind the platform load balancer / Cloudflare.

    Precedence: CF-Connecting-IP, then the first hop of X-Forwarded-For, then
    the direct peer. Returns "unknown" if none are available.
    """
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
```

- [ ] **Step 4: Point the limiter at the corrected IP** (`backend/app/limits.py`)

```python
from slowapi import Limiter

from .client_ip import client_ip

limiter = Limiter(key_func=client_ip)
```

- [ ] **Step 5: Add proxy-header trust to the servers**

In `backend/Dockerfile`, change the CMD to:

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
```

In `scripts/dev.sh`, change the uvicorn line to:

```sh
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8000 --proxy-headers --forwarded-allow-ips '*' &
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_client_ip.py -v` then `python -m pytest -q`
Expected: client-ip tests pass (4); full suite still green (rate-limit tests use TestClient whose client host is "testclient", unaffected).

- [ ] **Step 7: Commit**

```bash
ruff check . && cd .. && git add -A && git commit -m "fix: resolve real client IP for rate limiting behind LB/Cloudflare" && cd backend
```

---

### Task 2: Analytics config and enablement gate

**Files:**
- Create: `backend/app/analytics/__init__.py` (empty), `backend/app/analytics/config.py`, `backend/tests/test_analytics_config.py`

**Interfaces:**
- Produces in `app.analytics.config`: `AnalyticsConfig` dataclass (`turso_url`, `turso_token`, `admin_password`, `salt`); `load_config(env: Mapping[str,str]) -> AnalyticsConfig | None` (returns None unless all four present and non-empty).

- [ ] **Step 1: Write the failing test** (`backend/tests/test_analytics_config.py`)

```python
from app.analytics.config import load_config

FULL = {
    "TURSO_DATABASE_URL": "libsql://db.turso.io",
    "TURSO_AUTH_TOKEN": "tok",
    "ADMIN_PASSWORD": "s3cret-long",
    "ANALYTICS_SALT": "random-salt",
}


def test_loads_when_all_present():
    cfg = load_config(FULL)
    assert cfg is not None
    assert cfg.admin_password == "s3cret-long"
    assert cfg.salt == "random-salt"


def test_none_when_any_missing():
    for k in FULL:
        partial = {kk: vv for kk, vv in FULL.items() if kk != k}
        assert load_config(partial) is None


def test_none_when_any_empty():
    for k in FULL:
        blanked = {**FULL, k: ""}
        assert load_config(blanked) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_analytics_config.py -v`
Expected: FAIL, module not found. (Create empty `backend/app/analytics/__init__.py` first.)

- [ ] **Step 3: Write the implementation** (`backend/app/analytics/config.py`)

```python
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class AnalyticsConfig:
    turso_url: str
    turso_token: str
    admin_password: str
    salt: str


def load_config(env: Mapping[str, str]) -> AnalyticsConfig | None:
    """Return config only when all four vars are present and non-empty, else None.

    The salt is part of the gate on purpose: an empty salt would make visitor
    hashes brute-forceable, silently breaking anonymity.
    """
    url = env.get("TURSO_DATABASE_URL", "").strip()
    token = env.get("TURSO_AUTH_TOKEN", "").strip()
    password = env.get("ADMIN_PASSWORD", "").strip()
    salt = env.get("ANALYTICS_SALT", "").strip()
    if not (url and token and password and salt):
        return None
    return AnalyticsConfig(turso_url=url, turso_token=token, admin_password=password, salt=salt)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_analytics_config.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
ruff check . && cd .. && git add -A && git commit -m "feat: analytics config with four-var enablement gate" && cd backend
```

---

### Task 3: Visitor hashing

**Files:**
- Create: `backend/app/analytics/hashing.py`, `backend/tests/test_hashing.py`

**Interfaces:**
- Produces: `visitor_hash(salt: str, ip: str, day: str) -> str` (16 hex chars) and `today_utc() -> str` (`%Y-%m-%d`) in `app.analytics.hashing`.

- [ ] **Step 1: Write the failing test** (`backend/tests/test_hashing.py`)

```python
from app.analytics.hashing import visitor_hash

SALT = "random-salt"


def test_len_and_hex():
    h = visitor_hash(SALT, "1.2.3.4", "2026-07-17")
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)


def test_stable_within_day():
    a = visitor_hash(SALT, "1.2.3.4", "2026-07-17")
    b = visitor_hash(SALT, "1.2.3.4", "2026-07-17")
    assert a == b


def test_rotates_across_days():
    a = visitor_hash(SALT, "1.2.3.4", "2026-07-17")
    b = visitor_hash(SALT, "1.2.3.4", "2026-07-18")
    assert a != b


def test_salt_changes_output():
    a = visitor_hash(SALT, "1.2.3.4", "2026-07-17")
    b = visitor_hash("other-salt", "1.2.3.4", "2026-07-17")
    assert a != b


def test_never_contains_ip():
    h = visitor_hash(SALT, "203.0.113.77", "2026-07-17")
    assert "203.0.113.77" not in h
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_hashing.py -v`
Expected: FAIL, module not found.

- [ ] **Step 3: Write the implementation** (`backend/app/analytics/hashing.py`)

```python
import hashlib
import hmac
from datetime import datetime, timezone


def today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def visitor_hash(salt: str, ip: str, day: str) -> str:
    """Daily-rotating anonymous visitor id. HMAC keyed by the secret salt so it
    is not brute-forceable; rotates at UTC midnight so it can't link across days.
    """
    mac = hmac.new(salt.encode(), f"{day}|{ip}".encode(), hashlib.sha256)
    return mac.hexdigest()[:16]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_hashing.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
ruff check . && cd .. && git add -A && git commit -m "feat: HMAC daily-rotating visitor hash" && cd backend
```

---

### Task 4: Admin auth (password + signed cookie)

**Files:**
- Create: `backend/app/analytics/auth.py`, `backend/tests/test_auth.py`

**Interfaces:**
- Produces in `app.analytics.auth`: `check_password(supplied: str, expected: str) -> bool`; `make_cookie(password: str, now: float, ttl_seconds: int = 2592000) -> str`; `verify_cookie(cookie: str, password: str, now: float) -> bool`.

- [ ] **Step 1: Write the failing test** (`backend/tests/test_auth.py`)

```python
from app.analytics.auth import check_password, make_cookie, verify_cookie

PW = "long-random-password"
NOW = 1_800_000_000.0


def test_check_password():
    assert check_password("long-random-password", PW) is True
    assert check_password("wrong", PW) is False


def test_cookie_roundtrip():
    c = make_cookie(PW, NOW)
    assert verify_cookie(c, PW, NOW + 10) is True


def test_cookie_expires():
    c = make_cookie(PW, NOW, ttl_seconds=100)
    assert verify_cookie(c, PW, NOW + 101) is False


def test_cookie_rejects_wrong_password():
    c = make_cookie(PW, NOW)
    assert verify_cookie(c, "changed-password", NOW + 10) is False


def test_cookie_rejects_tamper():
    c = make_cookie(PW, NOW)
    tampered = c[:-2] + ("aa" if not c.endswith("aa") else "bb")
    assert verify_cookie(tampered, PW, NOW + 10) is False


def test_cookie_rejects_garbage():
    assert verify_cookie("not-a-cookie", PW, NOW) is False
    assert verify_cookie("", PW, NOW) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_auth.py -v`
Expected: FAIL, module not found.

- [ ] **Step 3: Write the implementation** (`backend/app/analytics/auth.py`)

```python
import hashlib
import hmac

# Fixed application pepper (not a secret; raises the bar with the user password).
_PEPPER = b"savevidai::admin::v1"


def _key(password: str) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), _PEPPER, 100_000)


def check_password(supplied: str, expected: str) -> bool:
    return hmac.compare_digest(supplied.encode(), expected.encode())


def make_cookie(password: str, now: float, ttl_seconds: int = 2_592_000) -> str:
    """Cookie value = "<expiry>.<hex sig>" where sig signs the expiry with a key
    derived from the admin password. Changing the password invalidates all cookies.
    """
    expiry = str(int(now) + ttl_seconds)
    sig = hmac.new(_key(password), expiry.encode(), hashlib.sha256).hexdigest()
    return f"{expiry}.{sig}"


def verify_cookie(cookie: str, password: str, now: float) -> bool:
    if not cookie or "." not in cookie:
        return False
    expiry, _, sig = cookie.partition(".")
    expected = hmac.new(_key(password), expiry.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        return int(expiry) > int(now)
    except ValueError:
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_auth.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
ruff check . && cd .. && git add -A && git commit -m "feat: admin password check and signed session cookie" && cd backend
```

---

### Task 5: Store layer (SqliteStore for tests/VPS, TursoStore for Render)

**Files:**
- Create: `backend/app/analytics/store.py`, `backend/tests/test_store.py`

**Interfaces:**
- Produces in `app.analytics.store`: `Store` protocol with `init_schema() -> None`, `execute_many(statements: list[tuple[str, list]]) -> None`, `query(sql: str, args: list) -> list[dict]`; `SqliteStore(path: str = ":memory:")`; `TursoStore(url: str, token: str)`; `make_store(cfg) -> Store` (Turso from config). `SCHEMA: list[str]`.

- [ ] **Step 1: Write the failing test** (`backend/tests/test_store.py`)

```python
from app.analytics.store import SqliteStore


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL, module not found.

- [ ] **Step 3: Write the implementation** (`backend/app/analytics/store.py`)

```python
import sqlite3
import threading
from typing import Any, Protocol

import httpx

SCHEMA: list[str] = [
    """CREATE TABLE IF NOT EXISTS events (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        ts      TEXT NOT NULL,
        type    TEXT NOT NULL,
        outcome TEXT,
        country TEXT,
        visitor TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)",
    "CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(type, ts)",
]


class Store(Protocol):
    def init_schema(self) -> None: ...
    def execute_many(self, statements: list[tuple[str, list]]) -> None: ...
    def query(self, sql: str, args: list) -> list[dict]: ...


class SqliteStore:
    """Local/VPS and test backend. Thread-safe via a single lock (writer thread
    plus request threads share one connection)."""

    def __init__(self, path: str = ":memory:"):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()

    def init_schema(self) -> None:
        with self._lock:
            for stmt in SCHEMA:
                self._conn.execute(stmt)
            self._conn.commit()

    def execute_many(self, statements: list[tuple[str, list]]) -> None:
        with self._lock:
            for sql, args in statements:
                self._conn.execute(sql, args)
            self._conn.commit()

    def query(self, sql: str, args: list) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(sql, args)
            return [dict(row) for row in cur.fetchall()]


def _turso_arg(value: Any) -> dict:
    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    return {"type": "text", "value": str(value)}


class TursoStore:
    """Render backend. Talks to Turso's libSQL HTTP pipeline API."""

    def __init__(self, url: str, token: str):
        # libsql:// -> https:// for the HTTP endpoint
        self._endpoint = url.replace("libsql://", "https://").rstrip("/") + "/v2/pipeline"
        self._headers = {"Authorization": f"Bearer {token}"}

    def _pipeline(self, stmts: list[tuple[str, list]]) -> list[dict]:
        requests = [
            {"type": "execute", "stmt": {"sql": sql, "args": [_turso_arg(a) for a in args]}}
            for sql, args in stmts
        ]
        requests.append({"type": "close"})
        resp = httpx.post(self._endpoint, headers=self._headers,
                          json={"requests": requests}, timeout=15.0)
        resp.raise_for_status()
        return resp.json()["results"]

    def init_schema(self) -> None:
        self._pipeline([(stmt, []) for stmt in SCHEMA])

    def execute_many(self, statements: list[tuple[str, list]]) -> None:
        self._pipeline(statements)

    def query(self, sql: str, args: list) -> list[dict]:
        results = self._pipeline([(sql, args)])
        result = results[0]["response"]["result"]
        cols = [c["name"] for c in result["cols"]]
        out: list[dict] = []
        for row in result["rows"]:
            values = [None if cell["type"] == "null" else cell["value"] for cell in row]
            typed = []
            for cell, val in zip(row, values):
                if val is not None and cell["type"] == "integer":
                    typed.append(int(val))
                else:
                    typed.append(val)
            out.append(dict(zip(cols, typed)))
        return out


def make_store(cfg) -> Store:
    return TursoStore(cfg.turso_url, cfg.turso_token)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_store.py -v`
Expected: 2 passed. (TursoStore is exercised in production; unit tests use SqliteStore with the identical SQL dialect per the spec.)

- [ ] **Step 5: Commit**

```bash
ruff check . && cd .. && git add -A && git commit -m "feat: analytics store (sqlite + turso http), shared schema" && cd backend
```

---

### Task 6: Event recorder (bounded queue + background writer)

**Files:**
- Create: `backend/app/analytics/recorder.py`, `backend/tests/test_recorder.py`

**Interfaces:**
- Consumes: `Store` from `app.analytics.store`.
- Produces in `app.analytics.recorder`: `Recorder(store, max_queue=1000, batch_interval=5.0, prune_days=90)` with `.record(type: str, visitor: str, outcome: str | None = None, country: str | None = None) -> None`, `.flush() -> int` (drains and writes queued events synchronously, returns count written), `.prune() -> None` (deletes events older than `prune_days`), `.start()`, `.stop()`. `.dropped` counter.

- [ ] **Step 1: Write the failing test** (`backend/tests/test_recorder.py`)

```python
from app.analytics.recorder import Recorder
from app.analytics.store import SqliteStore


def _store():
    s = SqliteStore(":memory:")
    s.init_schema()
    return s


def test_record_then_flush_writes_rows():
    s = _store()
    rec = Recorder(s)
    rec.record("fetch", visitor="v1", outcome="ok", country="BD")
    rec.record("visit", visitor="v2")
    written = rec.flush()
    assert written == 2
    rows = s.query("SELECT type, visitor, outcome, country FROM events ORDER BY id", [])
    assert rows[0]["type"] == "fetch" and rows[0]["country"] == "BD"
    assert rows[1]["type"] == "visit" and rows[1]["outcome"] is None


def test_drops_oldest_when_full():
    s = _store()
    rec = Recorder(s, max_queue=3)
    for i in range(5):
        rec.record("visit", visitor=f"v{i}")
    assert rec.dropped == 2
    written = rec.flush()
    assert written == 3
    rows = s.query("SELECT visitor FROM events ORDER BY id", [])
    # oldest two (v0, v1) dropped; v2..v4 kept
    assert [r["visitor"] for r in rows] == ["v2", "v3", "v4"]


def test_flush_empty_is_zero():
    rec = Recorder(_store())
    assert rec.flush() == 0


def test_prune_removes_old_events():
    s = _store()
    s.execute_many([
        ("INSERT INTO events (ts,type,outcome,country,visitor) VALUES (?,?,?,?,?)",
         ["2000-01-01 00:00:00", "visit", None, None, "old"]),
        ("INSERT INTO events (ts,type,outcome,country,visitor) VALUES (?,?,?,?,?)",
         [__import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
          "visit", None, None, "new"]),
    ])
    Recorder(s, prune_days=90).prune()
    rows = s.query("SELECT visitor FROM events", [])
    assert [r["visitor"] for r in rows] == ["new"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_recorder.py -v`
Expected: FAIL, module not found.

- [ ] **Step 3: Write the implementation** (`backend/app/analytics/recorder.py`)

```python
import logging
import threading
from collections import deque
from datetime import datetime, timezone

from .store import Store

logger = logging.getLogger("savevidai.analytics")

_INSERT = "INSERT INTO events (ts, type, outcome, country, visitor) VALUES (?,?,?,?,?)"


class Recorder:
    """Fire-and-forget event recording. record() never blocks on I/O; a background
    thread batches inserts. If the queue is full, the oldest event is dropped."""

    def __init__(self, store: Store, max_queue: int = 1000, batch_interval: float = 5.0,
                 prune_days: int = 90):
        self._store = store
        self._max = max_queue
        self._interval = batch_interval
        self._prune_days = prune_days
        self._q: deque[tuple] = deque()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cycles = 0
        self.dropped = 0

    def record(self, type: str, visitor: str, outcome: str | None = None,
               country: str | None = None) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            if len(self._q) >= self._max:
                self._q.popleft()
                self.dropped += 1
                logger.warning("analytics queue full, dropped oldest event")
            self._q.append((ts, type, outcome, country, visitor))

    def flush(self) -> int:
        with self._lock:
            batch = list(self._q)
            self._q.clear()
        if not batch:
            return 0
        try:
            self._store.execute_many([(_INSERT, list(row)) for row in batch])
        except Exception as exc:  # store/network failure must not propagate
            logger.warning("analytics flush failed, %d events lost: %r", len(batch), exc)
            return 0
        return len(batch)

    def prune(self) -> None:
        try:
            self._store.execute_many(
                [("DELETE FROM events WHERE ts < datetime('now', ?)", [f"-{self._prune_days} days"])]
            )
        except Exception as exc:
            logger.warning("analytics prune failed: %r", exc)

    def _loop(self) -> None:
        # Flush every interval; prune roughly hourly (720 * 5s).
        while not self._stop.wait(self._interval):
            self.flush()
            self._cycles += 1
            if self._cycles % 720 == 0:
                self.prune()

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.flush()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_recorder.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
ruff check . && cd .. && git add -A && git commit -m "feat: fire-and-forget event recorder with bounded queue" && cd backend
```

---

### Task 7: Stats aggregation + tz validation

**Files:**
- Create: `backend/app/analytics/stats.py`, `backend/tests/test_stats.py`

**Interfaces:**
- Consumes: `Store`.
- Produces in `app.analytics.stats`: `parse_tz(raw: str | int | None) -> int` (raises `ValueError` outside [-840,840] or non-int); `compute_stats(store: Store, days: int, tz: int) -> dict`.

- [ ] **Step 1: Write the failing test** (`backend/tests/test_stats.py`)

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stats.py -v`
Expected: FAIL, module not found.

- [ ] **Step 3: Write the implementation** (`backend/app/analytics/stats.py`)

```python
from .store import Store

_MAX_TZ = 840  # +/- 14 hours


def parse_tz(raw) -> int:
    """Validate the timezone offset (minutes east of UTC). Must be an integer in
    [-840, 840]; anything else raises ValueError (guards the SQL modifier)."""
    if raw is None or raw == "":
        raise ValueError("tz required")
    try:
        tz = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("tz must be an integer") from exc
    if tz < -_MAX_TZ or tz > _MAX_TZ:
        raise ValueError("tz out of range")
    return tz


def _local(tz: int) -> str:
    # tz is a validated int, safe to inline into the SQLite datetime modifier.
    sign = "+" if tz >= 0 else "-"
    return f"datetime(ts, '{sign}{abs(tz)} minutes')"


def _count_since(store: Store, where: str, args: list) -> int:
    rows = store.query(f"SELECT COUNT(*) AS n FROM events WHERE {where}", args)
    return rows[0]["n"] if rows else 0


def _period(store: Store, type_: str, tz: int) -> dict:
    local = _local(tz)
    day = f"date({local}) = date(datetime('now','+{tz} minutes'))" if tz >= 0 \
        else f"date({local}) = date(datetime('now','-{abs(tz)} minutes'))"
    return {
        "today": _count_since(store, f"type=? AND {day}", [type_]),
        "d7": _count_since(store, "type=? AND ts >= datetime('now','-7 days')", [type_]),
        "d30": _count_since(store, "type=? AND ts >= datetime('now','-30 days')", [type_]),
        "all_time": _count_since(store, "type=?", [type_]),
    }


def compute_stats(store: Store, days: int, tz: int) -> dict:
    local = _local(tz)
    window = f"ts >= datetime('now','-{int(days)} days')"

    fetches = _period(store, "fetch", tz)
    downloads = _period(store, "download", tz)
    visits = _period(store, "visit", tz)

    uniq_today = store.query(
        f"SELECT COUNT(DISTINCT visitor) AS n FROM events "
        f"WHERE date({local}) = date(datetime('now','{'+' if tz>=0 else '-'}{abs(tz)} minutes'))",
        [],
    )[0]["n"]

    ok = _count_since(store, f"type='fetch' AND outcome='ok' AND {window}", [])
    total_fetch = _count_since(store, f"type='fetch' AND {window}", [])
    success_rate = (ok / total_fetch) if total_fetch else 0.0

    # conversion: sum of daily-distinct fetching visitors / sum of daily-distinct visitors
    visitor_days = store.query(
        f"SELECT COUNT(*) AS n FROM (SELECT DISTINCT date({local}) d, visitor "
        f"FROM events WHERE {window})", [],
    )[0]["n"]
    fetch_visitor_days = store.query(
        f"SELECT COUNT(*) AS n FROM (SELECT DISTINCT date({local}) d, visitor "
        f"FROM events WHERE type='fetch' AND {window})", [],
    )[0]["n"]
    conversion = (fetch_visitor_days / visitor_days) if visitor_days else 0.0

    active_now = store.query(
        "SELECT COUNT(DISTINCT visitor) AS n FROM events WHERE ts >= datetime('now','-5 minutes')",
        [],
    )[0]["n"]

    series_rows = store.query(
        f"SELECT date({local}) AS day, type, COUNT(*) AS n FROM events "
        f"WHERE {window} GROUP BY day, type ORDER BY day", [],
    )
    uniq_rows = store.query(
        f"SELECT date({local}) AS day, COUNT(DISTINCT visitor) AS n FROM events "
        f"WHERE {window} GROUP BY day ORDER BY day", [],
    )
    series: dict[str, dict] = {}
    for r in series_rows:
        series.setdefault(r["day"], {"day": r["day"], "fetch": 0, "download": 0, "visit": 0, "uniques": 0})
        series[r["day"]][r["type"]] = r["n"]
    for r in uniq_rows:
        series.setdefault(r["day"], {"day": r["day"], "fetch": 0, "download": 0, "visit": 0, "uniques": 0})
        series[r["day"]]["uniques"] = r["n"]

    countries = store.query(
        f"SELECT COALESCE(country,'unknown') AS country, COUNT(*) AS count FROM events "
        f"WHERE {window} GROUP BY country ORDER BY count DESC LIMIT 11", [],
    )
    qualities = store.query(
        f"SELECT outcome AS quality, COUNT(*) AS count FROM events "
        f"WHERE type='download' AND {window} GROUP BY outcome ORDER BY count DESC", [],
    )
    errors = store.query(
        f"SELECT outcome AS code, COUNT(*) AS count FROM events "
        f"WHERE type='fetch' AND outcome != 'ok' AND {window} GROUP BY outcome ORDER BY count DESC", [],
    )
    hours = store.query(
        f"SELECT CAST(strftime('%H', {local}) AS INTEGER) AS hour, COUNT(*) AS count "
        f"FROM events WHERE {window} GROUP BY hour ORDER BY hour", [],
    )

    return {
        "totals": {
            "fetches": fetches,
            "downloads": downloads,
            "visits": visits,
            "unique_today": uniq_today,
            "success_rate": round(success_rate, 3),
            "conversion": round(conversion, 3),
        },
        "active_now": active_now,
        "series": sorted(series.values(), key=lambda r: r["day"]),
        "countries": countries,
        "qualities": qualities,
        "errors": errors,
        "hours": hours,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_stats.py -v`
Expected: parse_tz tests + shape test pass.

- [ ] **Step 5: Commit**

```bash
ruff check . && cd .. && git add -A && git commit -m "feat: stats aggregation with validated tz bucketing" && cd backend
```

---

### Task 8: Wire routes + fetch recording into the app

**Files:**
- Create: `backend/app/analytics/service.py`, `backend/app/analytics/router.py`, `backend/tests/test_analytics_api.py`
- Modify: `backend/app/main.py`, `backend/app/resolve.py`

**Interfaces:**
- Consumes: all analytics modules, `client_ip`, `limiter`.
- Produces in `app.analytics.service`: module-level `service` holder with `init(cfg, store, recorder)`, `enabled: bool`, `record_fetch(request, outcome)`, `record_from_request(request, type, outcome)`; `get_service()`.
- Produces in `app.analytics.router`: `router` with `POST /api/event`, `POST /api/admin/login`, `GET /api/admin/stats`, `GET /admin`.

- [ ] **Step 1: Write the service holder** (`backend/app/analytics/service.py`)

```python
from fastapi import Request

from ..client_ip import client_ip
from .config import AnalyticsConfig
from .hashing import today_utc, visitor_hash
from .recorder import Recorder
from .store import Store


class AnalyticsService:
    def __init__(self) -> None:
        self.enabled = False
        self._cfg: AnalyticsConfig | None = None
        self._recorder: Recorder | None = None

    def init(self, cfg: AnalyticsConfig, store: Store, recorder: Recorder) -> None:
        store.init_schema()
        recorder.start()
        self._cfg = cfg
        self._recorder = recorder
        self.enabled = True

    def _visitor(self, request: Request) -> str:
        return visitor_hash(self._cfg.salt, client_ip(request), today_utc())

    def record_from_request(self, request: Request, type: str, outcome: str | None) -> None:
        if not self.enabled:
            return
        country = request.headers.get("cf-ipcountry") or None
        if country in ("XX", "T1"):  # Cloudflare's unknown/Tor placeholders
            country = None
        self._recorder.record(type, visitor=self._visitor(request), outcome=outcome, country=country)

    def config(self) -> AnalyticsConfig | None:
        return self._cfg

    def recorder(self) -> Recorder | None:
        return self._recorder


service = AnalyticsService()


def get_service() -> AnalyticsService:
    return service
```

- [ ] **Step 2: Write the failing API test** (`backend/tests/test_analytics_api.py`)

```python
import pytest
from fastapi.testclient import TestClient

from app.analytics import service as service_mod
from app.analytics.config import AnalyticsConfig
from app.analytics.recorder import Recorder
from app.analytics.store import SqliteStore
from app.main import create_app


@pytest.fixture()
def enabled_client(monkeypatch):
    store = SqliteStore(":memory:")
    rec = Recorder(store, batch_interval=0.05)
    cfg = AnalyticsConfig("libsql://x", "t", "pw-long", "salt")
    svc = service_mod.AnalyticsService()
    svc.init(cfg, store, rec)
    monkeypatch.setattr(service_mod, "service", svc)
    monkeypatch.setattr("app.analytics.router.service", svc)
    monkeypatch.setattr("app.resolve.analytics", svc, raising=False)
    return TestClient(create_app(), raise_server_exceptions=False), svc, store


def test_event_records_download(enabled_client):
    client, svc, store = enabled_client
    r = client.post("/api/event", json={"type": "download", "quality": "1080p"})
    assert r.status_code == 204
    svc.recorder().flush()
    rows = store.query("SELECT type, outcome FROM events", [])
    assert rows == [{"type": "download", "outcome": "1080p"}]


def test_event_rejects_bad_type(enabled_client):
    client, *_ = enabled_client
    assert client.post("/api/event", json={"type": "hack"}).status_code == 422


def test_event_rejects_bad_quality(enabled_client):
    client, *_ = enabled_client
    assert client.post("/api/event", json={"type": "download", "quality": "; DROP"}).status_code == 422


def test_login_and_stats_gate(enabled_client):
    client, *_ = enabled_client
    # no cookie -> 401
    assert client.get("/api/admin/stats?days=30&tz=360").status_code == 401
    # wrong pw -> 401
    assert client.post("/api/admin/login", json={"password": "nope"}).status_code == 401
    # right pw -> 200 + cookie
    ok = client.post("/api/admin/login", json={"password": "pw-long"})
    assert ok.status_code == 204
    # cookie now present on the client -> stats 200
    s = client.get("/api/admin/stats?days=30&tz=360")
    assert s.status_code == 200
    assert "totals" in s.json()


def test_stats_bad_tz(enabled_client):
    client, *_ = enabled_client
    client.post("/api/admin/login", json={"password": "pw-long"})
    assert client.get("/api/admin/stats?days=30&tz=abc").status_code == 422


def test_disabled_returns_404(monkeypatch):
    svc = service_mod.AnalyticsService()  # never init()'d -> disabled
    monkeypatch.setattr(service_mod, "service", svc)
    monkeypatch.setattr("app.analytics.router.service", svc)
    client = TestClient(create_app(), raise_server_exceptions=False)
    assert client.post("/api/event", json={"type": "visit"}).status_code == 404
    assert client.get("/api/admin/stats?days=30&tz=0").status_code == 404
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_analytics_api.py -v`
Expected: FAIL, `app.analytics.router` not found.

- [ ] **Step 4: Write the router** (`backend/app/analytics/router.py`)

```python
import os
import re
import time

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, field_validator

from ..limits import limiter
from .auth import check_password, make_cookie, verify_cookie
from .service import service
from .stats import compute_stats, parse_tz

router = APIRouter()

_QUALITY_OK = re.compile(r"^\d{2,4}p$|^video$")
COOKIE = "svid_admin"


class EventIn(BaseModel):
    type: str
    quality: str | None = None

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v not in ("visit", "download"):
            raise ValueError("bad type")
        return v

    @field_validator("quality")
    @classmethod
    def _quality(cls, v):
        if v is not None and not _QUALITY_OK.match(v):
            raise ValueError("bad quality")
        return v


class LoginIn(BaseModel):
    password: str


def _require_enabled() -> None:
    if not service.enabled:
        raise HTTPException(status_code=404)


@router.post("/api/event", status_code=204)
@limiter.limit("30/minute")
def event(request: Request, payload: EventIn) -> Response:
    _require_enabled()
    outcome = payload.quality if payload.type == "download" else None
    service.record_from_request(request, payload.type, outcome)
    return Response(status_code=204)


@router.post("/api/admin/login", status_code=204)
@limiter.limit("5/minute")
def login(request: Request, payload: LoginIn) -> Response:
    _require_enabled()
    cfg = service.config()
    if not check_password(payload.password, cfg.admin_password):
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    resp = Response(status_code=204)
    resp.set_cookie(
        COOKIE, make_cookie(cfg.admin_password, time.time()),
        max_age=2_592_000, httponly=True, secure=True, samesite="strict", path="/api/admin",
    )
    return resp


@router.get("/api/admin/stats")
def stats(request: Request, days: int = 30, tz: str = "0") -> JSONResponse:
    _require_enabled()
    cfg = service.config()
    cookie = request.cookies.get(COOKIE, "")
    if not verify_cookie(cookie, cfg.admin_password, time.time()):
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    try:
        tz_min = parse_tz(tz)
    except ValueError:
        return JSONResponse(status_code=422, content={"error": "bad_tz"})
    days = max(1, min(int(days), 365))
    store = service.recorder()._store
    try:
        return JSONResponse(compute_stats(store, days, tz_min))
    except Exception:
        return JSONResponse(status_code=503, content={"error": "analytics_unavailable"})


@router.get("/admin")
def admin_page() -> FileResponse:
    static_dir = os.environ.get("STATIC_DIR", "")
    path = os.path.join(static_dir, "admin.html")
    if static_dir and os.path.isfile(path):
        return FileResponse(path)
    raise HTTPException(status_code=404)
```

- [ ] **Step 5: Wire into resolve.py** (record every fetch outcome)

Replace `backend/app/resolve.py` body with fetch recording (uses a module-level `analytics` referencing the service, monkeypatchable in tests):

```python
from fastapi import APIRouter, Request

from .analytics.service import service as analytics
from .cache import TTLCache
from .errors import INVALID_URL, AppError, app_error
from .extractor import extract
from .limits import limiter
from .schemas import ResolveRequest, ResolveResponse
from .sizes import fill_sizes
from .urls import InvalidTweetURL, parse_tweet_url

router = APIRouter()
cache = TTLCache(maxsize=512, ttl=3600.0)


@router.post("/api/resolve", response_model=ResolveResponse)
@limiter.limit("10/minute")
def resolve(request: Request, payload: ResolveRequest) -> ResolveResponse:
    try:
        tweet_id = parse_tweet_url(payload.url)
    except InvalidTweetURL as exc:
        analytics.record_from_request(request, "fetch", "invalid_url")
        raise app_error(INVALID_URL) from exc
    try:
        cached = cache.get(tweet_id)
        if cached is not None:
            analytics.record_from_request(request, "fetch", "ok")
            return cached
        result = extract(tweet_id)
        fill_sizes(result)
        cache.set(tweet_id, result)
    except AppError as exc:
        analytics.record_from_request(request, "fetch", exc.code)
        raise
    analytics.record_from_request(request, "fetch", "ok")
    return result
```

- [ ] **Step 6: Wire startup + router into main.py**

In `backend/app/main.py`, after the existing imports add:

```python
from .analytics import service as analytics_service
from .analytics.config import load_config
from .analytics.recorder import Recorder
from .analytics.router import router as analytics_router
from .analytics.store import make_store
```

Inside `create_app()`, before the static mount, add:

```python
    cfg = load_config(os.environ)
    if cfg is not None:
        store = make_store(cfg)
        analytics_service.service.init(cfg, store, Recorder(store))
    app.include_router(analytics_router)
```

(The router's endpoints self-gate via `_require_enabled()`, so including it unconditionally is safe.)

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_analytics_api.py -v` then `python -m pytest -q`
Expected: analytics API tests pass; full suite green. Note: `test_analytics_api` monkeypatches the service singleton and `app.resolve.analytics`.

- [ ] **Step 8: Commit**

```bash
ruff check . && cd .. && git add -A && git commit -m "feat: analytics routes, fetch recording, app wiring" && cd backend
```

---

### Task 9: Frontend event beacons

**Files:**
- Create: `frontend/src/lib/analytics.ts`, `frontend/src/lib/analytics.test.ts`
- Modify: `frontend/src/App.tsx` (visit beacon on load), `frontend/src/components/QualityButton.tsx` (download beacon on start)

**Interfaces:**
- Produces in `lib/analytics.ts`: `sendEvent(type: "visit" | "download", quality?: string): void` (fire-and-forget, never throws, uses `navigator.sendBeacon` when available else `fetch` keepalive).

- [ ] **Step 1: Write the failing test** (`frontend/src/lib/analytics.test.ts`)

```ts
import { afterEach, expect, test, vi } from "vitest";
import { sendEvent } from "./analytics";

afterEach(() => vi.unstubAllGlobals());

test("posts a visit event via fetch when sendBeacon is absent", async () => {
  const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("navigator", {});
  sendEvent("visit");
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect(url).toBe("/api/event");
  expect(JSON.parse(String(init.body))).toEqual({ type: "visit" });
});

test("includes quality for downloads and never throws on failure", () => {
  vi.stubGlobal("navigator", {});
  vi.stubGlobal("fetch", vi.fn(() => { throw new Error("network"); }));
  expect(() => sendEvent("download", "1080p")).not.toThrow();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --run src/lib/analytics.test.ts`
Expected: FAIL, cannot resolve `./analytics`.

- [ ] **Step 3: Write the implementation** (`frontend/src/lib/analytics.ts`)

```ts
type EventType = "visit" | "download";

/** Fire-and-forget analytics beacon. No personal data, never throws, never blocks. */
export function sendEvent(type: EventType, quality?: string): void {
  const body = JSON.stringify(quality ? { type, quality } : { type });
  try {
    if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
      navigator.sendBeacon("/api/event", new Blob([body], { type: "application/json" }));
      return;
    }
    void fetch("/api/event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    }).catch(() => {});
  } catch {
    // analytics must never affect the user
  }
}
```

- [ ] **Step 4: Fire the visit beacon on load** (`frontend/src/App.tsx`)

Add the import near the other lib imports:

```tsx
import { sendEvent } from "./lib/analytics";
```

Add this effect inside `App()`, next to the other `useEffect`s:

```tsx
  // Anonymous visit beacon, once per load.
  useEffect(() => {
    sendEvent("visit");
  }, []);
```

- [ ] **Step 5: Fire the download beacon** (`frontend/src/components/QualityButton.tsx`)

Add the import:

```tsx
import { sendEvent } from "../lib/analytics";
```

In `start()`, immediately after `setPhase({ name: "downloading", ... })` and before `await downloadVariant(...)`, add:

```tsx
    sendEvent("download", variant.label);
```

- [ ] **Step 6: Run tests + build**

Run: `npm test -- --run` then `npm run build`
Expected: all tests pass (including the 2 new); build clean.

- [ ] **Step 7: Commit**

```bash
cd .. && git add -A && git commit -m "feat: anonymous visit and download beacons" && cd frontend
```

---

### Task 10: Admin dashboard UI

**Files:**
- Create: `frontend/admin.html`, `frontend/src/admin/main.tsx`, `frontend/src/admin/Admin.tsx`, `frontend/src/admin/api.ts`, `frontend/src/admin/Admin.test.tsx`
- Modify: `frontend/vite.config.ts` (multi-page input)

**Interfaces:**
- Consumes: design tokens from `src/styles/index.css` (imported by the admin entry).
- Produces: `/admin.html` entry building to `dist/admin.html`; served at `/admin` in prod by the Task 8 route.

- [ ] **Step 1: Add the multi-page build input** (`frontend/vite.config.ts`)

```ts
import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/api": "http://localhost:8000" } },
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, "index.html"),
        admin: resolve(__dirname, "admin.html"),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    css: false,
  },
});
```

- [ ] **Step 2: Write admin.html**

```html
<!doctype html>
<html lang="en" class="dark">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="robots" content="noindex, nofollow" />
    <title>SaveVid AI - Admin</title>
    <script>
      try { if (localStorage.theme === "light") document.documentElement.classList.remove("dark"); } catch (e) {}
    </script>
  </head>
  <body class="font-sans">
    <div id="admin-root"></div>
    <script type="module" src="/src/admin/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 3: Write the admin API client** (`frontend/src/admin/api.ts`)

```ts
export type Stats = {
  totals: {
    fetches: Period; downloads: Period; visits: Period;
    unique_today: number; success_rate: number; conversion: number;
  };
  active_now: number;
  series: Array<{ day: string; fetch: number; download: number; visit: number; uniques: number }>;
  countries: Array<{ country: string; count: number }>;
  qualities: Array<{ quality: string; count: number }>;
  errors: Array<{ code: string; count: number }>;
  hours: Array<{ hour: number; count: number }>;
};
type Period = { today: number; d7: number; d30: number; all_time: number };

export async function login(password: string): Promise<boolean> {
  const r = await fetch("/api/admin/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  return r.status === 204;
}

export async function fetchStats(days = 30): Promise<Stats | "unauthorized" | "error"> {
  const tz = -new Date().getTimezoneOffset();
  const r = await fetch(`/api/admin/stats?days=${days}&tz=${tz}`);
  if (r.status === 401) return "unauthorized";
  if (!r.ok) return "error";
  return (await r.json()) as Stats;
}
```

- [ ] **Step 4: Write the failing test** (`frontend/src/admin/Admin.test.tsx`)

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { Admin } from "./Admin";

afterEach(() => vi.unstubAllGlobals());

const STATS = {
  totals: {
    fetches: { today: 5, d7: 20, d30: 50, all_time: 100 },
    downloads: { today: 3, d7: 12, d30: 30, all_time: 60 },
    visits: { today: 8, d7: 40, d30: 90, all_time: 200 },
    unique_today: 7, success_rate: 0.9, conversion: 0.5,
  },
  active_now: 2, series: [], countries: [{ country: "BD", count: 40 }],
  qualities: [{ quality: "1080p", count: 30 }], errors: [{ code: "no_video", count: 4 }],
  hours: [],
};

test("shows login first, then dashboard after auth", async () => {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).includes("/login")) return new Response(null, { status: 204 });
    return new Response(JSON.stringify(STATS), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<Admin />);
  expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText(/password/i), "pw");
  await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
  expect(await screen.findByText(/active now/i)).toBeInTheDocument();
  expect(screen.getByText("2")).toBeInTheDocument(); // active_now
});

test("wrong password shows an error and no dashboard", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 401 })));
  render(<Admin />);
  await userEvent.type(screen.getByLabelText(/password/i), "bad");
  await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.queryByText(/active now/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 5: Run test to verify it fails**

Run: `npm test -- --run src/admin/Admin.test.tsx`
Expected: FAIL, cannot resolve `./Admin`.

- [ ] **Step 6: Write the admin components** (`frontend/src/admin/Admin.tsx`)

```tsx
import { useEffect, useState } from "react";
import { fetchStats, login, type Stats } from "./api";

export function Admin() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [needsLogin, setNeedsLogin] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);

  async function load() {
    const r = await fetchStats();
    if (r === "unauthorized") setNeedsLogin(true);
    else if (r === "error") setError(true);
    else { setStats(r); setNeedsLogin(false); }
  }

  useEffect(() => { void load(); }, []);
  useEffect(() => {
    if (!stats) return;
    const t = setInterval(() => void load(), 60_000);
    return () => clearInterval(t);
  }, [stats]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(false);
    if (await login(password)) { setPassword(""); await load(); }
    else setError(true);
  }

  if (stats) return <Dashboard stats={stats} />;

  if (needsLogin || error) {
    return (
      <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-4">
        <h1 className="text-2xl font-semibold tracking-tight">SaveVid AI admin</h1>
        <form onSubmit={onSubmit} className="mt-6">
          <input
            type="password" aria-label="Password" value={password}
            onChange={(e) => setPassword(e.target.value)} placeholder="Password"
            className={`cta-input w-full ${error ? "animate-shake" : ""}`}
          />
          <button type="submit" className="btn mt-3 w-full">Sign in</button>
          {error && <p role="alert" className="error-glow mt-3 text-sm text-[#ff453a]">Wrong password.</p>}
        </form>
      </main>
    );
  }
  return <main className="p-8 text-[var(--muted)]">Loading…</main>;
}

function Tile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="panel p-4">
      <p className="text-sm text-[var(--muted)]">{label}</p>
      <p className="mt-1 font-mono text-2xl font-semibold">{value}</p>
    </div>
  );
}

function BarList({ title, rows }: { title: string; rows: Array<{ label: string; count: number }> }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <div className="panel p-4">
      <h2 className="font-semibold">{title}</h2>
      <div className="mt-3 space-y-2">
        {rows.length === 0 && <p className="text-sm text-[var(--muted)]">No data yet.</p>}
        {rows.map((r) => (
          <div key={r.label} className="flex items-center gap-3">
            <span className="w-24 shrink-0 truncate font-mono text-sm">{r.label}</span>
            <span className="h-2 rounded-full bg-[var(--accent)]" style={{ width: `${(r.count / max) * 100}%` }} />
            <span className="font-mono text-xs text-[var(--muted)]">{r.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Dashboard({ stats }: { stats: Stats }) {
  const t = stats.totals;
  return (
    <main className="mx-auto max-w-4xl px-4 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">SaveVid AI analytics</h1>
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Tile label="Active now" value={stats.active_now} />
        <Tile label="Unique today" value={t.unique_today} />
        <Tile label="Fetches (30d)" value={t.fetches.d30} />
        <Tile label="Downloads (30d)" value={t.downloads.d30} />
        <Tile label="Visits (30d)" value={t.visits.d30} />
        <Tile label="Fetches (all)" value={t.fetches.all_time} />
        <Tile label="Success rate" value={`${Math.round(t.success_rate * 100)}%`} />
        <Tile label="Conversion" value={`${Math.round(t.conversion * 100)}%`} />
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <BarList title="Top countries" rows={stats.countries.map((c) => ({ label: c.country, count: c.count }))} />
        <BarList title="Qualities" rows={stats.qualities.map((q) => ({ label: q.quality, count: q.count }))} />
        <BarList title="Errors (FixTweet health)" rows={stats.errors.map((e) => ({ label: e.code, count: e.count }))} />
        <BarList title="Busiest hours" rows={stats.hours.map((h) => ({ label: `${h.hour}:00`, count: h.count }))} />
      </div>
      <p className="mt-6 text-xs text-[var(--faint)]">Daily-unique basis · your local time · refreshes every 60s</p>
    </main>
  );
}
```

- [ ] **Step 7: Write the admin entry** (`frontend/src/admin/main.tsx`)

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Admin } from "./Admin";
import "../styles/index.css";

createRoot(document.getElementById("admin-root")!).render(
  <StrictMode>
    <Admin />
  </StrictMode>,
);
```

- [ ] **Step 8: Run tests + build**

Run: `npm test -- --run` then `npm run build`
Expected: all tests pass; build emits both `dist/index.html` and `dist/admin.html`.

- [ ] **Step 9: Commit**

```bash
cd .. && git add -A && git commit -m "feat: admin analytics dashboard UI (separate vite entry)" && cd frontend
```

---

### Task 11: Docs, transparency, deploy notes

**Files:**
- Modify: `README.md`, `CONTRIBUTING.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Add an Analytics transparency section to README.md**

Insert after the "Traffic stats without tracking" section (or near the end, before License):

```markdown
## Analytics (optional, privacy-first)

The hosted site records **aggregate** usage so the maintainer can see growth and
spot extraction breakage. What is stored: per-event timestamp, type
(visit/fetch/download), outcome (quality label or error code), a 2-letter country
(from Cloudflare, when proxied), and a **daily-rotating HMAC hash** used to estimate
unique visitors. What is **not** stored: IP addresses, any identifier that survives
a day, cookies for visitors, or anything that identifies a person. Events are pruned
after 90 days.

Analytics is **off by default**. It activates only when all of `TURSO_DATABASE_URL`,
`TURSO_AUTH_TOKEN`, `ADMIN_PASSWORD`, and `ANALYTICS_SALT` are set, so self-hosted
instances collect nothing unless you deliberately configure them. The admin
dashboard lives at `/admin` behind a password.

### Enabling it (hosted)

1. `turso db create savevidai --region aws-us-west-2`, then grab the URL and a token:
   `turso db show savevidai --url` and `turso db tokens create savevidai`.
2. Set `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `ADMIN_PASSWORD` (long + random; it
   doubles as session-signing key material), and `ANALYTICS_SALT` (long + random).
3. Optional: proxy the domain through Cloudflare (orange cloud) for country data.
```

- [ ] **Step 2: Add an analytics note to CONTRIBUTING.md**

Under the hard rules / architecture notes, add:

```markdown
## Analytics rules

- Never store a raw IP, a cross-day identifier, or a visitor cookie. Visitor
  counting uses only the daily-rotating HMAC hash in `app/analytics/hashing.py`.
- Recording is fire-and-forget: it must never block or fail a user request.
- Any new event field must be aggregate and non-identifying.
```

- [ ] **Step 3: Verify markdown renders and commit**

Run: `grep -c "off by default" README.md`
Expected: `1`.

```bash
git add README.md CONTRIBUTING.md && git commit -m "docs: analytics transparency + enablement notes"
```

---

### Task 12: Full verification pass

**Files:** none; release gate.

- [ ] **Step 1: Backend suite + lint**

```bash
cd backend && source .venv/bin/activate && python -m pytest -q && ruff check . && deactivate && cd ..
```

Expected: all green, only the known starlette warning.

- [ ] **Step 2: Frontend suite + build**

```bash
cd frontend && npm run lint && npm test -- --run && npm run build && cd ..
```

Expected: all green; `dist/index.html` and `dist/admin.html` both present.

- [ ] **Step 3: End-to-end locally with analytics enabled**

```bash
cd backend && source .venv/bin/activate
TURSO_DATABASE_URL=x TURSO_AUTH_TOKEN=x ADMIN_PASSWORD=testpw123 ANALYTICS_SALT=testsalt \
  STATIC_DIR=../frontend/dist python -c "
from app.main import create_app
from fastapi.testclient import TestClient
# swap Turso for in-memory sqlite so the local e2e needs no network
import app.analytics.store as store_mod
from app.analytics.store import SqliteStore
store_mod.make_store = lambda cfg: SqliteStore(':memory:')
c = TestClient(create_app())
print('visit', c.post('/api/event', json={'type':'visit'}).status_code)
print('login', c.post('/api/admin/login', json={'password':'testpw123'}).status_code)
print('stats', c.get('/api/admin/stats?days=30&tz=360').status_code)
"
deactivate && cd ..
```

Expected: `visit 204`, `login 204`, `stats 200`.

- [ ] **Step 4: Confirm public bundle untouched**

```bash
cd frontend && npm run build && grep -c "admin-root" dist/index.html && cd ..
```

Expected: `0` (the public page must not reference the admin root).

- [ ] **Step 5: Commit any fixes**

```bash
git add -A && git commit -m "test: analytics verification pass fixes"  # only if changes were needed
```

(Do not push; the user deploys and sets env vars.)
