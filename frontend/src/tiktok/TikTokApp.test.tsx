import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import TikTokApp from "./TikTokApp";

afterEach(() => vi.unstubAllGlobals());

// Runs first on purpose: TikTokApp guards the visit beacon with a module-level
// flag, so it only fires on the first render of this module. Ordering this test
// ahead of any other render keeps it deterministic (mirrors App.test.tsx).
test("fires exactly one visit beacon per page load, even with StrictMode's double-invoke", async () => {
  const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) =>
    new Response(null, { status: 204 }),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(
    <StrictMode>
      <TikTokApp />
    </StrictMode>,
  );
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  const visitCalls = fetchMock.mock.calls.filter(([url, init]) => {
    if (String(url) !== "/api/event") return false;
    const body = JSON.parse(String((init as RequestInit).body));
    return body.type === "visit";
  });
  expect(visitCalls).toHaveLength(1);
  const visitBody = JSON.parse(String((visitCalls[0][1] as RequestInit).body));
  expect(visitBody).toEqual({ type: "visit", platform: "tiktok" });
});

test("renders the TikTok downloader page", () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 204 })));
  render(<TikTokApp />);
  expect(screen.getByRole("heading", { name: /tiktok video downloader/i })).toBeInTheDocument();
  expect(screen.getByRole("textbox")).toHaveAttribute("placeholder", expect.stringMatching(/tiktok/i));
});

const RESOLVE_BODY = {
  id: "6718335390845095173", author: "scout2015", handle: "scout2015", avatar_url: null, text: "hi",
  items: [{ index: 1, kind: "video", thumbnail: null, duration_seconds: 3,
    variants: [{ label: "HD", width: 1280, height: 720, url: "https://v.tiktokcdn.com/v.mp4", size_bytes: 100 }] }],
};

test("example chip resolves the showcase post and fills the input", async () => {
  const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) =>
    new Response(JSON.stringify(RESOLVE_BODY), { status: 200 }),
  );
  vi.stubGlobal("fetch", fetchMock);
  render(<TikTokApp />);
  await userEvent.click(screen.getByRole("button", { name: /try an example/i }));
  expect(await screen.findByTestId("preview-card")).toBeInTheDocument();
  // Filter to the resolve call specifically: a visit beacon may also hit fetch
  // on mount, so the resolve request isn't guaranteed to be the first call.
  const call = fetchMock.mock.calls.find(([url]) => String(url) === "/api/resolve");
  expect(String(call?.[1]?.body)).toContain("@scout2015/video/6718335390845095173");
  expect(screen.getByRole("textbox")).toHaveValue(
    "https://www.tiktok.com/@scout2015/video/6718335390845095173",
  );
});
