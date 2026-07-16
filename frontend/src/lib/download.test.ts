import { afterEach, expect, test, vi } from "vitest";
import { buildFilename, downloadVariant, proxyUrl } from "./download";

afterEach(() => vi.unstubAllGlobals());

test("buildFilename single and multi", () => {
  expect(buildFilename("ada", "111", "1080p", 1, 1)).toBe("ada_111_1080p.mp4");
  expect(buildFilename("ada", "222", "720p", 2, 3)).toBe("ada_222_2_720p.mp4");
});

test("proxyUrl encodes url and filename", () => {
  const u = proxyUrl("https://video.twimg.com/v.mp4?tag=1", "a b.mp4");
  expect(u).toBe("/api/proxy?url=https%3A%2F%2Fvideo.twimg.com%2Fv.mp4%3Ftag%3D1&filename=a%20b.mp4");
});

test("falls back to proxy when direct fetch fails", async () => {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      if (url.startsWith("https://video.twimg.com/")) throw new TypeError("cors");
      // Use ReadableStream for consistent behavior in jsdom
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(new Uint8Array([1, 2, 3]));
          controller.close();
        },
      });
      return new Response(stream, {
        status: 200,
        headers: { "content-length": "3" },
      });
    }),
  );
  const progress: number[] = [];
  await downloadVariant("https://video.twimg.com/v.mp4", "f.mp4", (p) => progress.push(p.received));
  expect(calls[0]).toBe("https://video.twimg.com/v.mp4");
  expect(calls[1]).toContain("/api/proxy?");
  expect(progress.at(-1)).toBe(3);
});
