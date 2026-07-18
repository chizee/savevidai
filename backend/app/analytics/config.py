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
