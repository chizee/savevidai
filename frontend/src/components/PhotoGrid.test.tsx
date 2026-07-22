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
const STAGGER_MS = 600; // must match PhotoGrid's stagger between sequential saves

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

// A proxy mock that streams 3 bytes normally but fails (500, empty body) for the
// nth photo's filename; every non-proxy request 204s. Records proxy call order.
function stubFailingProxy(failFilename: string, order: string[]) {
  return vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    if (url.startsWith("/api/proxy")) {
      order.push(url);
      if (url.includes(failFilename)) {
        return new Response(null, { status: 500 });
      }
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

test("Save all: a failed photo is marked and the sweep continues sequentially, one album beacon", async () => {
  vi.useFakeTimers();
  const order: string[] = [];
  const fetchMock = stubFailingProxy("photo_2.jpg", order);
  vi.stubGlobal("fetch", fetchMock);
  const { container } = render(
    <PhotoGrid photos={PHOTOS} audio={null} handle="ada" id="222" platform="tiktok" />,
  );

  // Kick off the sweep and let only photo 1's download resolve (advance 0ms so the
  // 600ms stagger has NOT fired yet). Sequential means photo 2 must not have started.
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /save all/i }));
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(order).toHaveLength(1);
  expect(order[0]).toContain("photo_1.jpg");

  // Advance past the first stagger: photo 2 starts (and fails), still nothing after it.
  await act(async () => {
    await vi.advanceTimersByTimeAsync(STAGGER_MS);
  });
  expect(order).toHaveLength(2);
  expect(order[1]).toContain("photo_2.jpg");

  // Advance past the second stagger: photo 3 completes the sweep.
  await act(async () => {
    await vi.runAllTimersAsync();
  });
  expect(order).toHaveLength(3);
  expect(order[2]).toContain("photo_3.jpg");

  // Photo 2's tile is marked failed; photos 1 and 3 saved.
  const tiles = container.querySelectorAll(".photo-tile");
  expect(tiles[0]?.getAttribute("data-state")).toBe("saved");
  expect(tiles[1]?.getAttribute("data-state")).toBe("failed");
  expect(tiles[2]?.getAttribute("data-state")).toBe("saved");

  // Exactly one album beacon for the whole batch.
  const beacons = fetchMock.mock.calls.filter(([u]) => String(u) === "/api/event");
  expect(beacons).toHaveLength(1);
  expect(JSON.parse(String(beacons[0]?.[1]?.body))).toEqual({
    type: "download",
    quality: "album",
    platform: "tiktok",
  });

  // One proxy fetch per photo: the failure didn't retry or skip.
  const proxy = fetchMock.mock.calls.filter(([u]) => String(u).startsWith("/api/proxy"));
  expect(proxy).toHaveLength(3);
});

test("a tile tap during Save all is ignored (no extra beacon or proxy fetch)", async () => {
  vi.useFakeTimers();
  const fetchMock = stubProxyAndBeacon();
  vi.stubGlobal("fetch", fetchMock);
  render(<PhotoGrid photos={PHOTOS} audio={null} handle="ada" id="222" platform="tiktok" />);

  // Start the sweep and pause it mid-flight (after photo 1, savingAll still true).
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /save all/i }));
    await vi.advanceTimersByTimeAsync(0);
  });

  // Tap photo 3's tile while the sweep is in progress; the guard should drop it.
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /save photo 3/i }));
    await vi.advanceTimersByTimeAsync(0);
  });

  // Let the sweep finish. Bounded advance (not runAllTimersAsync) so motion's
  // requestAnimationFrame loop can't spin the fake clock forever.
  await act(async () => {
    await vi.advanceTimersByTimeAsync(STAGGER_MS * 4);
  });

  // Still just the one album beacon (no stray photo beacon from the tap).
  const beacons = fetchMock.mock.calls.filter(([u]) => String(u) === "/api/event");
  expect(beacons).toHaveLength(1);
  expect(JSON.parse(String(beacons[0]?.[1]?.body))).toMatchObject({ quality: "album" });

  // Exactly three proxy fetches (one per photo); photo 3 was not double-downloaded.
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
