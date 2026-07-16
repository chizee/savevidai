import pytest

from app.errors import AppError
from app.extractor import map_info

SINGLE = {
    "id": "111",
    "uploader": "Ada Lovelace",
    "uploader_id": "ada",
    "description": "engine demo",
    "thumbnail": "https://pbs.twimg.com/thumb.jpg",
    "duration": 12.5,
    "formats": [
        {"url": "https://video.twimg.com/ext_tw_video/1/vid/480x270/a.mp4",
         "vcodec": "h264", "width": 480, "height": 270, "protocol": "https"},
        {"url": "https://video.twimg.com/ext_tw_video/1/pl/x.m3u8",
         "vcodec": "h264", "height": 720, "protocol": "m3u8_native"},
        {"url": "https://video.twimg.com/ext_tw_video/1/vid/1920x1080/b.mp4",
         "vcodec": "h264", "width": 1920, "height": 1080, "protocol": "https"},
        {"url": "https://video.twimg.com/audio/only.mp4", "vcodec": "none", "acodec": "mp4a"},
    ],
}

MULTI = {
    "_type": "playlist",
    "id": "222",
    "uploader": "Ada Lovelace",
    "uploader_id": "ada",
    "description": "two clips",
    "entries": [
        {"thumbnail": "https://pbs.twimg.com/t1.jpg", "duration": 5,
         "formats": [{"url": "https://video.twimg.com/ext_tw_video/2/vid/640x360/a.mp4",
                      "vcodec": "h264", "width": 640, "height": 360, "protocol": "https"}]},
        {"thumbnail": "https://pbs.twimg.com/t2.jpg", "duration": 8,
         "formats": [{"url": "https://video.twimg.com/ext_tw_video/3/vid/1280x720/b.mp4",
                      "vcodec": "h264", "width": 1280, "height": 720, "protocol": "https"}]},
    ],
}

GIF = {
    "id": "333",
    "uploader": "Ada Lovelace",
    "uploader_id": "ada",
    "formats": [{"url": "https://video.twimg.com/tweet_video/AAA.mp4",
                 "vcodec": "h264", "width": 480, "height": 480, "protocol": "https"}],
}

NO_VIDEO_INFO = {"id": "444", "uploader": "Ada", "uploader_id": "ada", "formats": []}


def test_single_video_mapping():
    res = map_info("111", SINGLE)
    assert res.id == "111"
    assert res.author == "Ada Lovelace"
    assert res.handle == "ada"
    assert res.text == "engine demo"
    assert len(res.items) == 1
    item = res.items[0]
    assert item.kind == "video"
    assert item.thumbnail == "https://pbs.twimg.com/thumb.jpg"
    assert item.duration_seconds == 12.5
    # HLS and audio-only formats are excluded; sorted best-first
    assert [v.label for v in item.variants] == ["1080p", "270p"]
    assert item.variants[0].url.endswith("/1920x1080/b.mp4")


def test_multi_video_mapping():
    res = map_info("222", MULTI)
    assert [i.index for i in res.items] == [1, 2]
    assert res.items[1].variants[0].label == "720p"


def test_gif_detection():
    res = map_info("333", GIF)
    assert res.items[0].kind == "gif"


def test_no_video_raises():
    with pytest.raises(AppError) as exc:
        map_info("444", NO_VIDEO_INFO)
    assert exc.value.code == "no_video"
