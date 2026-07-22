import re
from urllib.parse import urlparse


class InvalidTweetURL(ValueError):
    pass


_HOSTS = {
    "twitter.com", "www.twitter.com", "mobile.twitter.com", "m.twitter.com",
    "x.com", "www.x.com", "mobile.x.com", "m.x.com",
    "fxtwitter.com", "www.fxtwitter.com",
    "vxtwitter.com", "www.vxtwitter.com",
    "fixupx.com", "www.fixupx.com",
    "twittpr.com", "www.twittpr.com",
}

# /<handle>/status/<id> or /i/web/status/<id>, tolerating trailing segments like /video/1
_PATH = re.compile(r"^/(?:[A-Za-z0-9_]{1,15}|i/web)/status(?:es)?/(\d{1,25})(?:/|$)")


def parse_tweet_url(raw: str) -> str:
    """Return the tweet ID for any supported tweet URL shape, else raise InvalidTweetURL."""
    raw = raw.strip()
    if not raw:
        raise InvalidTweetURL("empty input")
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise InvalidTweetURL(raw)
    if parsed.hostname.lower() not in _HOSTS:
        raise InvalidTweetURL(raw)
    match = _PATH.match(parsed.path)
    if not match:
        raise InvalidTweetURL(raw)
    return match.group(1)


TIKTOK_HOSTS = {
    "tiktok.com", "www.tiktok.com", "m.tiktok.com",
    "vm.tiktok.com", "vt.tiktok.com",
}


def parse_tiktok_url(raw: str) -> str:
    """Validate the host is TikTok and return a normalized https URL.

    Unlike Twitter (which extracts a numeric ID), TikTok's resolver takes the
    URL directly and follows short links (vm./vt.). We host-allowlist first so
    an arbitrary user URL is never forwarded to the third-party resolver.
    """
    raw = raw.strip()
    if not raw:
        raise InvalidTweetURL("empty input")
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise InvalidTweetURL(raw)
    if parsed.hostname.lower() not in TIKTOK_HOSTS:
        raise InvalidTweetURL(raw)
    return raw if raw.startswith("https://") else raw.replace("http://", "https://", 1)
