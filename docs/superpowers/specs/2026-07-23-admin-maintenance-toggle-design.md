# Admin Maintenance Toggle - Design

Add a maintenance on/off switch to the existing admin dashboard so the owner can take the site into maintenance mode with one click, instantly, no Render redeploy. Consolidates site control and analytics into one complete admin panel.

## Goals

1. A "Site controls" section at the top of the admin dashboard with a maintenance toggle: click to show the maintenance page to visitors, click again to go live.
2. Instant (no redeploy). Only the logged-in owner can flip it.
3. The existing `MAINTENANCE_MODE` env var stays as a hard override / backup and for self-hosters who run without analytics.
4. Everything (site control + analytics) lives in one admin dashboard.

## Non-goals

- No persistence of the flag across restarts/deploys. In-memory is deliberate (see below): a deploy or restart clears it to OFF, which is the desired "auto-live once the update ships" behavior and prevents the site ever getting stuck down.
- No multi-worker flag syncing. The prod service runs a single uvicorn worker (verified: Dockerfile CMD has no `--workers`), so a module-level flag is consistent. If workers are ever added, the flag would need to move to Turso; out of scope now.
- No new analytics metrics.

## Verified foundation (2026-07-23)

The owner set all four analytics env vars in Render (TURSO_DATABASE_URL, TURSO_AUTH_TOKEN, ADMIN_PASSWORD, ANALYTICS_SALT). Prod now has the admin panel live: `/admin` returns 200, `/api/admin/login` is active (422 on empty body), `/api/admin/stats` returns 401 unauthenticated. So `service.enabled` is true in prod and the cookie-auth flow works. The toggle builds directly on this.

## Backend

### In-memory flag (`backend/app/maintenance.py`, new)

A tiny module owning the process-local switch:
- `is_on() -> bool` returns the current in-memory flag.
- `set_on(value: bool) -> None` sets it.
- Module-level default False.

Rationale for in-memory over Turso persistence: instant toggle, no DB round-trip in the request path, and fail-safe. A restart or deploy resets it to False, so (a) a normal deploy automatically returns the site to Live once the new build is healthy, and (b) the site can never be stuck in maintenance by a stale flag. UptimeRobot keeps the single process alive between deploys, so the flag is stable during a working session.

### Middleware (`backend/app/main.py`)

`_maintenance_on()` becomes: `maintenance.is_on() or <the existing MAINTENANCE_MODE env truthy check>`. So maintenance is shown if EITHER the in-memory toggle is on OR the env var is set. The env var is a hard override (cannot be turned off from the UI while it is set). Everything else in the maintenance short-circuit is unchanged.

### Admin endpoints (`backend/app/analytics/router.py`)

Two endpoints under the existing `/api/admin` cookie path, both gated by `_require_enabled()` then cookie verification (same `verify_cookie(cookie, cfg.admin_password, time.time())` pattern the stats endpoint uses):

- `GET /api/admin/maintenance` -> `{"on": bool, "forced_by_env": bool}`. `on` is the effective state (`_maintenance_on()`), `forced_by_env` is true when the env var is set (so the UI can explain why the toggle is locked on). 401 without a valid cookie, 404 when analytics disabled.
- `POST /api/admin/maintenance` body `{"on": bool}` -> sets the in-memory flag via `maintenance.set_on(...)`, returns the same shape as the GET. Cookie-verified, rate-limited (e.g. `10/minute`). When `forced_by_env` is true, a POST setting `on=false` still returns `on=true` (env wins); the response's `forced_by_env` tells the UI to show why.

CSRF: the admin cookie is `samesite=strict`, so a cross-site POST cannot carry it. The state-changing POST is therefore CSRF-safe by the existing cookie policy. No request data is reflected.

Self-hosters without analytics: `_require_enabled()` returns 404 for these endpoints, so the toggle is simply unavailable and they use the `MAINTENANCE_MODE` env var. Graceful degradation, no error.

## Frontend

### `frontend/src/admin/api.ts`

- Type `Maintenance = { on: boolean; forced_by_env: boolean }`.
- `getMaintenance(): Promise<Maintenance>` (GET, credentials included like the stats call).
- `setMaintenance(on: boolean): Promise<Maintenance>` (POST).

### `frontend/src/admin/Admin.tsx`

A "Site controls" panel rendered at the TOP of the dashboard (above the analytics panels), styled with the existing panel tokens:
- A status line: a colored dot + label. Green "Live" when off, amber "In maintenance" when on.
- A toggle control (button or switch) reflecting the state.
  - Turning ON asks for a lightweight confirm first ("This shows the maintenance page to everyone. Continue?") since it takes the site down.
  - Turning OFF is immediate.
- After a successful toggle, the status updates from the endpoint response (source of truth), not optimistically guessed.
- When `forced_by_env` is true: the toggle is disabled and a one-line note explains the site is held in maintenance by the environment variable and must be cleared in Render. (Edge case; normal use is the button alone.)
- State loads on mount (alongside the existing stats fetch) and refreshes with the existing 60s poll or after a toggle.

The analytics dashboard below is unchanged. The result reads as one control-center-plus-analytics panel.

## Workflow this unlocks

- Show maintenance during an update: click the toggle ON (site shows the page instantly), push your update, and the deploy automatically returns the site to Live when the new build is healthy. No third step.
- Pause the site briefly without deploying: toggle ON, then toggle OFF when done. Both instant.
- Backup / force: set `MAINTENANCE_MODE` in Render to hold maintenance across restarts, or for a deploy where you do not want the auto-clear.

## Constraints

- No em dashes, no emoji anywhere (copy, code, comments).
- Reuse existing auth (`verify_cookie`, `COOKIE`, `check_password`), the existing `_require_enabled` gate, and existing panel styling tokens. No new dependencies.
- Backend commands from `backend/` (venv); frontend from `frontend/`. Warning baseline 6. Conventional commits.

## Testing / verification gate

- Backend: toggle POST with a valid cookie sets the flag and the middleware then serves the maintenance page (503); GET reflects it; POST/GET without a cookie -> 401; endpoints 404 when analytics disabled; env var forces `on=true` and `forced_by_env=true` even after a POST `on=false`; turning the flag off restores 200.
- Frontend: the Site controls panel renders Live/In-maintenance from the fetched state; clicking to enable prompts confirm then calls setMaintenance(true) and shows the new state; clicking to disable calls setMaintenance(false); forced_by_env disables the control with the note.
- Live gate (prod, after deploy, logged in): flip the toggle on, confirm the site shows the maintenance page for a logged-out visitor while the admin stays usable, flip it off, confirm the site is live. Confirm a normal analytics load still works.
