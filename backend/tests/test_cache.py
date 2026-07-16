import time

from app.cache import TTLCache


def test_get_set_roundtrip():
    cache = TTLCache(maxsize=4, ttl=60)
    cache.set("a", {"x": 1})
    assert cache.get("a") == {"x": 1}
    assert cache.get("missing") is None


def test_expiry():
    cache = TTLCache(maxsize=4, ttl=0.05)
    cache.set("a", 1)
    assert cache.get("a") == 1
    time.sleep(0.06)
    assert cache.get("a") is None


def test_lru_eviction():
    cache = TTLCache(maxsize=2, ttl=60)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")  # refresh "a"
    cache.set("c", 3)  # evicts "b", the least recently used
    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3
