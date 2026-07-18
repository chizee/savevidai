import hashlib
import hmac
import re

from app.analytics.hashing import today_utc, visitor_hash

SALT = "random-salt"


def test_len_and_hex():
    h = visitor_hash(SALT, "1.2.3.4", "2026-07-17")
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)


def test_stable_within_day():
    a = visitor_hash(SALT, "1.2.3.4", "2026-07-17")
    b = visitor_hash(SALT, "1.2.3.4", "2026-07-17")
    assert a == b


def test_rotates_across_days():
    a = visitor_hash(SALT, "1.2.3.4", "2026-07-17")
    b = visitor_hash(SALT, "1.2.3.4", "2026-07-18")
    assert a != b


def test_salt_changes_output():
    a = visitor_hash(SALT, "1.2.3.4", "2026-07-17")
    b = visitor_hash("other-salt", "1.2.3.4", "2026-07-17")
    assert a != b


def test_never_contains_ip():
    h = visitor_hash(SALT, "203.0.113.77", "2026-07-17")
    assert "203.0.113.77" not in h


def test_matches_known_hmac():
    # Golden value pinning the exact HMAC construction. A bare sha256 concat
    # (or any other keying/message change) produces a different value and fails.
    salt, ip, day = "s3cr3t", "1.2.3.4", "2026-07-17"
    expected = hmac.new(
        salt.encode(), f"{day}|{ip}".encode(), hashlib.sha256
    ).hexdigest()[:16]
    assert visitor_hash(salt, ip, day) == expected


def test_today_utc_format():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", today_utc())
