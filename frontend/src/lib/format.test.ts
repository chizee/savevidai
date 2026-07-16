import { expect, test } from "vitest";
import { formatBytes, formatDuration } from "./format";

test("formatBytes", () => {
  expect(formatBytes(null)).toBeNull();
  expect(formatBytes(0)).toBeNull();
  expect(formatBytes(512)).toBe("512 B");
  expect(formatBytes(1536)).toBe("1.5 KB");
  expect(formatBytes(35651584)).toBe("34 MB");
});

test("formatDuration", () => {
  expect(formatDuration(5)).toBe("0:05");
  expect(formatDuration(75)).toBe("1:15");
  expect(formatDuration(12.5)).toBe("0:13");
});
