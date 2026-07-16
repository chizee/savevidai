import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { PasteInput } from "./PasteInput";

test("submits trimmed url", async () => {
  const onSubmit = vi.fn();
  render(<PasteInput status="idle" errorMessage={null} onSubmit={onSubmit} />);
  await userEvent.type(screen.getByRole("textbox"), "  https://x.com/jack/status/20  ");
  await userEvent.click(screen.getByRole("button", { name: /fetch/i }));
  expect(onSubmit).toHaveBeenCalledWith("https://x.com/jack/status/20");
});

test("disables while resolving", () => {
  render(<PasteInput status="resolving" errorMessage={null} onSubmit={vi.fn()} />);
  expect(screen.getByRole("button")).toBeDisabled();
});

test("shows error message with alert role", () => {
  render(<PasteInput status="error" errorMessage="This post doesn't exist or was deleted." onSubmit={vi.fn()} />);
  expect(screen.getByRole("alert")).toHaveTextContent("doesn't exist");
});
