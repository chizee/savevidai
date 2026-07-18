"""Boot-time safety: analytics enablement must never take the public site down.

TursoStore.init_schema() does a real network call; if Turso is momentarily
unreachable, the token is stale, or a statement errors, it raises. That must
not propagate out of create_app(), or uvicorn can't start and /api/resolve,
/api/proxy, and the static site all go down with it - not just analytics.
"""
from fastapi.testclient import TestClient

from app import main as main_mod
from app.analytics import service as service_mod
from app.analytics.config import AnalyticsConfig


class _ExplodingStore:
    """Stands in for TursoStore when Turso is unreachable at boot - no real
    network involved."""

    def init_schema(self) -> None:
        raise RuntimeError("turso unreachable")

    def execute_many(self, statements):
        raise RuntimeError("turso unreachable")

    def query(self, sql, args):
        raise RuntimeError("turso unreachable")


def test_create_app_survives_analytics_init_failure(monkeypatch):
    # Isolate a fresh service instance so this test doesn't depend on
    # whatever state other tests left the real singleton in, and wire it
    # into both places that hold a reference to it (mirrors how the Task 8
    # route tests inject config/store: see enabled_client in
    # test_analytics_api.py).
    fresh_service = service_mod.AnalyticsService()
    monkeypatch.setattr(service_mod, "service", fresh_service)
    monkeypatch.setattr("app.analytics.router.service", fresh_service)

    # Force create_app()'s "analytics enabled" branch to run, but with a
    # store whose init_schema() blows up the way a Turso outage would.
    monkeypatch.setattr(
        main_mod, "load_config",
        lambda env: AnalyticsConfig("libsql://x", "t", "pw-long", "salt"),
    )
    monkeypatch.setattr(main_mod, "make_store", lambda cfg: _ExplodingStore())

    app = main_mod.create_app()  # must NOT raise even though init_schema() blows up

    assert fresh_service.enabled is False

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/event", json={"type": "visit"}).status_code == 404
