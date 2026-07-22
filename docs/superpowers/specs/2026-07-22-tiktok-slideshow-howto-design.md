# TikTok Slideshow Downloader + How-To Visual - Design

Pre-merge additions to the `feature/tiktok` branch. Two features plus four small improvements, all scoped to ship before the branch merges.

## Goals

1. Download TikTok photo slideshows (photos + soundtrack), not just videos.
2. Give the TikTok page the same annotated how-to graphic the home page has, with TikTok-specific art.
3. Fold in four small improvements: HD chip on the `hd` pill, example chip on the TikTok page, shorter TikTok cache TTL, TikTok-specific OG image.

## Non-goals

- No server-side media processing (no ffmpeg, no zip assembly). Zero-cost model holds.
- No changes to the Twitter flow. The home page changes only if the HD chip rule touches shared code, and then only additively.
- No new third-party dependencies on the backend.

## 1. Slideshow backend

**Where:** `backend/app/tiktok.py` (`map_tiktok`), inside the existing `_map_guarded` protection.

**Detection:** tikwm returns `data.images: [str, ...]` for photo posts. When a non-empty `images` list is present, map the post as a slideshow instead of requiring `play`/`hdplay` video variants.

**Mapping:**
- One `MediaItem(kind="image")` per photo: `index` = 1-based position, `thumbnail` = the image URL itself, `duration_seconds` = None, one `Variant(label="photo", url=<image url>)`.
- One `MediaItem(kind="audio")` when tikwm's music mp3 URL is present: single `Variant(label="sound", url=<mp3 url>)`. No conversion - tikwm serves a ready mp3.
- If the real response also carries `play`/`hdplay` on photo posts (tikwm server-renders slideshows into a video with the sound baked in), include the video item(s) exactly as the video path does today. Verify against reality before finalizing; do not assume.
- A photo post with an empty/malformed `images` list and no video URLs raises `no_video`, same as today.

**Schema:** no changes. `MediaItem.kind` comment widens to `"video" | "gif" | "image" | "audio"`.

**Verification contract (same discipline as the video resolver):** before finalizing, hit the real tikwm endpoint once with a public slideshow URL. Confirm: the `images` key name and shape, the music URL key and its host, the image byte hosts, and whether `play`/`hdplay` exist on photo posts. Check every observed host against the proxy allowlist (`tikwm.com`, `tiktokcdn.com`, `tiktokcdn-us.com`, `tiktokcdn-eu.com`, suffix-matched); widen `TIKTOK_MEDIA_HOSTS` only if an observed host falls outside it, and remember the tuple feeds the SSRF allowlist - changes there are security-reviewed.

**Analytics:** the `/api/event` quality regex widens to exactly `^(\d{2,4}p|video|hd|sd|photo|album|sound)$`.

## 2. Slideshow frontend

**Where:** `frontend/src/components/PreviewCard.tsx` (and a small new grid subcomponent if cleaner), `frontend/src/components/QualityButton.tsx` untouched for videos.

**Rendering:** `kind="image"` items render as a thumbnail grid (the photos themselves), consistent with the existing card/panel tokens. `kind="audio"` renders as a small secondary "Sound" pill under the grid.

**Downloads:** all through the existing proxy blob flow.
- Tap a photo: saves that photo, filename `{handle}_{id}_photo_{n}.jpg`.
- `Save all` button: downloads every photo sequentially with a short stagger between saves. No zip.
- `Sound` button: saves `{handle}_{id}_sound.mp3`.

**Beacons:** one per user action, not per file. Single photo -> `quality: "photo"`; Save all -> one event `quality: "album"`; sound -> `quality: "sound"`. All carry `platform: "tiktok"`.

**Copy updates:** TikTok page FAQ answer for slideshows flips from "Not yet" to yes (visible `<details>` and JSON-LD both), phrased plainly. No em dashes, no emoji.

**Tests:** real-DOM tests for the grid render, per-photo filename, single-beacon-per-action semantics, and the sound button. Backend fixture tests for the slideshow mapping, empty-images edge, and sound-absent edge.

## 3. TikTok how-to visual

**Where:** new `frontend/src/tiktok/TikTokHowToVisual.tsx` (fork of `HowToVisual.tsx`, ~300 lines of inline SVG; forking over parameterizing because the panel art is platform-specific and the SVG is the component).

**Art, mirroring the home reference style (red marker annotations, theme-aware tokens):**
- Panel 1: TikTok post mock with Share > Copy link circled.
- Panel 2: input showing `tiktok.com/@user/vid…` + Fetch button, circled.
- Panel 3: quality pills - `hd` with HD chip (circled), `sd` - saved-file line (`user_123_hd.mp4`, check icon) and the note "No watermark. Straight from the source."
- Landscape flow on sm+ screens, stacked phone-only variant, same as home.

**Placement:** above the step cards on the TikTok page, same slot as home.

## 4. Extras

- **HD chip:** `QualityButton` shows the HD chip when `variant.label === "hd"` in addition to the existing height >= 720 rule. TikTok variants carry no dimensions, so this is the only signal.
- **Example chip:** the TikTok page gets the home-style "try an example" chip wired to a stable public TikTok video URL (verified resolving at build time); input mirrors the URL, then resolves.
- **TikTok cache TTL:** TikTok resolve cache entries live ~15 minutes (twitter stays 1 hour). tikwm play URLs are time-signed; an hour-old cache hit can hand out a URL that 403s at download. Implementation detail (per-entry TTL or a second TTLCache instance) is the implementer's choice; behavior contract: a TikTok resolve older than 15 minutes re-resolves.
- **OG image:** TikTok-specific `og-tiktok.png` rendered with the existing `make_og.py` dev-script pattern; `tiktokvideodownloader.html` OG/Twitter meta points at it.

## Constraints carried forward

- Response shape unchanged; labels for video stay exactly `hd`/`sd`; watermarked URL never offered.
- Proxy matching stays exact-host or dot-suffix, never substring; no redirect-follow.
- Analytics off unless configured; no em dashes or emoji anywhere, including page copy.
- Backend from `backend/` with venv active; frontend from `frontend/`. Warning baseline is 5.

## Testing/verification gate

Full suites green, build emits all entries, and a live browser end-to-end on a real slideshow post: resolve, grid renders, single photo saves, Save all saves every photo, sound saves, beacons fire once per action. Video flow re-verified unchanged.
