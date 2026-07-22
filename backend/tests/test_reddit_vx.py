import httpx
import pytest
import respx

from app.errors import UNSUPPORTED_POST, AppError
from app.reddit import _VX_UA, _parse_og, fetch_vx

# Real vxreddit response for post d8qo81 (og tags copied from
# .superpowers/sdd/vx-video.html). The og:site_name emoji stat tail is elided;
# it plays no part in the u/<author> on r/<sub> parse and keeps this file
# emoji-free. The og:title keeps the real curly apostrophes (U+2019) so the
# unescape path is exercised on genuine content.
REAL_VX = (
    '<!doctype html><html lang="en"><head>'
    '<meta charset="UTF-8" />'
    '<meta property="og:site_name" content="u/Dynna13337 on r/funny - up 87631 | comments 1773" />'
    '<meta content="\\#FF4500" name="theme-color" />'
    '<meta property="og:url" content="https://www.reddit.com/comments/d8qo81" />'
    '<meta property="og:title" content="Baby crocodiles sound like they’re shooting laser guns and it’s the best thing ever" />'
    '<meta property="og:type" content="video.other" />'
    '<meta name="twitter:card" content="player" />'
    '<meta name="twitter:player:stream" content="https://vxreddit.com/redditvideo.mp4?video_url=https%3A%2F%2Fv.redd.it%2Fenxxsuo5xko31%2FHLS_540_v4.m3u8&amp;audio_url=x" />'
    '<meta property="og:video" content="https://vxreddit.com/redditvideo.mp4?video_url=https%3A%2F%2Fv.redd.it%2Fenxxsuo5xko31%2FHLS_540_v4.m3u8&amp;audio_url=https%3A%2F%2Fv.redd.it%2Fenxxsuo5xko31%2FHLS_AUDIO_160_K_v4.m3u8" />'
    '<meta property="og:video:type" content="video/mp4" />'
    '<meta property="og:image" content="https://external-preview.redd.it/UHct8ILPjYNqSBGXtDYyf5dEN_2lEqW65gZne_Fqvcc.png?format=pjpg&amp;auto=webp&amp;s=9f7025752ce0487a555e6b95152ef86acbea7c25" />'
    '</head><body>Redirecting...</body></html>'
)

# Plain-UA signature: a meta-refresh body with no og tags at all.
PLAIN_REFRESH = (
    '<!doctype html><html><head>'
    '<meta http-equiv="refresh" content="0;url=https://www.reddit.com/comments/d8qo81" />'
    '</head><body>Redirecting...</body></html>'
)

# Synthetic image post: og:type website + og:image on i.redd.it, no og:video.
IMAGE_POST = (
    '<html><head>'
    '<meta property="og:site_name" content="u/somebody on r/pics - up 10" />'
    '<meta property="og:title" content="a still image" />'
    '<meta property="og:type" content="website" />'
    '<meta property="og:image" content="https://i.redd.it/abc123def456.jpg" />'
    '</head></html>'
)


def test_unsupported_post_spec():
    assert UNSUPPORTED_POST == ("unsupported_post", "Reddit galleries are not supported yet.", 422)


def test_vx_ua_exact():
    assert _VX_UA == "Discordbot/2.0 (SaveVidAI; +https://savevidai.israfill.dev)"


def test_parse_og_real_fixture_recovers_fields():
    og = _parse_og(REAL_VX)
    assert og["og:type"] == "video.other"
    assert og["og:site_name"] == "u/Dynna13337 on r/funny - up 87631 | comments 1773"
    assert og["og:title"] == "Baby crocodiles sound like they’re shooting laser guns and it’s the best thing ever"


def test_parse_og_unescapes_entities():
    html = '<meta property="og:title" content="Tom &amp; Jerry say &#39;hi&#39; &lt;3" />'
    assert _parse_og(html)["og:title"] == "Tom & Jerry say 'hi' <3"


def test_parse_og_tolerates_attribute_order():
    html = '<meta content="video.other" property="og:type" />'
    assert _parse_og(html)["og:type"] == "video.other"


def test_parse_og_first_occurrence_wins():
    html = (
        '<meta property="og:title" content="first" />'
        '<meta property="og:title" content="second" />'
    )
    assert _parse_og(html)["og:title"] == "first"


def test_parse_og_ignores_name_only_meta():
    html = '<meta name="twitter:card" content="player" />'
    assert _parse_og(html) == {}


@respx.mock
def test_fetch_vx_real_fixture_full_shape():
    respx.get("https://www.vxreddit.com/comments/d8qo81").mock(
        return_value=httpx.Response(200, text=REAL_VX)
    )
    result = fetch_vx("/comments/d8qo81")
    assert result == {
        "title": "Baby crocodiles sound like they’re shooting laser guns and it’s the best thing ever",
        "author": "Dynna13337",
        "subreddit": "funny",
        "og_type": "video.other",
        "vredd_id": "enxxsuo5xko31",
        "image_url": "https://external-preview.redd.it/UHct8ILPjYNqSBGXtDYyf5dEN_2lEqW65gZne_Fqvcc.png?format=pjpg&auto=webp&s=9f7025752ce0487a555e6b95152ef86acbea7c25",
    }


@respx.mock
def test_fetch_vx_sends_bot_ua_and_no_redirects():
    route = respx.get("https://www.vxreddit.com/comments/d8qo81").mock(
        return_value=httpx.Response(200, text=REAL_VX)
    )
    fetch_vx("/comments/d8qo81")
    request = route.calls.last.request
    assert request.headers["User-Agent"] == _VX_UA


@respx.mock
def test_fetch_vx_does_not_follow_redirects():
    # follow_redirects=False: a 302 must surface as UPSTREAM, not be chased.
    respx.get("https://www.vxreddit.com/comments/d8qo81").mock(
        return_value=httpx.Response(302, headers={"location": "https://www.reddit.com/comments/d8qo81"})
    )
    with pytest.raises(AppError) as exc:
        fetch_vx("/comments/d8qo81")
    assert exc.value.code == "upstream_error"


@respx.mock
def test_fetch_vx_404_maps_upstream():
    respx.get("https://www.vxreddit.com/comments/nope").mock(return_value=httpx.Response(404))
    with pytest.raises(AppError) as exc:
        fetch_vx("/comments/nope")
    assert exc.value.code == "upstream_error"


@respx.mock
def test_fetch_vx_meta_refresh_plain_body_maps_upstream(caplog):
    respx.get("https://www.vxreddit.com/comments/d8qo81").mock(
        return_value=httpx.Response(200, text=PLAIN_REFRESH)
    )
    with pytest.raises(AppError) as exc:
        fetch_vx("/comments/d8qo81")
    assert exc.value.code == "upstream_error"
    # A warning must flag that the bot UA may no longer be honored.
    assert any("UA" in r.message or "ua" in r.message.lower() for r in caplog.records)


@respx.mock
def test_fetch_vx_network_error_maps_upstream():
    respx.get("https://www.vxreddit.com/comments/d8qo81").mock(
        side_effect=httpx.ConnectError("down")
    )
    with pytest.raises(AppError) as exc:
        fetch_vx("/comments/d8qo81")
    assert exc.value.code == "upstream_error"


@respx.mock
def test_fetch_vx_image_post_populates_image_url():
    respx.get("https://www.vxreddit.com/comments/img1").mock(
        return_value=httpx.Response(200, text=IMAGE_POST)
    )
    result = fetch_vx("/comments/img1")
    assert result["image_url"] == "https://i.redd.it/abc123def456.jpg"
    assert result["vredd_id"] is None
    assert result["og_type"] == "website"
    assert result["author"] == "somebody"
    assert result["subreddit"] == "pics"


def test_missing_og_video_yields_none_vredd_id():
    og = _parse_og(IMAGE_POST)
    from app.reddit import _vredd_id
    assert _vredd_id(og.get("og:video")) is None


def test_non_vreddit_video_url_host_yields_none_vredd_id():
    # Security: a video_url pointing anywhere but v.redd.it must not yield an id.
    from app.reddit import _vredd_id
    evil = "https://vxreddit.com/redditvideo.mp4?video_url=https%3A%2F%2Fevil.example.com%2Fabcd1234efgh%2FHLS.m3u8"
    assert _vredd_id(evil) is None


def test_vreddit_video_url_id_extracted():
    from app.reddit import _vredd_id
    good = "https://vxreddit.com/redditvideo.mp4?video_url=https%3A%2F%2Fv.redd.it%2Fenxxsuo5xko31%2FHLS_540_v4.m3u8"
    assert _vredd_id(good) == "enxxsuo5xko31"


def test_vreddit_id_rejects_bad_first_segment():
    from app.reddit import _vredd_id
    # first path segment too short (<8) must be rejected
    short = "https://vxreddit.com/redditvideo.mp4?video_url=https%3A%2F%2Fv.redd.it%2Fabc%2FHLS.m3u8"
    assert _vredd_id(short) is None
