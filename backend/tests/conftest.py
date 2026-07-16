import pytest

from app.limits import limiter


@pytest.fixture(autouse=True)
def _no_rate_limits():
    limiter.enabled = False
    yield
    limiter.enabled = True
