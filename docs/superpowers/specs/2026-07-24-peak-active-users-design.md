# Peak concurrent active users - design

Date: 2026-07-24
Status: approved (brainstorm)
Branch: feature/peak-active-users

## Problem

The dashboard shows a live "Active now" gauge (distinct visitors in the trailing
5 minutes) but never records how high it has ever gone. The owner wants to know
the peak concurrent usage of the site and whether peaks are trending up.

## Definition

Peak concurrent = the highest `COUNT(DISTINCT visitor)` in any fixed 5-minute
bucket. Buckets are floored on UTC epoch seconds so concurrency is
timezone-independent; each bucket is attributed to a local calendar day (owner's
tz, same as the rest of the dashboard) for the chart, and the record's timestamp
is rendered in the owner's local time.

This is a tumbling-window definition. The live "Active now" gauge is a trailing
(sliding) window, so the two can differ at the margin when a spike straddles a
bucket boundary. "Peak concurrent per 5-minute interval" is the standard
analytics meaning and is the intended metric here. Bucket size is fixed at 5
minutes to match the live gauge's window length.

## Data source and privacy

Uses only existing columns: `ts` and `visitor` (the daily-rotating HMAC hash,
IP already discarded). No new event field, no new client beacon, no migration.
Aggregate-only, fully within the existing privacy model.

## Retention

Events prune at 90 days (`recorder.py` `prune_days=90`), so the metric is
"peak in the last 90 days". Currently no data has pruned (site launched
2026-07-16), so it is effectively all-time. The tile is captioned to stay honest
after pruning begins.

## Backend (backend/app/analytics/stats.py)

Add a helper computing two things from the events table, added under a new
`peak_active` key in the `compute_stats` response:

```
peak_active: {
  record: { count: int, day: str, time: str } | null,   # null on empty data
  series: [ { day: str, peak: int }, ... ]               # one point per local day
}
```

5-minute bucket key (SQL): `(strftime('%s', ts) / 300) * 300` (integer epoch
seconds floored to the bucket start).

- **record**: over the whole retained window, the bucket with the highest
  distinct-visitor count. Query groups by bucket, `COUNT(DISTINCT visitor)`,
  orders desc, limit 1. `count` is the distinct count; `day` and `time` are the
  bucket-start converted to the owner's local tz (`day` = local date string,
  `time` = local HH:MM). Empty table -> `record` is `null`.
- **series**: per local day, the max bucket count that day. Two-level
  aggregate: inner selects per (local-day, bucket) distinct-visitor counts,
  outer takes `MAX` per local day. Sorted ascending by day, consistent with the
  existing `series` output.

Local-day and local-time derivation reuse the same `{local}` tz-shift the file
already builds for other queries (`parse_tz` validated offset). The record
timestamp uses the same shift so the tile and chart agree.

Cost: one extra grouped scan (record) plus one two-level grouped scan (series)
per dashboard load. Dashboard is owner-only and loaded rarely; `idx_events_ts`
already exists. No new index.

## Frontend (frontend/src/admin/)

- `api.ts`: extend the `Stats` type with
  `peak_active: { record: { count: number; day: string; time: string } | null; series: Array<{ day: string; peak: number }> }`.
- `Admin.tsx`:
  - A record `Tile` near the existing avg-active tiles: label "Peak concurrent",
    value the count, with a caption line "Jul 21, 9:15pm - last 90 days" (or a
    dash when `record` is null). Read defensively with `?? { record: null,
    series: [] }` so an older backend deploy cannot crash the panel (mirrors the
    existing `avg_active ?? ...` guard).
  - A single-series daily line chart of `series[].peak`. Reuse the existing
    `LineChart`/`fillDays` pattern rather than inventing a new chart system;
    a minimal one-series variant is acceptable. Empty series renders nothing
    (same as the existing chart with no data).

## Testing (TDD, backend)

Seed a `SqliteStore` and assert:
- Two visitors within the same 5-minute bucket -> record count 2.
- The same two visitors split across two different buckets -> record count 1
  (pins the tumbling-bucket semantics, distinguishing it from a sliding window).
- Distinct visitors on different local days -> `series` has the right per-day
  peak on the right day; a nonzero `tz` puts a boundary-straddling bucket on the
  correct local day.
- Empty store -> `record` is `null`, `series` is `[]`.
- A repeat visitor (same hash twice in a bucket) counts once (DISTINCT).

Frontend: extend the existing Admin stats mock with `peak_active` and assert the
tile renders the count and the null case renders a dash; older-deploy guard test
(missing `peak_active` key) does not throw.

## Out of scope

- Intraday / per-hour concurrency chart (finer granularity) - not now.
- Peak daily-uniques ("best day") - a different metric the owner did not ask for.
- Any change to the live "Active now" gauge.
