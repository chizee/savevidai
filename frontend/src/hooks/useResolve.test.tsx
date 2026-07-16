import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useResolve } from "./useResolve";

afterEach(() => vi.unstubAllGlobals());

const BODY = { id: "20", author: "Jack", handle: "jack", avatar_url: null, text: "", items: [] };

test("happy path goes idle -> resolving -> ready", async () => {
  let release!: (r: Response) => void;
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((res) => (release = res))));
  const { result } = renderHook(() => useResolve());
  expect(result.current.state.status).toBe("idle");

  act(() => void result.current.resolve("https://x.com/jack/status/20"));
  expect(result.current.state.status).toBe("resolving");

  await act(async () => release(new Response(JSON.stringify(BODY), { status: 200 })));
  expect(result.current.state).toMatchObject({ status: "ready", data: BODY });
});

test("api error carries code and message; reset returns to idle", async () => {
  vi.stubGlobal("fetch", vi.fn(async () =>
    new Response(JSON.stringify({ error: "not_found", message: "gone" }), { status: 404 })));
  const { result } = renderHook(() => useResolve());
  await act(() => result.current.resolve("https://x.com/jack/status/20"));
  expect(result.current.state).toMatchObject({ status: "error", code: "not_found", message: "gone" });
  act(() => result.current.reset());
  expect(result.current.state.status).toBe("idle");
});

test("network failure maps to network error state", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("fetch failed"); }));
  const { result } = renderHook(() => useResolve());
  await act(() => result.current.resolve("https://x.com/jack/status/20"));
  expect(result.current.state).toMatchObject({ status: "error", code: "network" });
});
