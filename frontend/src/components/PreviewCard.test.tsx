import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import type { ResolveResponse } from "../lib/api";
import { PreviewCard } from "./PreviewCard";

const DATA: ResolveResponse = {
  id: "222",
  author: "Ada Lovelace",
  handle: "ada",
  avatar_url: null,
  text: "two clips",
  items: [
    { index: 1, kind: "video", thumbnail: "https://pbs.twimg.com/t1.jpg", duration_seconds: 5,
      variants: [
        { label: "720p", width: 1280, height: 720, url: "https://video.twimg.com/a.mp4", size_bytes: 2097152 },
        { label: "360p", width: 640, height: 360, url: "https://video.twimg.com/b.mp4", size_bytes: null },
      ] },
    { index: 2, kind: "gif", thumbnail: null, duration_seconds: null,
      variants: [
        { label: "480p", width: 480, height: 480, url: "https://video.twimg.com/tweet_video/c.mp4", size_bytes: 512000 },
      ] },
  ],
};

test("renders author, handle, text, and per-item sections", () => {
  render(<PreviewCard data={DATA} />);
  expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
  expect(screen.getByText("@ada")).toBeInTheDocument();
  expect(screen.getByText("two clips")).toBeInTheDocument();
  expect(screen.getByText("Video 1")).toBeInTheDocument();
  expect(screen.getByText("Video 2")).toBeInTheDocument();
  expect(screen.getByText("GIF")).toBeInTheDocument();
});

test("renders one button per variant with full dimensions, HD chip, and size", () => {
  render(<PreviewCard data={DATA} />);
  const hd = screen.getByRole("button", { name: /1280×720/ });
  expect(hd).toHaveTextContent("2.0 MB");
  expect(hd).toHaveTextContent("HD"); // height >= 720 gets the HD chip
  expect(screen.getByRole("button", { name: /640×360/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /480×480/ })).toBeInTheDocument();
});
