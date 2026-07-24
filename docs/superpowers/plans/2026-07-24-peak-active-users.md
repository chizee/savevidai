# Peak Concurrent Active Users Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "peak concurrent visitors" record tile and a per-day peak line chart to the admin analytics dashboard, computed retroactively from stored events.

**Architecture:** A new backend helper `_peak_active(store, tz)` in `stats.py` groups events into fixed 5-minute buckets (floored on UTC epoch seconds), counts distinct visitors per bucket, and returns the all-time record bucket plus a per-local-day series of peak bucket counts. It is added under a `peak_active` key in the `compute_stats` response. The frontend extends the `Stats` type and renders a `Tile` plus a single-series `PeakChart`.

**Tech Stack:** Python 3.12 / FastAPI / SQLite+libsql (backend), TypeScript / React / Vite / Vitest (frontend). Backend tests with pytest from `backend/` with `.venv` active; frontend tests with `npm test` from `frontend/`.

## Global Constraints

- NO em dashes, NO emoji anywhere (code, comments, UI copy, commits, docs). Use hyphen/comma/colon.
- Conventional commit prefixes; end commit messages with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Backend test warning baseline is 7; anything new is a finding. `ruff check app tests` must pass clean.
- Aggregate-only, privacy-preserving: use only existing `ts` and `visitor` columns. No new event field, no new client beacon, no migration.
- Work on branch `feature/peak-active-users` (already created). Never commit to `main`.
- Peak = highest `COUNT(DISTINCT visitor)` in any fixed 5-minute bucket; buckets floored on UTC epoch (tz-independent), attributed to owner-local day for the chart and shown in owner-local time on the tile.

---

### Task 1: Backend `_peak_active` helper and response wiring

**Files:**
- Modify: `backend/app/analytics/stats.py` (add `_peak_active`, add `peak_active` key to `compute_stats` return dict near the other keys around line 242-249)
- Test: `backend/tests/test_stats.py` (append new tests; import `_peak_active` is not required, tests go through `compute_stats`)

**Interfaces:**
- Consumes: existing `_tzmod(tz)` helper in `stats.py` (returns a string like `"+330 minutes"` / `"-300 minutes"`), the `Store` protocol's `.query(sql, args)` returning a list of dict-like rows with int-coerced numeric cells.
- Produces: `compute_stats(...)["peak_active"]` with shape
  `{"record": {"count": int, "day": str, "time": str} | None, "series": [{"day": str, "peak": int}, ...]}`.
  `day` is a local `YYYY-MM-DD` string, `time` a local `HH:MM` (24h) string. Empty data -> `record` is `None`, `series` is `[]`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_stats.py`:

```python
def _insert(store, rows):
    store.execute_many([
        ("INSERT INTO events (ts,type,outcome,country,visitor) VALUES (?,?,?,?,?)", list(r))
        for r in rows
    ])


def test_peak_active_counts_distinct_in_same_bucket():
    # Two different visitors inside the same 5-minute bucket [10:00, 10:05) -> peak 2.
    s = SqliteStore(":memory:")
    s.init_schema()
    _insert(s, [
        ("2026-07-20 10:00:00", "visit", None, "US", "a"),
        ("2026-07-20 10:02:00", "visit", None, "US", "b"),
    ])
    rec = compute_stats(s, days=30, tz=0)["peak_active"]["record"]
    assert rec == {"count": 2, "day": "2026-07-20", "time": "10:00"}


def test_peak_active_split_buckets_is_one():
    # Same two visitors, but in different 5-minute buckets -> concurrency never
    # exceeds 1. This pins the tumbling-bucket semantics vs a sliding window.
    s = SqliteStore(":memory:")
    s.init_schema()
    _insert(s, [
        ("2026-07-20 10:00:00", "visit", None, "US", "a"),
        ("2026-07-20 10:06:00", "visit", None, "US", "b"),
    ])
    assert compute_stats(s, days=30, tz=0)["peak_active"]["record"]["count"] == 1


def test_peak_active_dedups_repeat_visitor_in_bucket():
    # Same visitor firing multiple events in one bucket counts once (DISTINCT).
    s = SqliteStore(":memory:")
    s.init_schema()
    _insert(s, [
        ("2026-07-20 10:00:00", "visit", None, "US", "a"),
        ("2026-07-20 10:01:00", "fetch", "ok", "US", "a"),
        ("2026-07-20 10:03:00", "download", "1080p", "US", "a"),
    ])
    assert compute_stats(s, days=30, tz=0)["peak_active"]["record"]["count"] == 1


def test_peak_active_series_per_day_max_and_tz():
    # tz = -300 (UTC-5). A 02:00 UTC bucket falls on the PREVIOUS local day.
    #   02:00 UTC -> 2026-07-19 21:00 local, two visitors -> that local day peak 2
    #   15:00 UTC -> 2026-07-20 10:00 local, one visitor -> that local day peak 1
    s = SqliteStore(":memory:")
    s.init_schema()
    _insert(s, [
        ("2026-07-20 02:00:00", "visit", None, "US", "a"),
        ("2026-07-20 02:02:00", "visit", None, "US", "b"),
        ("2026-07-20 15:00:00", "visit", None, "US", "c"),
    ])
    peak = compute_stats(s, days=30, tz=-300)["peak_active"]
    assert peak["series"] == [
        {"day": "2026-07-19", "peak": 2},
        {"day": "2026-07-20", "peak": 1},
    ]
    assert peak["record"] == {"count": 2, "day": "2026-07-19", "time": "21:00"}


def test_peak_active_empty_store():
    s = SqliteStore(":memory:")
    s.init_schema()
    assert compute_stats(s, days=30, tz=0)["peak_active"] == {"record": None, "series": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_stats.py -k peak_active -q`
Expected: FAIL - `KeyError: 'peak_active'` (the key does not exist yet).

- [ ] **Step 3: Write the helper**

Add to `backend/app/analytics/stats.py` (place it above `compute_stats`, after the other module-level helpers like `_local` / `_count_since`):

```python
def _peak_active(store: Store, tz: int) -> dict:
    """Peak concurrent visitors: the highest COUNT(DISTINCT visitor) in any
    fixed 5-minute bucket. Buckets are floored on UTC epoch seconds so
    concurrency is timezone-independent; each bucket is attributed to the
    owner's local calendar day (and its start rendered in local time). `record`
    is the single highest bucket over all retained data (ties break toward the
    most recent bucket); `series` is the per-local-day maximum bucket count.
    Returns record=None and series=[] on an empty table.

    This is a tumbling-window peak; the live `active_now` gauge is a trailing
    sliding window, so the two can differ at a bucket boundary. 5 minutes is
    chosen to match the live gauge's window length. Data prunes at 90 days
    (recorder.py), so this is really "peak in the last 90 days"."""
    tzmod = _tzmod(tz)
    # Bucket start = epoch seconds floored to a 5-minute (300s) boundary.
    bucket = "(CAST(strftime('%s', ts) AS INTEGER) / 300) * 300"
    per_bucket = (
        f"SELECT {bucket} AS b, COUNT(DISTINCT visitor) AS n FROM events GROUP BY b"
    )
    rec = store.query(
        f"SELECT date(datetime(b, 'unixepoch', '{tzmod}')) AS day, "
        f"strftime('%H:%M', datetime(b, 'unixepoch', '{tzmod}')) AS time, "
        f"n AS count FROM ({per_bucket}) ORDER BY n DESC, b DESC LIMIT 1", [],
    )
    record = (
        {"count": rec[0]["count"], "day": rec[0]["day"], "time": rec[0]["time"]}
        if rec else None
    )
    series_rows = store.query(
        f"SELECT date(datetime(b, 'unixepoch', '{tzmod}')) AS day, MAX(n) AS peak "
        f"FROM ({per_bucket}) GROUP BY day ORDER BY day", [],
    )
    series = [{"day": r["day"], "peak": r["peak"]} for r in series_rows]
    return {"record": record, "series": series}
```

Then add the key to the `compute_stats` return dict (alongside `"avg_active"`, `"sources"`, `"visitors"`):

```python
        "peak_active": _peak_active(store, tz),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source .venv/bin/activate && python -m pytest tests/test_stats.py -q && ruff check app tests`
Expected: all pass, ruff clean.

- [ ] **Step 5: Run the full backend suite (no regressions, warning baseline held)**

Run: `cd backend && source .venv/bin/activate && python -m pytest -q`
Expected: all pass; warnings still 7.

- [ ] **Step 6: Commit**

```bash
git add backend/app/analytics/stats.py backend/tests/test_stats.py
git commit -m "feat: compute peak concurrent visitors from 5-minute buckets

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Frontend peak tile and per-day peak chart

**Files:**
- Modify: `frontend/src/admin/api.ts` (extend the `Stats` type)
- Modify: `frontend/src/admin/Admin.tsx` (add `PeakChart`, a `fillPeakDays` helper, the record tile + caption, and place the chart)
- Test: `frontend/src/admin/Admin.test.tsx` (extend the `STATS` mock and the older-deploy mock; add assertions)

**Interfaces:**
- Consumes: `Stats["peak_active"]` from Task 1 (`{ record: { count, day, time } | null; series: Array<{ day; peak }> }`); existing `Tile`, `formatDay`, and the `panel` / chart styling idioms in `Admin.tsx`.
- Produces: no exports consumed elsewhere; renders into the existing dashboard layout.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/admin/Admin.test.tsx`, add `peak_active` to the `STATS` mock (inside the object literal, e.g. after `visitors`):

```typescript
  peak_active: {
    record: { count: 47, day: "2026-07-21", time: "21:15" },
    series: [
      { day: "2026-07-20", peak: 30 },
      { day: "2026-07-21", peak: 47 },
    ],
  },
```

Add a new test (anywhere after the mount helpers, following the file's existing style of rendering the dashboard and asserting on text):

```typescript
test("shows the peak concurrent record tile", async () => {
  renderAuthed(); // use whatever the file's existing "render an authed dashboard" path is
  expect(await screen.findByText("Peak concurrent")).toBeInTheDocument();
  expect(screen.getByText("47")).toBeInTheDocument();
});
```

Note: match the surrounding tests' actual render/auth helper (this file already mounts the authed dashboard in other tests - reuse that exact pattern rather than inventing `renderAuthed` if it does not exist).

In the existing older-deploy test (around line 168, the one that builds a stats payload omitting `avg_active`/`sources`/`visitors`), ALSO omit `peak_active` so it asserts the panel still renders without crashing.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- Admin`
Expected: FAIL - `Stats` type has no `peak_active` (type error) and/or "Peak concurrent" text not found.

- [ ] **Step 3: Extend the `Stats` type**

In `frontend/src/admin/api.ts`, add to the `Stats` type (after `visitors`):

```typescript
  peak_active: {
    record: { count: number; day: string; time: string } | null;
    series: Array<{ day: string; peak: number }>;
  };
```

- [ ] **Step 4: Add the `PeakChart` component and fill helper**

In `frontend/src/admin/Admin.tsx`, add a fill helper near `fillDays`:

```typescript
// Fill missing calendar days with peak 0 so the line dips honestly across gaps.
function fillPeakDays(series: Stats["peak_active"]["series"]): Stats["peak_active"]["series"] {
  if (series.length === 0) return [];
  const byDay = new Map(series.map((s) => [s.day, s]));
  const start = Date.parse(`${series[0]!.day}T00:00:00Z`);
  const end = Date.parse(`${series[series.length - 1]!.day}T00:00:00Z`);
  const out: Stats["peak_active"]["series"] = [];
  for (let t = start; t <= end; t += 86_400_000) {
    const day = new Date(t).toISOString().slice(0, 10);
    out.push(byDay.get(day) ?? { day, peak: 0 });
  }
  return out;
}
```

Add the chart component (mirrors `LineChart`, single series):

```typescript
function PeakChart({ series }: { series: Stats["peak_active"]["series"] }) {
  const points = fillPeakDays(series);
  if (points.length === 0) {
    return (
      <div className="panel p-4 sm:col-span-2">
        <h2 className="font-semibold">Peak concurrent per day</h2>
        <p className="mt-3 text-sm text-[var(--muted)]">No data yet.</p>
      </div>
    );
  }
  const width = 760, height = 220, left = 32, right = 10, top = 14, bottom = 24;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const n = points.length;
  const max = Math.max(1, ...points.map((p) => p.peak));
  const x = (i: number) => left + (n <= 1 ? plotW / 2 : (plotW * i) / (n - 1));
  const y = (v: number) => top + plotH * (1 - v / max);
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.peak).toFixed(1)}`).join(" ");
  return (
    <div className="panel p-4 sm:col-span-2">
      <h2 className="font-semibold">Peak concurrent per day</h2>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Line chart of daily peak concurrent visitors" className="mt-3 h-auto w-full">
        {[0, 0.5, 1].map((f) => (
          <line key={f} x1={left} x2={width - right} y1={top + plotH * f} y2={top + plotH * f} stroke="var(--line)" strokeWidth="1" />
        ))}
        <text x={left - 6} y={top + 4} textAnchor="end" fontFamily="var(--font-mono)" fontSize="10" fill="var(--faint)">{max}</text>
        <text x={left - 6} y={top + plotH + 4} textAnchor="end" fontFamily="var(--font-mono)" fontSize="10" fill="var(--faint)">0</text>
        <path d={path} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx={x(n - 1)} cy={y(points[n - 1]!.peak)} r="3" fill="var(--accent)" />
        <text x={left} y={height - 6} fontFamily="var(--font-mono)" fontSize="10" fill="var(--faint)">{formatDay(points[0]!.day)}</text>
        <text x={width - right} y={height - 6} textAnchor="end" fontFamily="var(--font-mono)" fontSize="10" fill="var(--faint)">{formatDay(points[n - 1]!.day)}</text>
      </svg>
    </div>
  );
}
```

- [ ] **Step 5: Read `peak_active` defensively and render tile + chart**

In the `Dashboard` render body of `Admin.tsx`, add the defensive read next to the others (near `const avgActive = stats.avg_active ?? ...`):

```typescript
  const peak = stats.peak_active ?? { record: null, series: [] };
```

After the avg-active caption `<p>` (the "Average daily unique visitors..." paragraph), add the peak tile and caption:

```tsx
      <div className="mt-3 grid grid-cols-2 gap-3">
        <Tile label="Peak concurrent" value={peak.record ? peak.record.count : "-"} />
      </div>
      <p className="mt-2 text-xs text-[var(--faint)]">
        {peak.record
          ? `Most visitors on the site at once, in any 5-minute window: ${formatDay(peak.record.day)}, ${peak.record.time}. Last 90 days.`
          : "Most visitors on the site at once, in any 5-minute window. No data yet."}
      </p>
```

Inside the charts grid (`<div className="mt-4 grid gap-3 sm:grid-cols-2">`), add the chart after `<LineChart ... />`:

```tsx
        <PeakChart series={peak.series} />
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npm test -- Admin`
Expected: PASS, including the older-deploy test that omits `peak_active`.

- [ ] **Step 7: Typecheck and build**

Run: `cd frontend && npm run build`
Expected: clean build, no TS errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/admin/api.ts frontend/src/admin/Admin.tsx frontend/src/admin/Admin.test.tsx
git commit -m "feat: show peak concurrent tile and per-day peak chart in admin

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Definition (5-min bucket, UTC-floored, local-day attribution, local-time record) -> Task 1 helper + tests.
- Response shape `peak_active: {record, series}` -> Task 1 Step 3, consumed in Task 2 Step 3.
- Record tile + caption with 90-day honesty -> Task 2 Step 5.
- Per-day peak chart reusing the LineChart pattern -> Task 2 Step 4.
- Privacy / no migration -> only `ts` + `visitor` used; no schema change (whole plan).
- Empty-data handling -> Task 1 `test_peak_active_empty_store`, Task 2 null-record caption + chart "No data yet".
- Older-deploy guard -> Task 2 Step 1 (extend the existing omit-keys test) + Step 5 `?? { record: null, series: [] }`.
- Testing bullets from spec (same-bucket, split-bucket, tz day attribution, empty, distinct dedup) -> all present in Task 1 Step 1.

**Placeholder scan:** No TBD/TODO; all code shown. The only soft instruction is "reuse the file's existing authed-render helper" in Task 2 Step 1, which is deliberate (the test file already has that pattern; naming it wrongly would be worse than pointing at it).

**Type consistency:** `peak_active` shape identical in Task 1 (Produces), Task 2 api.ts type, `PeakChart` prop type, and `fillPeakDays`. `record` fields `count`/`day`/`time` consistent across backend dict, TS type, and tile/caption reads. `series` item `{day, peak}` consistent across backend, type, fill helper, and chart.
