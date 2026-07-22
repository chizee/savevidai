import pytest

from app.errors import AppError
from app.tiktok import map_tiktok

OK = {
    "code": 0,
    "data": {
        "id": "7280000000000000000",
        "title": "a caption",
        "cover": "https://p19-common-sign.tiktokcdn-us.com/cover/x.jpg",
        "duration": 15,
        "play": "https://v16m.tiktokcdn-us.com/video/play/x.mp4",
        "hdplay": "https://v16m-default.tiktokcdn-us.com/video/hdplay/x.mp4",
        "wmplay": "https://v16m.tiktokcdn-us.com/video/wmplay/x.mp4",
        "size": 2953029,
        "hd_size": 2004627,
        "author": {
            "unique_id": "user",
            "nickname": "User Name",
            "avatar": "https://p19-common-sign.tiktokcdn-us.com/a.jpg",
        },
    },
}
NO_VID = {"code": 0, "data": {"id": "1", "title": "", "author": {"unique_id": "u", "nickname": "U"}}}
ERR = {"code": -1, "msg": "url parse err"}


def test_map_ok_prefers_no_watermark_hd_then_sd():
    res = map_tiktok("7280000000000000000", OK)
    assert res.handle == "user"
    assert res.author == "User Name"
    assert res.text == "a caption"
    assert res.items[0].kind == "video"
    assert res.items[0].duration_seconds == 15
    labels = [v.label for v in res.items[0].variants]
    assert labels == ["hd", "sd"]
    # watermarked url is never present
    assert all("wmplay" not in v.url for v in res.items[0].variants)
    assert res.items[0].variants[0].url.endswith("/hdplay/x.mp4")


def test_map_ok_sets_sizes_from_response():
    res = map_tiktok("7280000000000000000", OK)
    hd, sd = res.items[0].variants
    assert hd.size_bytes == 2004627  # from hd_size
    assert sd.size_bytes == 2953029  # from size


def test_map_no_video_raises():
    with pytest.raises(AppError) as exc:
        map_tiktok("1", NO_VID)
    assert exc.value.code == "no_video"


def test_map_error_code_raises_upstream():
    with pytest.raises(AppError) as exc:
        map_tiktok("1", ERR)
    assert exc.value.code in ("upstream_error", "not_found")
