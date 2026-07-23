import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { SiteControls } from "./SiteControls";
import * as api from "./api";

vi.mock("./api", () => ({
  getMaintenance: vi.fn(),
  setMaintenance: vi.fn(),
}));

const getMaintenance = vi.mocked(api.getMaintenance);
const setMaintenance = vi.mocked(api.setMaintenance);

beforeEach(() => {
  getMaintenance.mockReset();
  setMaintenance.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("shows Live when maintenance is off", async () => {
  getMaintenance.mockResolvedValue({ on: false, forced_by_env: false });
  render(<SiteControls />);
  expect(await screen.findByText("Live")).toBeInTheDocument();
});

test("shows In maintenance when the flag is on", async () => {
  getMaintenance.mockResolvedValue({ on: true, forced_by_env: false });
  render(<SiteControls />);
  expect(await screen.findByText("In maintenance")).toBeInTheDocument();
});

test("enabling maintenance confirms, calls setMaintenance(true), then shows In maintenance", async () => {
  getMaintenance.mockResolvedValue({ on: false, forced_by_env: false });
  setMaintenance.mockResolvedValue({ on: true, forced_by_env: false });
  vi.stubGlobal("confirm", vi.fn(() => true));

  render(<SiteControls />);
  await screen.findByText("Live");

  await userEvent.click(screen.getByRole("button", { name: /enable maintenance/i }));

  expect(setMaintenance).toHaveBeenCalledWith(true);
  expect(await screen.findByText("In maintenance")).toBeInTheDocument();
});

test("forced_by_env disables the button and shows the env note", async () => {
  getMaintenance.mockResolvedValue({ on: true, forced_by_env: true });
  render(<SiteControls />);

  expect(await screen.findByText("In maintenance")).toBeInTheDocument();
  expect(screen.getByRole("button")).toBeDisabled();
  expect(screen.getByText(/MAINTENANCE_MODE variable/i)).toBeInTheDocument();
});
