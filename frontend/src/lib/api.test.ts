import { afterEach, expect, test, vi } from "vitest";
import { ApiError, resolveTweet } from "./api";

afterEach(() => vi.unstubAllGlobals());

test("returns parsed body on 200", async () => {
  const body = { id: "20", author: "Jack", handle: "jack", avatar_url: null, text: "", items: [] };
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
  await expect(resolveTweet("https://x.com/jack/status/20")).resolves.toEqual(body);
});

test("throws ApiError with server code on 4xx", async () => {
  const err = { error: "no_video", message: "This post has no video." };
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(err), { status: 422 })));
  const p = resolveTweet("https://x.com/jack/status/20");
  await expect(p).rejects.toBeInstanceOf(ApiError);
  await expect(p).rejects.toMatchObject({ code: "no_video" });
});

test("throws generic ApiError on non-JSON failure", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>bad gateway</html>", { status: 502 })));
  await expect(resolveTweet("x")).rejects.toMatchObject({ code: "upstream_error" });
});
