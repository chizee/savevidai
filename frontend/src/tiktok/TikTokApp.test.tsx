import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import TikTokApp from "./TikTokApp";

afterEach(() => vi.unstubAllGlobals());

test("renders the TikTok downloader page", () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 204 })));
  render(<TikTokApp />);
  expect(screen.getByRole("heading", { name: /tiktok video downloader/i })).toBeInTheDocument();
  expect(screen.getByRole("textbox")).toHaveAttribute("placeholder", expect.stringMatching(/tiktok/i));
});
