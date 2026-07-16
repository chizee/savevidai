import pytest

from app.errors import (
    NO_VIDEO,
    NOT_FOUND,
    PRIVATE,
    RATE_LIMITED,
    UPSTREAM,
    app_error,
    map_extractor_error,
)

CASES = [
    ("ERROR: No video could be found in this tweet", NO_VIDEO),
    ("ERROR: No status found with that ID.", NOT_FOUND),
    ("requested tweet does not exist", NOT_FOUND),
    ("NSFW tweet requires authentication", PRIVATE),
    ("This tweet is from a protected account", PRIVATE),
    ("age-restricted content", PRIVATE),
    ("login required to view", PRIVATE),
    ("HTTP Error 429: rate-limit exceeded", RATE_LIMITED),
    ("something totally unexpected", UPSTREAM),
]


@pytest.mark.parametrize("msg,spec", CASES)
def test_mapping(msg, spec):
    err = map_extractor_error(Exception(msg))
    assert err.code == spec[0]
    assert err.status == spec[2]


def test_app_error_builder():
    err = app_error(NO_VIDEO)
    assert err.code == "no_video"
    assert err.status == 422
    assert "quoted post" in err.message
