# SaveVid AI - TikTok Video Downloader

Date: 2026-07-20
Status: Approved pending user review

## What

Add TikTok (no-watermark) video download to SaveVid AI as its OWN dedicated page, not mixed into the home page. Each platform gets a separate, keyword-rich page:

- Twitter/X: home (`/`), unchanged.
- TikTok: `/tiktokvideodownloader` (this build).
- Reddit: `/redditvideodownloader` (fast-follow, same pattern, separate spec/build).

Platforms are never mixed in one paste box. Instead, a prominent row of platform links sits under the hero (the empty area above the how-to graphic) plus compact links in the top nav, so visitors can jump straight to the page for their platform. This build ships TikTok; the page pattern and the platform-links component are built to make Reddit and future platforms drop-in. YouTube and a broader everything-downloader remain out of scope (a separate future site).

## Goals

- Paste a TikTok post link, get the no-watermark video in a few seconds, same UX as X.
- Keep the resolve-then-proxy model and near-zero cost (no yt-dlp, no ffmpeg, no residential proxies).
- Protect the home page's existing "Twitter Video Downloader" ranking; `/tiktokvideodownloader` owns the TikTok term.
- Per-platform analytics so the owner can see X vs TikTok usage.
- Do not weaken the proxy's SSRF lock.

## Non-goals (v1)

- TikTok photo/slideshow posts, audio-only/MP3 extraction, live videos.
- YouTube / multi-platform everything-downloader (separate site later).
- Rebranding the home H1 to multi-platform (would dilute the Twitter keyword).

## Architecture: a thin platform layer

Today resolving is Twitter-specific (`extract(tweet_id)` in `extractor.py`). Introduce a small platform router so each platform is one isolated module returning the same `ResolveResponse`.

- `app/platforms.py`: `detect_platform(url) -> "twitter" | "tiktok" | None` by hostname; `resolve(url) -> ResolveResponse` that validates, routes, and caches.
- Twitter path unchanged: parse to tweet ID, fxtwitter/vxtwitter (existing `extractor.py`).
- TikTok path: new `app/tiktok.py`, `extract_tiktok(url) -> ResolveResponse`.
- `/api/resolve` calls `platforms.resolve(url)`; response shape, preview card, download flow, and analytics all stay the same.

### URL detection and validation (SSRF-safe input)

- Twitter hosts: existing set (twitter.com, x.com, mirrors).
- TikTok hosts allowlist (input): `tiktok.com`, `www.tiktok.com`, `m.tiktok.com`, `vm.tiktok.com`, `vt.tiktok.com`. Anything else -> `invalid_url` (422).
- Twitter still extracts a numeric ID. TikTok passes the full, host-validated URL to the resolver (short links `vm./vt.` are handled by the resolver, which follows the redirect). We never send an arbitrary user URL to a third party without host-allowlisting first.

## TikTok resolver

- Primary: a free public resolver (tikwm-style) that takes the TikTok URL and returns the no-watermark mp4 plus author, unique_id (handle), title (text), cover (thumbnail), duration. Called with `httpx`, short timeout, `User-Agent` set. Same dependency posture as fxtwitter (third-party, may break; fix is usually resolver-side).
- Structured as `map_tiktok(url, body) -> ResolveResponse` (pure, unit-tested with fixtures) + a thin network `extract_tiktok` wrapper (same split as the Twitter extractor, so mapping is tested without network).
- Variants: prefer no-watermark HD (`hdplay`, labeled `"hd"`) then no-watermark SD (`play`, labeled `"sd"`); the watermarked URL is ignored. These two exact labels (`hd`, `sd`) are the committed TikTok label set, and the widened event validation below must accept exactly them.
- Fallback slot: structure `extract_tiktok` so a second free resolver can be added later as a fallback (mirrors fxtwitter -> vxtwitter), without a rewrite. v1 ships primary only.
- Errors map to the existing catalog: not found / private / no_video / upstream_error, plus clean handling when the resolver is unreachable (fire the same `upstream_error`, logged).

### Download bytes may run through the resolver

Unlike fxtwitter (bytes come from Twitter's own CDN), the tikwm-style no-watermark file often comes from the resolver's own cache host. So a resolver outage can break the actual download, not just resolving. Accepted for v1; the fallback-resolver slot mitigates it later. The spec names this so it is a known, not a surprise.

## Download proxy (the one security-sensitive change)

Downloads stream through the existing `/api/proxy`, which is hard-locked to `https://video.twimg.com/` today. Extend the lock to a **per-platform host allowlist**, keeping it tight:

- Allowlist is an explicit set of rules. Twitter: `video.twimg.com` (unchanged). TikTok: the exact byte host(s) the resolver actually returns (to be pinned in the plan after observing a real response; expected `tikwm.com` and/or the TikTok media CDN).
- Host matching is exact-host or safe registrable-suffix (`host == "tiktokcdn.com" or host.endswith(".tiktokcdn.com")`). Never substring match (the `video.twimg.com.evil.com` trap). The trailing-boundary check that protects the current lock is preserved.
- The proxy still does **not** follow redirects (a 3xx from an allowed host cannot bounce to a disallowed one). The plan must verify the TikTok download URL is terminal; if it 3xx-redirects, resolve the final host at resolve time and allowlist that, rather than enabling redirect-follow.
- Concurrency cap, rate limit, filename sanitization, and the semaphore-no-leak fix all stay as-is.

## Caching

The resolve cache key must be namespaced by platform (`f"{platform}:{id_or_urlkey}"`) so a TikTok ID can never collide with a tweet ID. TTL/behavior unchanged.

## Analytics (per-platform)

- Add a nullable `platform` column to the `events` table (`twitter` | `tiktok` | null for legacy rows). `CREATE TABLE IF NOT EXISTS` stays; add a lightweight migration that `ALTER TABLE ADD COLUMN platform` if missing (both SqliteStore and TursoStore), guarded so it is idempotent and never crashes boot (the non-fatal enablement wrapper already protects startup).
- `fetch` and `download` events record their resolved platform (`twitter` | `tiktok`). `visit` events record the page's platform (`twitter` for `/`, `tiktok` for `/tiktokvideodownloader`).
- Stats API gains a `platforms` breakdown (fetches/downloads by platform, window-scoped). Dashboard adds one small bar/row showing X vs TikTok.
- **Download-event validation fix:** the `/api/event` quality pattern is currently `^\d{2,4}p$|^video$` and would 422 the TikTok labels. Widen it to exactly `^(\d{2,4}p|video|hd|sd)$`. This is required or TikTok download beacons are silently dropped.

## Frontend

Dedicated page per platform, no mixed input. Each page is a Vite entry (same multi-page pattern as `/admin`), served by FastAPI, reusing the same tool and design system, scoped to one platform (placeholder, examples, SEO, brand copy).

- **Home (`/`)**: unchanged, Twitter/X only. H1 stays "Twitter/X Video Downloader" (protects the ranking). Its paste box stays Twitter-only in presentation.
- **TikTok page (`/tiktokvideodownloader`)**: served at `GET /tiktokvideodownloader`. Own SEO head: title "TikTok Video Downloader - No Watermark, Free | SaveVid AI", TikTok-specific meta, and genuinely distinct crawlable static content (TikTok how-to, TikTok FAQ, no-watermark explainer) so it is not thin/duplicate. Paste box placeholder + example are TikTok.
- **Platform-links component (discoverability, the key UX ask)**: a row of cards/pills, one per platform (Twitter/X, TikTok, and Reddit once it ships), rendered on every platform page in the space directly under the hero caption and above the how-to graphic (the area the owner marked). The card for the current page is shown as active; the others link to their pages. This is how visitors find the right downloader. Adding a platform later = one entry in this component, no redesign.
- **Top nav**: add compact links to the platform pages (Twitter / TikTok / Reddit) alongside the existing nav, so the pages are reachable from the header too.
- Backend stays forgiving: `/api/resolve` still auto-detects platform from the pasted URL, so a mis-pasted link (e.g. a TikTok URL on the home page) still resolves rather than hard-failing. The separation is a presentation/SEO choice, not a backend restriction. Each page may show a gentle hint if the pasted link is for a different platform ("that's a TikTok link, here's the TikTok page").
- URL slugs are the exact keyword phrases (`tiktokvideodownloader`, later `redditvideodownloader`). Hyphenated variants (`tiktok-video-downloader`) read marginally better for SEO; going with the owner's no-hyphen preference unless changed.
- `sitemap.xml` gains `/tiktokvideodownloader` (and `/redditvideodownloader` when built). `robots.txt` unchanged. Public bundle for `/` must stay unaffected (separate entry chunks, as verified for `/admin`).

## Error handling

- Not a TikTok/X link -> `invalid_url`.
- TikTok post with no video (photo/slideshow) -> `no_video` with a message pointing out slideshows are not supported yet.
- Private/removed -> `not_found` / `private_or_restricted`.
- Resolver down / non-JSON / malformed -> `upstream_error`, logged (reuse the guarded-mapper pattern from the extractor).

## Testing

- `detect_platform` for twitter/tiktok/unknown hosts.
- TikTok URL host-allowlist: accepts tiktok.com/@u/video/id, `vm.`/`vt.`/`m.` variants, tracking params; rejects other hosts and lookalikes (`tiktok.com.evil.com`).
- `map_tiktok` fixture mapping: no-watermark variant selection, handle/text/thumbnail/duration, no_video on empty, error-code mapping. No network in tests.
- Proxy allowlist: accepts the TikTok byte host(s), still rejects `video.twimg.com.evil.com`, non-allowed hosts, and control-char URLs (existing regression holds).
- Cache namespacing: a tiktok id and a twitter id with the same digits do not collide.
- Analytics: `platform` recorded on fetch/download; migration idempotent; widened quality validation accepts TikTok labels and still rejects junk; stats `platforms` breakdown correct on a seeded fixture.
- Frontend: `/tiktokvideodownloader` entry builds and the home (`/`) bundle is unaffected; the TikTok page resolves a TikTok URL (mocked); the platform-links component renders on each page with the current platform active and the others linking out; backend `/api/resolve` still auto-detects a TikTok URL regardless of page (forgiving).

## Risks

- Free TikTok resolver is a third-party single point of failure, and (unlike Twitter) the download bytes may depend on it too. Mitigation: fallback-resolver slot, in-memory cache, honest error messages.
- Resolver rate limits (tikwm-style services are stricter than fxtwitter). Cache absorbs popular items; note as a scaling watch-item.
- Proxy allowlist is the SSRF-critical surface; the plan pins exact hosts and uses suffix-safe matching, no substring, no redirect-follow.
- `/tiktokvideodownloader` thin-content SEO risk: mitigated by genuinely distinct TikTok copy.
