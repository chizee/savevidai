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
