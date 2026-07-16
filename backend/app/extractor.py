import yt_dlp

from .errors import NO_VIDEO, app_error, map_extractor_error
from .schemas import MediaItem, ResolveResponse, Variant
from .urls import canonical_url

_YDL_OPTS = {"quiet": True, "no_warnings": True, "skip_download": True}


def extract(tweet_id: str) -> ResolveResponse:
    """Resolve a tweet ID to its video variants via yt-dlp (metadata only, no download)."""
    try:
        with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
            info = ydl.extract_info(canonical_url(tweet_id), download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise map_extractor_error(exc) from exc
    return map_info(tweet_id, info)


def map_info(tweet_id: str, info: dict) -> ResolveResponse:
    entries = info.get("entries") if info.get("_type") == "playlist" else [info]
    items: list[MediaItem] = []
    for i, entry in enumerate([e for e in (entries or []) if e], start=1):
        item = _map_entry(entry, i)
        if item is not None:
            items.append(item)
    if not items:
        raise app_error(NO_VIDEO)
    handle = info.get("uploader_id") or "unknown"
    return ResolveResponse(
        id=tweet_id,
        author=info.get("uploader") or handle,
        handle=handle,
        text=(info.get("description") or "").strip(),
        items=items,
    )


def _map_entry(entry: dict, index: int) -> MediaItem | None:
    variants: list[Variant] = []
    for f in entry.get("formats") or []:
        url = f.get("url") or ""
        if f.get("vcodec") in (None, "none"):
            continue  # audio-only
        if not url.startswith("https://video.twimg.com/"):
            continue
        if f.get("protocol") not in (None, "https", "http"):
            continue  # skip HLS playlists; browsers download plain mp4s
        height = f.get("height")
        variants.append(
            Variant(
                label=f"{height}p" if height else "video",
                width=f.get("width"),
                height=height,
                url=url,
            )
        )
    if not variants:
        return None
    variants.sort(key=lambda v: (v.height or 0, v.width or 0), reverse=True)
    kind = "gif" if "/tweet_video/" in variants[0].url else "video"
    return MediaItem(
        index=index,
        kind=kind,
        thumbnail=entry.get("thumbnail"),
        duration_seconds=entry.get("duration"),
        variants=variants,
    )
