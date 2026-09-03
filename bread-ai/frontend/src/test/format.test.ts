import { describe, expect, it } from "vitest";

import { formatBytes, formatDuration, formatVram, truncate } from "../lib/format";

describe("formatBytes", () => {
  it("scales through the units", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
    expect(formatBytes(3 * 1024 ** 3)).toBe("3.00 GB");
  });
});

describe("formatDuration", () => {
  it("keeps short times in milliseconds and long ones readable", () => {
    expect(formatDuration(420)).toBe("420 ms");
    expect(formatDuration(2500)).toBe("2.5 s");
    expect(formatDuration(125_000)).toBe("2m 5s");
  });

  it("returns an empty string when there is nothing to show", () => {
    expect(formatDuration(null)).toBe("");
  });
});

describe("formatVram", () => {
  it("reports unknown rather than guessing zero", () => {
    expect(formatVram(null)).toBe("unknown");
    expect(formatVram(512)).toBe("512 MB");
    expect(formatVram(32768)).toBe("32.0 GB");
  });
});

describe("truncate", () => {
  it("cuts on a word boundary and marks the cut", () => {
    const result = truncate("the quick brown fox jumps over the lazy dog", 20);
    expect(result.endsWith("…")).toBe(true);
    expect(result.length).toBeLessThanOrEqual(21);
    expect(result).not.toContain("  ");
  });

  it("leaves short text alone", () => {
    expect(truncate("short", 20)).toBe("short");
  });
});
