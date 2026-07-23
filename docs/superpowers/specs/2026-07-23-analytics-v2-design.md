# Analytics v2 - Richer Visitor Insight - Design

Add three visitor insights to the admin dashboard: rolling average active users per day, traffic sources (how people arrive), and new vs returning visitors. All privacy-preserving: only category words are ever sent or stored, never URLs or cross-day identifiers.

## Goals

1. **Average active users/day** - 7-day and 30-day rolling averages of daily unique visitors, shown as tiles. Computed from data already recorded; no new tracking.
2. **Traffic sources** - a breakdown of Direct / Search / Social / Referral / Internal, from the visitor's referrer categorized in the browser (only the bucket word is sent).
3. **New vs returning** - a split of first-time vs returning visitors, from a local browser flag (the linkage lives on the visitor's device, never on the server).

## Non-goals

- No full referrer URLs stored or logged. No cross-day server-side visitor identifier. The daily-rotating HMAC visitor hash stays exactly as-is; these features do not weaken it.
- No cookie-consent banner: no persistent identifier is created server-side; the new/returning flag is browser-local (localStorage), and the referrer is reduced to a bucket in the browser.
- No change to how fetch/download events are recorded. The two new fields apply to visit events only.

## Privacy model (unchanged guarantees)

- `source` is one of a fixed small set of category words, decided in the browser from `document.referrer`. The raw referrer URL never leaves the browser and is never stored.
- `visitor_kind` is "new" or "returning", decided in the browser from a localStorage flag (`svai_seen`). The server never receives anything that links a visitor across days; it only aggregates the category. This is an estimate (a cleared cache, incognito, or a new device reads as "new") and the dashboard + CONTRIBUTING note it honestly.
- Both fields are nullable and only set on visit events. Old rows (and fetch/download rows) have them null and are handled gracefully in every query.

## Data model (`backend/app/analytics/store.py`)

The `events` table gains two nullable columns via the same idempotent, boot-safe migration pattern the `platform` column used (`_ensure_*_column` helpers returning ALTER statements only when the column is absent; added to the base `CREATE TABLE` too so fresh DBs never ALTER):
- `source TEXT` - the referrer bucket.
- `visitor_kind TEXT` - "new" or "returning".

The migration must never crash boot (the enablement block in `main.py` is already try/except wrapped).

## Recorder + service + router

- `Recorder.record(type, visitor, outcome=None, country=None, platform=None, source=None, visitor_kind=None)`; `_INSERT` and the queued tuple include the two new fields in column order.
- `AnalyticsService.record_from_request(request, type, outcome, platform=None, source=None, visitor_kind=None)` threads them through.
- `EventIn` gains `source: str | None` and `visitor_kind: str | None`, validated:
  - `source` in `{direct, search, social, referral, internal}` or None.
  - `visitor_kind` in `{new, returning}` or None.
  - Invalid values -> 422 (same as the existing platform/quality validators).
- The `/api/event` handler passes `source` and `visitor_kind` from the payload only for `type == "visit"` (ignore them on download events).

## Frontend (`frontend/src/lib/analytics.ts`, `frontend/src/App.tsx`, TikTokApp, RedditApp)

- `sendEvent(type, opts)` opts type widens to `{ quality?: string; platform?: string; source?: string; visitor_kind?: string }`. The body already spreads opts, so no send-path change beyond the type.
- A small pure helper `visitContext()` (new, e.g. in `analytics.ts` or a sibling) returns `{ source, visitor_kind }`:
  - `source` from `document.referrer`:
    - empty referrer -> `direct`
    - referrer host === current host -> `internal`
    - host matches a search-engine list (google, bing, duckduckgo, yahoo, ecosia, baidu, yandex, and common variants) -> `search`
    - host matches a social list (t.co, twitter, x.com, reddit, facebook, instagram, tiktok, youtube, linkedin, pinterest, and common variants) -> `social`
    - any other host -> `referral`
    - matching is host-suffix based (endsWith on a normalized host) so subdomains count; wrap `new URL(referrer)` in try/catch and fall back to `direct` on parse failure.
  - `visitor_kind`: if `localStorage["svai_seen"]` is set -> `returning`; else -> `new` and set it. Wrap in try/catch (localStorage can throw in private mode) and fall back to `new` without persisting.
- Each page's visit beacon becomes `sendEvent("visit", { platform: <p>, ...visitContext() })`. The download beacons are unchanged.
- The helper is pure/testable: it takes the referrer string and a storage accessor (or reads them internally with guards) so tests can exercise each branch.

## Stats (`backend/app/analytics/stats.py`)

`compute_stats` adds three keys, all over the same local-time window already used by the other queries:
- `avg_active`: `{ "d7": int, "d30": int }` - the mean of daily unique-visitor counts over the last 7 and 30 days. Derive from the same per-day uniques the `series` already computes (average the uniques of the days present in the window; round to nearest int; 0 when no data). d7 uses the last 7 days, d30 the last 30, regardless of the requested `days` range (so the tiles are stable).
- `sources`: `[{ "source": str, "count": int }]` - visit events grouped by `source` where `source IS NOT NULL`, ordered count desc.
- `visitors`: `{ "new": int, "returning": int }` - visit events counted by `visitor_kind` over the window.

## Dashboard (`frontend/src/admin/Admin.tsx`, `frontend/src/admin/api.ts`)

- `Stats` type gains `avg_active: { d7: number; d30: number }`, `sources: { source: string; count: number }[]`, `visitors: { new: number; returning: number }`.
- Two new tiles in the top tile row (or a small row under it): "Avg/day 7d" and "Avg/day 30d" from `avg_active`.
- A "Traffic sources" `BarList` panel (label = source, value = count), `maxRows` not needed (max 5 buckets). Empty -> "No data yet."
- A "New vs returning" panel: either two small tiles (New, Returning) or a two-row BarList. Include a one-line caption that it is a privacy-safe browser estimate.
- All panels use existing tokens and styling. No layout regression to the current dashboard.

## Docs

- README/CONTRIBUTING analytics section: note the two new fields are browser-categorized buckets (no URLs, no cross-day IDs), and that new/returning is a localStorage-based estimate consistent with the no-tracking stance.

## Constraints

- No em dashes, no emoji anywhere (copy, code, comments). No new dependencies. Conventional commits.
- Reuse the existing migration, recorder, service, and BarList/Tile patterns. Backend from `backend/` (venv); frontend from `frontend/`. Warning baseline 7.
- The `/api/event` quality regex and platform validation are unchanged; only new optional fields are added.

## Testing / verification gate

- Backend: migration idempotent + fresh-vs-legacy column present; record writes source/visitor_kind; EventIn accepts valid values and 422s invalid; stats avg_active averages daily uniques correctly (including a nonzero-tz window case), sources groups non-null, visitors splits new/returning; old null rows handled.
- Frontend: `visitContext()` returns the right source for empty/internal/search/social/referral referrers and new-then-returning across two calls (with a mocked storage); the visit beacon body includes source + visitor_kind; the dashboard renders the avg tiles, traffic-sources panel, and new/returning panel from a fixture.
- Live gate (prod, after deploy, logged in): confirm the new tiles/panels render with real data, a fresh visit records a source and new/returning, and existing analytics still load. Do not push or deploy without the owner.
