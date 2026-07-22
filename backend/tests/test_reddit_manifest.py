import httpx
import pytest
import respx

from app.errors import AppError
from app.reddit import (
    _MANIFEST_UA,
    Manifest,
    fetch_manifest,
)

# Real DASHPlaylist.mpd for v.redd.it id enxxsuo5xko31, copied verbatim from
# .superpowers/sdd/mpd-old.xml. Four video Representations (720/480/360/240)
# carry width attrs and extensionless child BaseURL values (DASH_720 .. DASH_240);
# one audio Representation (mimeType audio/mp4) has BaseURL "audio". The MPD
# default namespace is what forces namespace-aware iteration.
OLD_MPD = """<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" mediaPresentationDuration="PT24.534S" minBufferTime="PT1.500S" profiles="urn:mpeg:dash:profile:isoff-on-demand:2011" type="static">
    <Period duration="PT24.534S">
        <AdaptationSet segmentAlignment="true" subsegmentAlignment="true" subsegmentStartsWithSAP="1">
            <Representation bandwidth="2366871" codecs="avc1.4d401f" frameRate="30" height="720" id="VIDEO-1" mimeType="video/mp4" startWithSAP="1" width="404">
                <BaseURL>DASH_720</BaseURL>
                <SegmentBase indexRange="978-1081" indexRangeExact="true">
                    <Initialization range="0-977" />
                </SegmentBase>
            </Representation>
            <Representation bandwidth="1181402" codecs="avc1.4d401f" frameRate="30" height="480" id="VIDEO-2" mimeType="video/mp4" startWithSAP="1" width="270">
                <BaseURL>DASH_480</BaseURL>
                <SegmentBase indexRange="975-1078" indexRangeExact="true">
                    <Initialization range="0-974" />
                </SegmentBase>
            </Representation>
            <Representation bandwidth="788867" codecs="avc1.4d401e" frameRate="30" height="360" id="VIDEO-3" mimeType="video/mp4" startWithSAP="1" width="202">
                <BaseURL>DASH_360</BaseURL>
                <SegmentBase indexRange="978-1081" indexRangeExact="true">
                    <Initialization range="0-977" />
                </SegmentBase>
            </Representation>
            <Representation bandwidth="591509" codecs="avc1.4d401e" frameRate="30" height="240" id="VIDEO-4" mimeType="video/mp4" startWithSAP="1" width="134">
                <BaseURL>DASH_240</BaseURL>
                <SegmentBase indexRange="978-1081" indexRangeExact="true">
                    <Initialization range="0-977" />
                </SegmentBase>
            </Representation>
            </AdaptationSet>
        <AdaptationSet>
            <Representation audioSamplingRate="48000" bandwidth="130322" codecs="mp4a.40.2" id="AUDIO-1" mimeType="audio/mp4" startWithSAP="1">
                <AudioChannelConfiguration schemeIdUri="urn:mpeg:dash:23003:3:audio_channel_configuration:2011" value="2" />
                <BaseURL>audio</BaseURL>
                <SegmentBase indexRange="892-983" indexRangeExact="true">
                    <Initialization range="0-891" />
                </SegmentBase>
            </Representation>
        </AdaptationSet>
    </Period>
</MPD>"""

# Authored fixture mirroring the newer manifest shape: video BaseURLs carry a
# .mp4 extension and audio is DASH_AUDIO_128.mp4. Video reps deliberately omit
# the width attr (to exercise width=None) and the 720 rep is listed before 1080
# (to prove the parser sorts height DESC rather than trusting document order).
NEW_MPD = """<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" mediaPresentationDuration="PT30.000S" minBufferTime="PT1.500S" profiles="urn:mpeg:dash:profile:isoff-on-demand:2011" type="static">
    <Period duration="PT30.000S">
        <AdaptationSet segmentAlignment="true" subsegmentAlignment="true" subsegmentStartsWithSAP="1">
            <Representation bandwidth="1181402" codecs="avc1.4d401f" frameRate="30" height="720" id="VIDEO-2" mimeType="video/mp4" startWithSAP="1">
                <BaseURL>DASH_720.mp4</BaseURL>
                <SegmentBase indexRange="975-1078" indexRangeExact="true">
                    <Initialization range="0-974" />
                </SegmentBase>
            </Representation>
            <Representation bandwidth="4200000" codecs="avc1.640028" frameRate="30" height="1080" id="VIDEO-1" mimeType="video/mp4" startWithSAP="1">
                <BaseURL>DASH_1080.mp4</BaseURL>
                <SegmentBase indexRange="978-1081" indexRangeExact="true">
                    <Initialization range="0-977" />
                </SegmentBase>
            </Representation>
            </AdaptationSet>
        <AdaptationSet>
            <Representation audioSamplingRate="48000" bandwidth="130322" codecs="mp4a.40.2" id="AUDIO-1" mimeType="audio/mp4" startWithSAP="1">
                <AudioChannelConfiguration schemeIdUri="urn:mpeg:dash:23003:3:audio_channel_configuration:2011" value="2" />
                <BaseURL>DASH_AUDIO_128.mp4</BaseURL>
                <SegmentBase indexRange="892-983" indexRangeExact="true">
                    <Initialization range="0-891" />
                </SegmentBase>
            </Representation>
        </AdaptationSet>
    </Period>
</MPD>"""

# Audio-less variant of NEW_MPD: a single video Representation, no audio set.
VIDEO_ONLY_MPD = """<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static">
    <Period>
        <AdaptationSet>
            <Representation height="720" id="VIDEO-1" mimeType="video/mp4" width="1280">
                <BaseURL>DASH_720.mp4</BaseURL>
            </Representation>
        </AdaptationSet>
    </Period>
</MPD>"""

# Audio-only manifest: no video Representation at all.
AUDIO_ONLY_MPD = """<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static">
    <Period>
        <AdaptationSet>
            <Representation id="AUDIO-1" mimeType="audio/mp4">
                <BaseURL>DASH_AUDIO_128.mp4</BaseURL>
            </Representation>
        </AdaptationSet>
    </Period>
</MPD>"""

# One video rep has a BaseURL with a path separator (a directory-traversal /
# absolute-path shape). Such a value would later become a URL path segment, so
# it must be rejected outright rather than trusted.
SLASH_BASEURL_MPD = """<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static">
    <Period>
        <AdaptationSet>
            <Representation height="720" mimeType="video/mp4">
                <BaseURL>../../evil/DASH_720.mp4</BaseURL>
            </Representation>
        </AdaptationSet>
    </Period>
</MPD>"""

# One video rep whose BaseURL is entirely dot characters (".."). Like the slash
# case this passes the naive charset but would splice into a byte-fetch URL as a
# path-traversal segment, so it must be rejected as a corrupt/hostile manifest.
DOTS_BASEURL_MPD = """<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static">
    <Period>
        <AdaptationSet>
            <Representation height="720" mimeType="video/mp4">
                <BaseURL>..</BaseURL>
            </Representation>
        </AdaptationSet>
    </Period>
</MPD>"""

# A video rep whose BaseURL is a single dot (".") - the current-directory shape.
DOT_BASEURL_MPD = """<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static">
    <Period>
        <AdaptationSet>
            <Representation height="720" mimeType="video/mp4">
                <BaseURL>.</BaseURL>
            </Representation>
        </AdaptationSet>
    </Period>
</MPD>"""

# One video rep with a dots-only BaseURL ("..") alongside a well-formed rep. A
# malformed BaseURL is fatal (same as the slash case), so the whole parse raises
# UPSTREAM rather than salvaging the valid rep.
DOTS_MIX_MPD = """<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static">
    <Period>
        <AdaptationSet>
            <Representation height="1080" mimeType="video/mp4">
                <BaseURL>DASH_1080.mp4</BaseURL>
            </Representation>
            <Representation height="720" mimeType="video/mp4">
                <BaseURL>..</BaseURL>
            </Representation>
        </AdaptationSet>
    </Period>
</MPD>"""

# A video rep whose BaseURL is present but empty text.
EMPTY_BASEURL_MPD = """<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static">
    <Period>
        <AdaptationSet>
            <Representation height="720" mimeType="video/mp4">
                <BaseURL></BaseURL>
            </Representation>
        </AdaptationSet>
    </Period>
</MPD>"""

# One well-formed video rep plus one video rep missing height and another
# missing BaseURL. The incomplete reps must be skipped, not crash the parse.
INCOMPLETE_REPS_MPD = """<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static">
    <Period>
        <AdaptationSet>
            <Representation height="480" mimeType="video/mp4" width="640">
                <BaseURL>DASH_480.mp4</BaseURL>
            </Representation>
            <Representation mimeType="video/mp4" width="640">
                <BaseURL>DASH_NOHEIGHT.mp4</BaseURL>
            </Representation>
            <Representation height="240" mimeType="video/mp4" width="320">
            </Representation>
        </AdaptationSet>
    </Period>
</MPD>"""


def _mock(vid: str, *, status: int = 200, text: str = "", side_effect=None):
    route = respx.get(f"https://v.redd.it/{vid}/DASHPlaylist.mpd")
    if side_effect is not None:
        return route.mock(side_effect=side_effect)
    return route.mock(return_value=httpx.Response(status, text=text))


def test_manifest_ua_exact():
    assert _MANIFEST_UA == "SaveVidAI/1.0 (+https://savevidai.israfill.dev)"


@respx.mock
def test_old_mpd_four_videos_and_audio():
    _mock("enxxsuo5xko31", text=OLD_MPD)
    m = fetch_manifest("enxxsuo5xko31")
    assert isinstance(m, Manifest)
    assert [(r.height, r.width, r.base_url) for r in m.videos] == [
        (720, 404, "DASH_720"),
        (480, 270, "DASH_480"),
        (360, 202, "DASH_360"),
        (240, 134, "DASH_240"),
    ]
    assert m.audio_base == "audio"


@respx.mock
def test_new_mpd_mp4_names_widthless_and_sorted_desc():
    _mock("newvidid1234", text=NEW_MPD)
    m = fetch_manifest("newvidid1234")
    assert [(r.height, r.width, r.base_url) for r in m.videos] == [
        (1080, None, "DASH_1080.mp4"),
        (720, None, "DASH_720.mp4"),
    ]
    assert m.audio_base == "DASH_AUDIO_128.mp4"


@respx.mock
def test_heights_sorted_descending():
    _mock("newvidid1234", text=NEW_MPD)
    heights = [r.height for r in fetch_manifest("newvidid1234").videos]
    assert heights == sorted(heights, reverse=True)


@respx.mock
def test_audio_absent_yields_none_audio_base():
    _mock("videoonly123", text=VIDEO_ONLY_MPD)
    m = fetch_manifest("videoonly123")
    assert m.audio_base is None
    assert [r.base_url for r in m.videos] == ["DASH_720.mp4"]


@respx.mock
def test_no_video_representations_maps_no_video():
    _mock("audioonly123", text=AUDIO_ONLY_MPD)
    with pytest.raises(AppError) as exc:
        fetch_manifest("audioonly123")
    assert exc.value.code == "no_video"


@respx.mock
def test_baseurl_with_slash_rejected_as_upstream():
    # Documented choice: a manifest that parses as XML but carries a BaseURL
    # outside [A-Za-z0-9_.]+ is a corrupt/hostile upstream response, not a
    # "post has no video" case, so it maps to UPSTREAM rather than NO_VIDEO.
    _mock("slashvid1234", text=SLASH_BASEURL_MPD)
    with pytest.raises(AppError) as exc:
        fetch_manifest("slashvid1234")
    assert exc.value.code == "upstream_error"


@respx.mock
def test_dots_only_baseurl_rejected_as_upstream():
    # A BaseURL of ".." passes the bare charset but is a path-traversal segment
    # once spliced into the byte-fetch URL, so it is treated exactly like the
    # slash case: a corrupt/hostile manifest mapping to UPSTREAM, not NO_VIDEO.
    _mock("dotsvid12345", text=DOTS_BASEURL_MPD)
    with pytest.raises(AppError) as exc:
        fetch_manifest("dotsvid12345")
    assert exc.value.code == "upstream_error"


@respx.mock
def test_single_dot_baseurl_rejected_as_upstream():
    _mock("dotvid123456", text=DOT_BASEURL_MPD)
    with pytest.raises(AppError) as exc:
        fetch_manifest("dotvid123456")
    assert exc.value.code == "upstream_error"


@respx.mock
def test_dots_only_baseurl_is_fatal_even_beside_valid_rep():
    # A malformed BaseURL is fatal (matching the slash semantics), so a manifest
    # mixing a dots-only rep with a valid one raises rather than salvaging.
    _mock("dotsmix12345", text=DOTS_MIX_MPD)
    with pytest.raises(AppError) as exc:
        fetch_manifest("dotsmix12345")
    assert exc.value.code == "upstream_error"


@respx.mock
def test_empty_baseurl_rejected_as_upstream():
    _mock("emptyvid1234", text=EMPTY_BASEURL_MPD)
    with pytest.raises(AppError) as exc:
        fetch_manifest("emptyvid1234")
    assert exc.value.code == "upstream_error"


@respx.mock
def test_incomplete_reps_skipped_not_crash():
    _mock("incompl12345", text=INCOMPLETE_REPS_MPD)
    m = fetch_manifest("incompl12345")
    # Only the one complete rep survives; the height-less and BaseURL-less
    # reps are silently skipped.
    assert [(r.height, r.base_url) for r in m.videos] == [(480, "DASH_480.mp4")]


@respx.mock
def test_non_xml_body_maps_upstream():
    _mock("garbagevid12", text="<html>not a manifest</html> not xml < & >")
    with pytest.raises(AppError) as exc:
        fetch_manifest("garbagevid12")
    assert exc.value.code == "upstream_error"


@respx.mock
def test_empty_body_maps_upstream():
    _mock("emptybody123", text="")
    with pytest.raises(AppError) as exc:
        fetch_manifest("emptybody123")
    assert exc.value.code == "upstream_error"


@respx.mock
def test_non_200_maps_upstream():
    _mock("notfound1234", status=404, text=OLD_MPD)
    with pytest.raises(AppError) as exc:
        fetch_manifest("notfound1234")
    assert exc.value.code == "upstream_error"


@respx.mock
def test_network_error_maps_upstream():
    _mock("neterr123456", side_effect=httpx.ConnectError("down"))
    with pytest.raises(AppError) as exc:
        fetch_manifest("neterr123456")
    assert exc.value.code == "upstream_error"


@respx.mock
def test_sends_manifest_ua_and_no_redirects():
    route = _mock("enxxsuo5xko31", text=OLD_MPD)
    fetch_manifest("enxxsuo5xko31")
    request = route.calls.last.request
    assert request.headers["User-Agent"] == _MANIFEST_UA


@respx.mock
def test_does_not_follow_redirects():
    respx.get("https://v.redd.it/enxxsuo5xko31/DASHPlaylist.mpd").mock(
        return_value=httpx.Response(302, headers={"location": "https://v.redd.it/x/DASHPlaylist.mpd"})
    )
    with pytest.raises(AppError) as exc:
        fetch_manifest("enxxsuo5xko31")
    assert exc.value.code == "upstream_error"


def test_invalid_vid_rejected_defense_in_depth():
    # No HTTP is issued: the entry re-validation rejects a bad id before any
    # request is built. Pinned as UPSTREAM (an internal-invariant violation,
    # since callers pass ids already matching the v.redd.it charset).
    with pytest.raises(AppError) as exc:
        fetch_manifest("bad/id")
    assert exc.value.code == "upstream_error"
