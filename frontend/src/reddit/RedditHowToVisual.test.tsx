import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { RedditHowToVisual } from "./RedditHowToVisual";

test("renders the reddit how-to art", () => {
  render(<RedditHowToVisual />);
  expect(screen.getAllByText(/reddit\.com\/r\//i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/with audio/i).length).toBeGreaterThan(0);
});
