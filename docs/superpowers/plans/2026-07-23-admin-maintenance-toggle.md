# Admin Maintenance Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a maintenance on/off switch to the admin dashboard so the owner can toggle the site's maintenance page instantly, no redeploy, with the existing `MAINTENANCE_MODE` env var kept as a hard override.

**Architecture:** A process-local in-memory flag (`maintenance.py`) is read by the existing maintenance middleware alongside the env var. Two cookie-authenticated admin endpoints get and set the flag. The admin dashboard gains a "Site controls" panel at the top with a confirm-on-enable toggle that reflects the effective state.

**Tech Stack:** Python 3.12, FastAPI, pytest. TypeScript, Vite 6, React, Vitest.

**Spec:** `docs/superpowers/specs/2026-07-23-admin-maintenance-toggle-design.md` (read before starting).

## Global Constraints

- The in-memory flag is process-local and defaults to False; a restart/deploy clears it (deliberate: deploy auto-returns the site to Live, and the site can never get stuck down). Single uvicorn worker in prod (Dockerfile CMD has no `--workers`), so the flag is consistent.
- Effective maintenance state = `maintenance.is_on() OR MAINTENANCE_MODE env truthy`. The env var is a hard override that the UI toggle cannot clear.
- Admin endpoints live under `/api/admin` (shares the existing admin cookie path), are gated by `_require_enabled()` then `verify_cookie(...)`, and return 401 without a valid cookie, 404 when analytics is disabled.
- CSRF safety comes from the existing `samesite=strict` admin cookie; do not weaken it.
- Reuse existing auth (`verify_cookie`, `COOKIE`, `check_password`, `service.config()`), the `_require_enabled` gate, and existing panel styling tokens. No new dependencies.
- No em dashes, no emoji anywhere (copy, code, comments). Conventional commits.
- Backend from `backend/` with venv active (`source .venv/bin/activate`); frontend from `frontend/`. Warning baseline: 6.

## File structure

Backend:
- Create `backend/app/maintenance.py` - the in-memory flag (`is_on`, `set_on`).
- Modify `backend/app/main.py` - `_maintenance_on()` reads the flag OR the env var.
- Modify `backend/app/analytics/router.py` - GET + POST `/api/admin/maintenance`.

Frontend:
- Modify `frontend/src/admin/api.ts` - `Maintenance` type + `getMaintenance`/`setMaintenance`.
- Create `frontend/src/admin/SiteControls.tsx` - the toggle panel.
- Modify `frontend/src/admin/Admin.tsx` - render `SiteControls` at the top of the dashboard.

---

### Task 1: In-memory flag + middleware wiring

**Files:**
- Create: `backend/app/maintenance.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_maintenance.py` (extend), `backend/tests/test_maintenance_flag.py` (new, for the module)

**Interfaces:**
- Produces: `maintenance.is_on() -> bool`, `maintenance.set_on(value: bool) -> None`, module default False. `main._maintenance_on()` returns `maintenance.is_on() or <existing env truthy check>`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_maintenance_flag.py`:
```python
from app import maintenance


def test_flag_defaults_off_and_toggles():
    maintenance.set_on(False)
    assert maintenance.is_on() is False
    maintenance.set_on(True)
    assert maintenance.is_on() is True
    maintenance.set_on(False)
    assert maintenance.is_on() is False
```

Append to `backend/tests/test_maintenance.py` a test that the in-memory flag drives the middleware (mirror the existing STATIC_DIR setup the file already uses; MAINTENANCE_MODE must be unset for this test):
```python
def test_in_memory_flag_triggers_maintenance(monkeypatch, tmp_static):
    # tmp_static = the fixture/helper the file already uses to point STATIC_DIR at a dir
    # with maintenance.html; adapt to the file's actual setup.
    from app import maintenance
    monkeypatch.delenv("MAINTENANCE_MODE", raising=False)
    client = <build the TestClient as the existing tests do>
    maintenance.set_on(False)
    assert client.get("/").status_code == 200
    maintenance.set_on(True)
    try:
        assert client.get("/").status_code == 503
    finally:
        maintenance.set_on(False)
```
(Read the current `test_maintenance.py` first and match its client/STATIC_DIR construction exactly. Always reset the flag to False in a finally so tests do not leak state.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_maintenance_flag.py tests/test_maintenance.py -v`
Expected: import error for `app.maintenance` / the flag test fails.

- [ ] **Step 3: Implement**

`backend/app/maintenance.py`:
```python
"""Process-local maintenance switch, toggled from the admin dashboard.

In-memory on purpose: instant to flip, no DB round-trip, and it resets to off
on restart or deploy, so a deploy returns the site to live automatically and
the site can never get stuck in maintenance. Single uvicorn worker in prod, so
one process holds the truth.
"""
_on = False


def is_on() -> bool:
    return _on


def set_on(value: bool) -> None:
    global _on
    _on = bool(value)
```

In `backend/app/main.py`, import the module and update the helper:
```python
from . import maintenance
```
```python
def _maintenance_on() -> bool:
    return maintenance.is_on() or os.environ.get("MAINTENANCE_MODE", "").strip().lower() in (
        "1", "true", "yes", "on",
    )
```
(Keep the exact env truthy set already in the code; only OR in `maintenance.is_on()`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_maintenance_flag.py tests/test_maintenance.py -v && python -m pytest -q`
Expected: all pass (existing maintenance tests still green).

- [ ] **Step 5: Commit**

```bash
ruff check . && cd .. && git add backend/app/maintenance.py backend/app/main.py backend/tests/test_maintenance_flag.py backend/tests/test_maintenance.py && git commit -m "feat: in-memory maintenance flag read by the middleware" && cd backend
```

---

### Task 2: Admin maintenance endpoints

**Files:**
- Modify: `backend/app/analytics/router.py`
- Test: `backend/tests/test_maintenance_api.py` (new)

**Interfaces:**
- Consumes: `_require_enabled`, `service.config()`, `verify_cookie`, `COOKIE`, `limiter`, `app.maintenance`, `main._maintenance_on` (or re-derive the env check locally to avoid importing main; prefer importing `from ..maintenance import is_on, set_on` and checking the env var inline for `forced_by_env`).
- Produces:
  - `GET /api/admin/maintenance` -> `{"on": bool, "forced_by_env": bool}` where `on` is the effective state and `forced_by_env` is the env-var truthy check.
  - `POST /api/admin/maintenance` body `{"on": bool}` -> sets the in-memory flag, returns the same shape. Rate limited `10/minute`.
  - Both: `_require_enabled()` first (404 when disabled), then `verify_cookie` (401 without a valid cookie).

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_maintenance_api.py`)

Mirror the existing admin-endpoint test setup in `backend/tests/test_analytics_api.py` (how it enables the service and obtains an auth cookie via `/api/admin/login`). Cover:
- POST `/api/admin/maintenance {on:true}` with a valid cookie -> 200, body `{"on": true, "forced_by_env": false}`; then GET `/api/admin/maintenance` -> `on:true`; then the public `GET /` (same app, STATIC_DIR with maintenance.html) -> 503; POST `{on:false}` -> `on:false`; `GET /` -> 200.
- No cookie -> GET and POST both 401.
- Service disabled (analytics off) -> 404.
- Env override: set `MAINTENANCE_MODE=1`, POST `{on:false}` with a valid cookie -> body `{"on": true, "forced_by_env": true}` (env wins). Unset it afterwards; reset the in-memory flag in a finally.

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_maintenance_api.py -v`
Expected: 404/route-not-found for the new endpoints.

- [ ] **Step 3: Implement** in `backend/app/analytics/router.py`.

Add a small input model and the two routes (mirror the `stats` handler's `_require_enabled()` + cookie-verify shape). Sketch:
```python
class MaintenanceIn(BaseModel):
    on: bool


def _forced_by_env() -> bool:
    return os.environ.get("MAINTENANCE_MODE", "").strip().lower() in ("1", "true", "yes", "on")


def _maintenance_state() -> dict:
    from ..maintenance import is_on
    return {"on": is_on() or _forced_by_env(), "forced_by_env": _forced_by_env()}


@router.get("/api/admin/maintenance")
def get_maintenance(request: Request) -> JSONResponse:
    _require_enabled()
    cfg = service.config()
    if not verify_cookie(request.cookies.get(COOKIE, ""), cfg.admin_password, time.time()):
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    return JSONResponse(_maintenance_state())


@router.post("/api/admin/maintenance")
@limiter.limit("10/minute")
def set_maintenance(request: Request, payload: MaintenanceIn) -> JSONResponse:
    _require_enabled()
    cfg = service.config()
    if not verify_cookie(request.cookies.get(COOKIE, ""), cfg.admin_password, time.time()):
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    from ..maintenance import set_on
    set_on(payload.on)
    return JSONResponse(_maintenance_state())
```
Add `import os` if not present, and `from pydantic import BaseModel` (already used for other input models in this file - reuse the existing import). Keep the exact env truthy set consistent with `main._maintenance_on`.

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_maintenance_api.py -v && python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
ruff check . && cd .. && git add backend/app/analytics/router.py backend/tests/test_maintenance_api.py && git commit -m "feat: cookie-authed admin endpoints to get and set maintenance" && cd backend
```

---

### Task 3: Frontend api client

**Files:**
- Modify: `frontend/src/admin/api.ts`
- Test: `frontend/src/admin/api.test.ts` (extend or create following the existing admin test layout)

**Interfaces:**
- Produces: `type Maintenance = { on: boolean; forced_by_env: boolean }`; `getMaintenance(): Promise<Maintenance>` (GET `/api/admin/maintenance`, same credentials/fetch options the existing `fetchStats` uses); `setMaintenance(on: boolean): Promise<Maintenance>` (POST with JSON body `{on}`). Both parse JSON and throw on non-ok, matching how `fetchStats`/`login` handle responses in this file.

- [ ] **Step 1: Failing test** asserting `setMaintenance(true)` POSTs to `/api/admin/maintenance` with body `{"on":true}` and returns the parsed `{on, forced_by_env}` (mock fetch the way the existing admin api/App tests mock it - read the file first).
- [ ] **Step 2: Verify failure.**
- [ ] **Step 3: Implement** the type and two functions mirroring `fetchStats`'s fetch/parse/error idiom.
- [ ] **Step 4:** `npm test -- --run && npm run build`.
- [ ] **Step 5: Commit**

```bash
cd .. && git add frontend/src/admin/api.ts frontend/src/admin/api.test.ts && git commit -m "feat: admin api client for maintenance get and set"
```

---

### Task 4: Site controls panel

**Files:**
- Create: `frontend/src/admin/SiteControls.tsx`
- Modify: `frontend/src/admin/Admin.tsx`
- Test: `frontend/src/admin/SiteControls.test.tsx`, update `frontend/src/admin/Admin.test.tsx` if needed

**Interfaces:**
- Consumes: `getMaintenance`, `setMaintenance`, `Maintenance` from `./api`.
- Produces: `SiteControls()` self-contained component; rendered by `Dashboard` at the top (directly under the `<h1>` header row, above the Tiles grid), wrapped in a `panel` like the other sections.

**Behavior contract:**
- On mount, `getMaintenance()` sets local state; while loading, a neutral placeholder ("Checking...").
- Renders a status: a dot + label. `on` false -> green dot + "Live". `on` true -> amber dot + "In maintenance".
- A toggle control (button styled with existing tokens):
  - When off: button reads "Enable maintenance". Clicking it opens a confirm (`window.confirm` is acceptable, message: "This shows the maintenance page to everyone. Continue?"); on confirm, call `setMaintenance(true)`, update state from the response.
  - When on: button reads "Turn off, go live". Clicking calls `setMaintenance(false)` immediately (no confirm), update state.
- While a toggle request is in flight, disable the button and show a subtle busy state.
- When `forced_by_env` is true: disable the button and show a one-line note: "Held on by the MAINTENANCE_MODE variable. Clear it in Render to unlock this." The status still shows "In maintenance".
- Errors from the endpoints: keep the last known state and show a small inline "Could not update, try again." No throw into the dashboard.
- No emoji, no em dashes.

- [ ] **Step 1: Failing tests** (`SiteControls.test.tsx`, real DOM, mock the api module or fetch as the existing admin tests do). Cover:
  1. Renders "Live" when getMaintenance resolves `{on:false, forced_by_env:false}`.
  2. Renders "In maintenance" when `{on:true,...}`.
  3. Clicking "Enable maintenance" with `window.confirm` stubbed true calls setMaintenance(true) and then shows "In maintenance".
  4. `forced_by_env:true` disables the button and shows the note.
- [ ] **Step 2: Verify failure** (module not found).
- [ ] **Step 3: Implement** `SiteControls.tsx` per the contract; render `<SiteControls />` in `Dashboard` at the top. Use existing panel/dot/button classes (read the file for the exact class names in use).
- [ ] **Step 4:** `npm test -- --run && npm run build` (all existing admin tests still green).
- [ ] **Step 5: Commit**

```bash
cd .. && git add frontend/src/admin/SiteControls.tsx frontend/src/admin/SiteControls.test.tsx frontend/src/admin/Admin.tsx frontend/src/admin/Admin.test.tsx && git commit -m "feat: site controls panel with maintenance toggle in the admin dashboard"
```

---

### Task 5: Full verification (release gate)

- [ ] **Step 1:** Backend `python -m pytest -q && ruff check .` from `backend/` venv - green, warning baseline 6.
- [ ] **Step 2:** Frontend `npm test -- --run && npm run build` from `frontend/` - green, admin bundle builds.
- [ ] **Step 3:** Local live check: run the dev server, log into `/admin` (using the local `.env` ADMIN_PASSWORD if analytics is configured locally; if not, note that the endpoints 404 without analytics and rely on the automated tests). Toggle maintenance on, confirm `GET /` returns the maintenance page (503) in a separate client, confirm the admin session still works, toggle off, confirm `GET /` is 200 again.
- [ ] **Step 4:** After merge + deploy, prod live check while logged into `/admin`: flip the toggle on, confirm a logged-out visitor sees the maintenance page and the site auto-returns to Live when toggled off. Confirm analytics still loads. Do not push or deploy without the owner.
