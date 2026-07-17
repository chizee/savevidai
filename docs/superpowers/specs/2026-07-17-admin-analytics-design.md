# SaveVid AI - Private Admin Analytics Dashboard

Date: 2026-07-17
Status: Approved pending user review

## What

An owner-only dashboard at `/admin` showing aggregate usage of savevidai.israfill.dev: visitors, fetches, downloads, qualities, countries, errors, and traffic over time. No personal data is ever stored; the public "no tracking, no cookies" promise stays literally true for visitors.

## Goals

- Answer: how many people use the site, how much, from where, and is extraction healthy?
- Keep the privacy promise: no raw IPs at rest, no visitor cookies, aggregate-only metrics.
- Work on today's Render free tier (no persistent disk) and migrate unchanged to the VPS later.
- Zero impact on public-page performance and on fetch latency; analytics failure can never break the product.
- Analytics and admin are OFF by default for self-hosters (env-gated).

## Non-goals

- Per-visitor browsing history, session replay, raw IP logging, or cross-day visitor tracking.
- Third-party analytics scripts (would break the no-third-party-requests rule).
- Alerting/notifications (possible later on top of the same data).

## Privacy architecture

- Event rows contain: UTC timestamp, event type, outcome/label, 2-letter country (nullable), and a **daily-rotating anonymous visitor hash**: `HMAC-SHA256(key=ANALYTICS_SALT, message=utc_date || client_ip)` truncated to 16 hex chars. HMAC (not a bare concat hash) is the correct keyed-hash primitive here. The raw IP exists only in request memory and is never written, logged, or returned.
- Reversal resistance rests on the salt staying secret (env-only, never in the repo): without it, brute-forcing the IPv4 space is infeasible; the salt must be long and random. The hash rotates at UTC midnight, so even the anonymous ID cannot link a visitor across days.
- Country comes from the `CF-IPCountry` header when Cloudflare proxying is enabled (owner may flip the DNS record to proxied now that the Render cert is issued); otherwise stored as null and shown as "unknown". No GeoIP database, no IP-based lookup at rest.
- Retention: events older than 90 days are pruned daily by the writer.
- Admin authentication uses one cookie set only after the owner logs in; ordinary visitors receive no cookies, so the public FAQ copy remains true.
- README gains an "Analytics" transparency section: what is collected (aggregate counts, IP-free daily-rotating hash), what is not (IPs, identifiers, cookies), retention, and that self-hosted instances have it disabled unless configured.

## Client IP resolution (fixes a live production bug)

Uvicorn currently ignores forwarded headers, so behind Render's load balancer every visitor shares one client IP and the per-IP rate limits are globally shared. Fix, shipped with this feature:

- Uvicorn runs with `--proxy-headers --forwarded-allow-ips='*'` (container is only reachable through the platform LB).
- New `app/client_ip.py: client_ip(request) -> str` with precedence: `CF-Connecting-IP` header, else first hop of `X-Forwarded-For`, else `request.client.host`.
- The slowapi limiter key function and the visitor hash both use `client_ip()`.

## Storage

Turso (SQLite-compatible, free tier), accessed over its HTTP pipeline API with `httpx` - no new client dependency. Recommended DB region: AWS us-west-2 (matches Render Oregon). Schema (created on startup, `IF NOT EXISTS`):

```sql
CREATE TABLE IF NOT EXISTS events (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  ts      TEXT NOT NULL,            -- ISO-8601 UTC
  type    TEXT NOT NULL,            -- 'visit' | 'fetch' | 'download'
  outcome TEXT,                     -- fetch: 'ok'|error code; download: quality label; visit: NULL
  country TEXT,                     -- 2-letter code or NULL
  visitor TEXT NOT NULL             -- 16-hex daily-rotating hash
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(type, ts);
```

## Event ingestion

- `visit`: frontend fires `POST /api/event {type:"visit"}` once per page load. Counts real visitors and enables conversion rate; ad-blocker loss accepted as directional.
- `fetch`: recorded server-side inside `/api/resolve` after completion, outcome `ok` or the AppError code. Cache hits count (they are user-facing fetches).
- `download`: frontend fires `POST /api/event {type:"download", quality:"<label>"}` when a download starts (video bytes never touch the server, so client reporting is the only way to count real downloads). Quality validated against `^\d{2,4}p$|^video$`.
- `/api/event` is rate-limited 30/minute/IP; unknown types rejected 422. No body fields other than type/quality accepted.
- Writes are fire-and-forget: endpoints push onto a bounded in-process queue (cap 1000, drop-oldest with a logged warning); a background writer thread batches pipeline inserts every ~5 s. Turso being down never affects users.
- Enablement: all ingestion, `/api/event`, and `/api/admin/*` return 404/no-op unless **all four** of `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `ADMIN_PASSWORD`, and `ANALYTICS_SALT` are set. The salt is part of the gate on purpose: running with an empty salt would make visitor hashes brute-forceable, silently breaking the anonymity guarantee.

## Admin auth

- `POST /api/admin/login {password}` compared with `hmac.compare_digest` against `ADMIN_PASSWORD`; rate-limited 5/minute/IP; failures return a generic 401.
- Success sets a signed token cookie: payload = expiry timestamp (30 days), signed with a key derived via PBKDF2-HMAC-SHA256 (fixed app pepper, 100k iterations) from `ADMIN_PASSWORD`. Changing the password invalidates all sessions. Cookie flags: `HttpOnly; Secure; SameSite=Strict; Path=/api/admin`, so it is only ever sent to admin data endpoints.
- The `/admin` page itself is public static HTML that shows the login panel when unauthenticated; only the data endpoints are gated, so nothing sensitive is in the page markup.
- README documents: use a long random password; it doubles as key material.

## Stats API

`GET /api/admin/stats?days=30&tz=360` (cookie-gated; `tz` = minutes east of UTC, so day/hour buckets render in the owner's local time; Dhaka = 360). Two hard rules on `tz`:

- **Validation (SQL-injection guard):** the value is interpolated into SQLite's `datetime(ts, '+N minutes')` modifier string, so it must be parsed as an integer and clamped to [-840, 840] before any query is built; anything else is a 422. It is never string-substituted raw.
- **Sign convention:** JavaScript's `getTimezoneOffset()` returns UTC-minus-local (Dhaka = -360), so the frontend sends `-new Date().getTimezoneOffset()`.

Single JSON response:

- `totals`: fetches/downloads/visits for today, 7d, 30d, all-time; unique visitors today; success rate (ok fetches / all fetches, 30d); conversion rate. Because visitor hashes rotate daily by design, cross-day deduplication is impossible, so multi-day "unique" metrics are defined as **sums of daily distincts**: conversion = sum over the window of daily-distinct visitors who fetched, divided by the sum of daily-distinct visitors. The dashboard labels it "daily-unique basis" so the number is honest.
- `active_now`: distinct visitors in the last 5 minutes
- `series`: per-day fetches, downloads, visits, uniques for the window
- `countries`: top 10 by events, plus unknown bucket
- `qualities`: download counts by label
- `errors`: fetch outcomes != ok, by code - the FixTweet early-warning panel
- `hours`: events by local hour-of-day (busiest hours)

All computed with GROUP BY queries in one Turso pipeline call; `datetime(ts, '+<tz> minutes')` for local bucketing.

## Dashboard UI

Separate Vite entry (`admin.html` -> `src/admin/`) so the public bundle and its Lighthouse score are untouched. FastAPI serves it at `GET /admin`. Same design system (tokens, panels, Onest, accent). Components: login panel (wrong password reuses `.animate-shake`), stat tile grid (incl. Active now), 30-day line chart (fetches vs downloads vs visits), country and quality bar lists, error breakdown, busiest-hours strip. All charts hand-rolled inline SVG (no chart library). Auto-refreshes every 60 s. Dark/light via the same theme toggle mechanism.

## Error handling

- Turso unreachable: ingestion drops + logs; `stats` returns 503 `{"error":"analytics_unavailable"}` and the UI shows a friendly retry panel.
- Wrong/absent cookie: 401; UI falls back to the login panel.
- Malformed `/api/event`: 422, never recorded.

## Testing

- Visitor hash: HMAC construction, rotates across dates, stable within a day, never contains the IP; empty/missing salt keeps analytics disabled.
- `tz` param: integers accepted and clamped to [-840, 840]; non-integer and out-of-range values rejected 422; injection strings (`"1); DROP TABLE"`) never reach query text.
- Conversion math: multi-day windows computed as sums of daily distincts (fixture spanning 3 days with overlapping visitors proves no cross-day dedup is attempted).
- `client_ip()` precedence (CF header > XFF first hop > client.host).
- `/api/event` validation matrix and rate limit; disabled-mode returns 404.
- Auth: constant-time compare called, cookie signing round-trip, expiry rejection, wrong-password 401.
- Stats SQL executed against in-memory SQLite (same dialect) with seeded fixtures, including tz bucketing.
- Frontend: login flow state machine, tiles render from a stats fixture.

## Owner setup (one-time, ~5 min)

1. Create free Turso DB (`turso db create savevidai --region aws-us-west-2`), copy URL + auth token.
2. In Render: set `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `ADMIN_PASSWORD` (long random), `ANALYTICS_SALT` (long random).
3. Optional: flip the Cloudflare record to proxied (orange) for country data + DDoS shield.

## Risks

- Beacon undercounting from ad-blockers: accepted; fetch events are server-side and exact.
- Event-count inflation by a hostile client: rate limits + validation cap it; aggregate dashboards tolerate noise.
- Turso free-tier limits: orders of magnitude above expected volume; 90-day pruning bounds growth.
