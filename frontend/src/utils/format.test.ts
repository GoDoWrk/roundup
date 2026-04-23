import { describe, expect, it } from "vitest";
import { formatReadableTimestamp, formatRelativeTime, formatTimestamp } from "./format";

describe("formatReadableTimestamp", () => {
  it("formats valid timestamps for display", () => {
    expect(formatReadableTimestamp("2026-04-23T00:00:00Z")).not.toBeNull();
  });

  it("returns null for invalid timestamps", () => {
    expect(formatReadableTimestamp("not-a-date")).toBeNull();
  });

  it("accepts both unix seconds and unix milliseconds", () => {
    expect(formatTimestamp(1_767_907_200)).toContain("UTC");
    expect(formatReadableTimestamp(1_767_907_200)).not.toBeNull();
    expect(formatRelativeTime(1_767_907_200, 1_767_907_260_000)).toBe("1m ago");
  });
});
