import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import type { MediaItem } from "../lib/api";
import { PhotoGrid } from "./PhotoGrid";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function photo(n: number): MediaItem {
  return {
    index: n,
    kind: "image",
    thumbnail: `https://pbs.twimg.com/p${n}.jpg`,
    duration_seconds: null,
    variants: [
      { label: "orig", width: 1080, height: 1920, url: `https://pbs.twimg.com/photo${n}.jpg`, size_bytes: 3 },
    ],
  };
}

const AUDIO: MediaItem = {
  index: 99,
  kind: "audio",
  thumbnail: null,
  duration_seconds: 30,
  variants: [
    { label: "sound", width: null, height: null, url: "https://sf16.tiktok.com/track.mp3", size_bytes: 3 },
  ],
};

// Mirror QualityButton.test.tsx: /api/proxy streams 3 bytes, everything else 204.
function stubProxyAndBeacon() {
  return vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    if (String(input).startsWith("/api/proxy")) {
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(new Uint8Array([1, 2, 3]));
          controller.close();
        },
      });
      return new Response(stream, { status: 200, headers: { "content-length": "3" } });
    }
    return new Response(null, { status: 204 });
  });
}

const PHOTOS = [photo(1), photo(2), photo(3)];

test("renders one img per photo and a Save all button; Sound only with audio", () => {
  const { container, rerender } = render(
    <PhotoGrid photos={PHOTOS} audio={null} handle="ada" id="222" platform="tiktok" />,
  );
  // Photos are decorative (alt=""), so query the DOM directly rather than by role.
  expect(container.querySelectorAll("img")).toHaveLength(3);
  expect(screen.getByRole("button", { name: /save all/i })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^sound$/i })).toBeNull();

  rerender(<PhotoGrid photos={PHOTOS} audio={AUDIO} handle="ada" id="222" platform="tiktok" />);
  expect(screen.getByRole("button", { name: /^sound$/i })).toBeInTheDocument();
});

test("tapping one photo fires exactly one photo beacon and one proxy fetch (photo_2.jpg)", async () => {
  const fetchMock = stubProxyAndBeacon();
  vi.stubGlobal("fetch", fetchMock);
  render(<PhotoGrid photos={PHOTOS} audio={null} handle="ada" id="222" platform="tiktok" />);

  await userEvent.click(screen.getByRole("button", { name: /save photo 2/i }));

  const beacons = fetchMock.mock.calls.filter(([u]) => String(u) === "/api/event");
  expect(beacons).toHaveLength(1);
  expect(JSON.parse(String(beacons[0]?.[1]?.body))).toEqual({
    type: "download",
    quality: "photo",
    platform: "tiktok",
  });

  const proxy = fetchMock.mock.calls.filter(([u]) => String(u).startsWith("/api/proxy"));
  expect(proxy).toHaveLength(1);
  expect(String(proxy[0]?.[0])).toContain("photo_2.jpg");
});

test("Save all fires exactly one album beacon and one proxy fetch per photo", async () => {
  vi.useFakeTimers();
  const fetchMock = stubProxyAndBeacon();
  vi.stubGlobal("fetch", fetchMock);
  render(<PhotoGrid photos={PHOTOS} audio={null} handle="ada" id="222" platform="tiktok" />);

  // fireEvent (not userEvent) so it doesn't fight the fake clock; runAllTimersAsync
  // flushes the sequential downloads and the 600ms staggers between them.
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /save all/i }));
    await vi.runAllTimersAsync();
  });

  const beacons = fetchMock.mock.calls.filter(([u]) => String(u) === "/api/event");
  expect(beacons).toHaveLength(1);
  expect(JSON.parse(String(beacons[0]?.[1]?.body))).toEqual({
    type: "download",
    quality: "album",
    platform: "tiktok",
  });

  const proxy = fetchMock.mock.calls.filter(([u]) => String(u).startsWith("/api/proxy"));
  expect(proxy).toHaveLength(3);
});

test("Sound fires one sound beacon and fetches sound.m4a", async () => {
  const fetchMock = stubProxyAndBeacon();
  vi.stubGlobal("fetch", fetchMock);
  render(<PhotoGrid photos={PHOTOS} audio={AUDIO} handle="ada" id="222" platform="tiktok" />);

  await userEvent.click(screen.getByRole("button", { name: /^sound$/i }));

  const beacons = fetchMock.mock.calls.filter(([u]) => String(u) === "/api/event");
  expect(beacons).toHaveLength(1);
  expect(JSON.parse(String(beacons[0]?.[1]?.body))).toEqual({
    type: "download",
    quality: "sound",
    platform: "tiktok",
  });

  const proxy = fetchMock.mock.calls.filter(([u]) => String(u).startsWith("/api/proxy"));
  expect(proxy).toHaveLength(1);
  expect(String(proxy[0]?.[0])).toContain("sound.m4a");
});
