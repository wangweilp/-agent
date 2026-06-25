import { describe, it, expect } from "vitest";
import {
  formatCents,
  formatPercent,
  formatLatency,
  formatDelta,
  formatCompact,
  estimateMonthlyCostCents,
} from "@/components/dashboard-v2/format";

describe("formatCents", () => {
  it("converts cents to yuan with 2 decimals", () => {
    expect(formatCents(12345)).toBe("¥123.45");
  });

  it("formats zero", () => {
    expect(formatCents(0)).toBe("¥0.00");
  });

  it("handles large values with thousands separator", () => {
    expect(formatCents(100000)).toBe("¥1,000.00");
  });

  it("returns ¥0.00 for non-finite input", () => {
    expect(formatCents(NaN)).toBe("¥0.00");
    expect(formatCents(Infinity)).toBe("¥0.00");
  });
});

describe("formatPercent", () => {
  it("formats a percentage value", () => {
    expect(formatPercent(87.5)).toBe("87.5%");
  });

  it("formats whole numbers with .0", () => {
    expect(formatPercent(100)).toBe("100.0%");
  });

  it("returns — for null/undefined/non-finite", () => {
    expect(formatPercent(null)).toBe("—");
    expect(formatPercent(undefined)).toBe("—");
    expect(formatPercent(NaN)).toBe("—");
  });
});

describe("formatLatency", () => {
  it("formats milliseconds under 1000 with ms suffix", () => {
    expect(formatLatency(320)).toBe("320ms");
  });

  it("converts to seconds at or above 1000", () => {
    expect(formatLatency(1500)).toBe("1.5s");
  });

  it("returns — for non-finite", () => {
    expect(formatLatency(NaN)).toBe("—");
  });
});

describe("formatDelta", () => {
  it("prefixes positive with +", () => {
    expect(formatDelta(12)).toBe("+12");
  });

  it("keeps negative sign", () => {
    expect(formatDelta(-5)).toBe("-5");
  });

  it("returns 0 for zero", () => {
    expect(formatDelta(0)).toBe("0");
  });

  it("returns 0 for non-finite", () => {
    expect(formatDelta(NaN)).toBe("0");
  });
});

describe("formatCompact", () => {
  it("formats thousands with K", () => {
    expect(formatCompact(1500)).toBe("1.5K");
  });

  it("formats millions with M", () => {
    expect(formatCompact(1200000)).toBe("1.2M");
  });

  it("returns plain number below 1000", () => {
    expect(formatCompact(42)).toBe("42");
  });

  it("handles negative compact values", () => {
    expect(formatCompact(-2500)).toBe("-2.5K");
  });
});

describe("estimateMonthlyCostCents", () => {
  it("multiplies daily cost by 30", () => {
    expect(estimateMonthlyCostCents(100)).toBe(3000);
  });

  it("returns 0 for zero daily cost", () => {
    expect(estimateMonthlyCostCents(0)).toBe(0);
  });

  it("returns 0 for negative or non-finite input", () => {
    expect(estimateMonthlyCostCents(-50)).toBe(0);
    expect(estimateMonthlyCostCents(NaN)).toBe(0);
  });
});
