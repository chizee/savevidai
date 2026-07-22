"""Resolve Reddit posts to downloadable media via a hybrid, two-tier design.

Tier 1 (this module, always on): an anonymous fetch of vxreddit.com. vxreddit
serves Discord-style Open Graph meta tags to bot user agents, so a single GET
with a Discordbot UA yields the post's title, author, subreddit, media type and,
for v.redd.it videos, the bare video id encoded inside the og:video URL. No
Reddit credentials are involved, nothing is rate-limited against a Reddit app,
and the only trust placed in the upstream is the og:video URL, which we treat as
attacker-controlled: the video id is accepted only after the embedded video_url
decodes to a genuine v.redd.it host and a strict id charset.

Tier 2 (added later, env-gated): when Reddit OAuth credentials are configured,
a direct OAuth call to Reddit's own API can upgrade or replace the anonymous
result (higher-fidelity metadata, gallery/crosspost handling). That path is
intentionally optional and absent here; galleries currently surface as
errors.UNSUPPORTED_POST until the OAuth half lands. Keeping the anonymous path
standalone means the downloader keeps working with zero configuration.

Stdlib only for parsing (regex over meta tags plus html.unescape); no new deps.
"""
import html
import logging
import re
from urllib.parse import parse_qs, urlparse

import httpx

from .errors import UPSTREAM, app_error

logger = logging.getLogger("savevidai.reddit")

_VX_BASE = "https://www.vxreddit.com"
# vxreddit serves og tags to Discord's link unfurler; a browser-like UA gets a
# bare meta-refresh instead. This exact string is the contract with the upstream.
_VX_UA = "Discordbot/2.0 (SaveVidAI; +https://savevidai.israfill.dev)"

# Match each <meta ...> tag, then pull its attributes generically so property/
# content order does not matter and single or double quotes both parse.
_META_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTR_RE = re.compile(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')

# og:site_name looks like "u/<author> on r/<sub> - <emoji stats>"; we take only
# the leading handle and subreddit and tolerate the pattern being absent.
_SITE_RE = re.compile(r"^u/([A-Za-z0-9_-]+)\s+on\s+r/([A-Za-z0-9_]+)")

# A v.redd.it video id: the first path segment of the decoded video_url.
_VREDD_ID_RE = re.compile(r"[A-Za-z0-9]{8,20}")


def _parse_og(html_text: str) -> dict[str, str]:
    """Map og-style ``property`` -> ``content`` for every meta tag that has both.

    First occurrence wins, attribute order is irrelevant, and html entities in
    the content are unescaped. Tags carrying only ``name`` (twitter:*, theme
    colours) are ignored: only ``property`` meta tags are recorded.
    """
    result: dict[str, str] = {}
    for tag in _META_RE.findall(html_text):
        attrs: dict[str, str] = {}
        for key, dq, sq in _ATTR_RE.findall(tag):
            attrs[key.lower()] = dq if dq else sq
        prop = attrs.get("property")
        content = attrs.get("content")
        if prop and content is not None and prop not in result:
            result[prop] = html.unescape(content)
    return result


def _parse_site_name(site: str) -> tuple[str | None, str | None]:
    match = _SITE_RE.match(site or "")
    if not match:
        return (None, None)
    return (match.group(1), match.group(2))


def _vredd_id(og_video: str | None) -> str | None:
    """Recover a v.redd.it video id from an og:video URL, or None.

    The og:video URL is upstream-controlled, so its embedded ``video_url`` is
    validated hard: it must decode to a ``v.redd.it`` host and its first path
    segment must be a bare id of the expected charset/length. Anything else
    (missing param, foreign host, junk segment) yields None rather than a value
    that would later be pasted into a byte-fetch URL.
    """
    if not og_video:
        return None
    params = parse_qs(urlparse(og_video).query)
    values = params.get("video_url")
    if not values:
        return None
    inner = urlparse(values[0])  # parse_qs has already percent-decoded this
    if (inner.hostname or "").lower() != "v.redd.it":
        return None
    segments = [p for p in inner.path.split("/") if p]
    if not segments or not _VREDD_ID_RE.fullmatch(segments[0]):
        return None
    return segments[0]


def _build(og: dict[str, str]) -> dict:
    author, subreddit = _parse_site_name(og.get("og:site_name", ""))
    return {
        "title": og.get("og:title", ""),
        "author": author,
        "subreddit": subreddit,
        "og_type": og.get("og:type"),
        "vredd_id": _vredd_id(og.get("og:video")),
        "image_url": og.get("og:image"),
    }


def fetch_vx(path: str) -> dict:
    """GET ``vxreddit.com{path}`` as a bot and return its parsed og tags.

    Any transport failure, non-200 status, or a body carrying no og tags maps to
    a clean upstream_error. A body with no og tags is the plain-UA signature (a
    bare meta-refresh to reddit.com), which most likely means the Discordbot UA
    has stopped being honoured; that case is logged loudly.
    """
    url = f"{_VX_BASE}{path}"
    try:
        resp = httpx.get(url, headers={"User-Agent": _VX_UA},
                         timeout=12.0, follow_redirects=False)
    except httpx.HTTPError as exc:
        logger.warning("vxreddit fetch failed for %s: %r", path, exc)
        raise app_error(UPSTREAM) from exc
    if resp.status_code != 200:
        logger.warning("vxreddit non-200 (%s) for %s", resp.status_code, path)
        raise app_error(UPSTREAM)
    og = _parse_og(resp.text)
    if not any(key.startswith("og:") for key in og):
        logger.warning(
            "vxreddit returned no og tags for %s; the bot UA %r may no longer be "
            "honoured (got a plain meta-refresh body)", path, _VX_UA)
        raise app_error(UPSTREAM)
    return _build(og)
