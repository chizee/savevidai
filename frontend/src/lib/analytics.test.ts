import { afterEach, expect, test, vi } from "vitest";
import { sendEvent } from "./analytics";

afterEach(() => vi.unstubAllGlobals());

test("posts a visit event via fetch when sendBeacon is absent", async () => {
  const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) =>
    new Response(null, { status: 204 }),
  );
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("navigator", {});
  sendEvent("visit");
  const [url, init] = fetchMock.mock.calls[0];
  expect(url).toBe("/api/event");
  expect(JSON.parse(String(init?.body))).toEqual({ type: "visit" });
});

test("includes quality for downloads and never throws on failure", () => {
  vi.stubGlobal("navigator", {});
  vi.stubGlobal(
    "fetch",
    vi.fn(() => {
      throw new Error("network");
    }),
  );
  expect(() => sendEvent("download", "1080p")).not.toThrow();
});

test("uses sendBeacon with the event payload when available", () => {
  const sendBeacon = vi.fn((_url: string, _data?: BodyInit) => true);
  vi.stubGlobal("navigator", { sendBeacon });
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  sendEvent("download", "720p");
  expect(sendBeacon).toHaveBeenCalledTimes(1);
  expect(fetchMock).not.toHaveBeenCalled();
  const [url, blob] = sendBeacon.mock.calls[0];
  expect(url).toBe("/api/event");
  expect(blob).toBeInstanceOf(Blob);
});

test("swallows a rejected fetch (e.g. 404 when analytics is disabled) without throwing", () => {
  vi.stubGlobal("navigator", {});
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 404 })));
  expect(() => sendEvent("visit")).not.toThrow();
});
