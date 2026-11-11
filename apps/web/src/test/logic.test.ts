import { describe, expect, it } from "vitest";

import { deadlineInfo, formatDateTimeIST, formatINR, fromPaise, toPaise } from "@/lib/format";
import { DEFAULT_FILTERS, parseFilters, serializeFilters, toggleSort, updateFilters } from "@/lib/tender-query";

describe("Indian formatting", () => {
  it("uses crore and lakh", () => {
    expect(formatINR(12_40_00_000_00)).toBe("₹12.40 Cr");
    expect(formatINR(96_00_000_00)).toBe("₹96.00 L");
    expect(formatINR(9_500_00)).toBe("₹9,500");
    expect(formatINR(null)).toBe("Not stated");
  });

  it("converts lakh/crore inputs to paise without floats leaking", () => {
    expect(toPaise(2.45, "crore")).toBe(2_45_00_000_00);
    expect(toPaise(50, "lakh")).toBe(50_00_000_00);
    expect(fromPaise(18_00_00_000_00, "crore")).toBe(18);
  });

  it("renders deadlines in Asia/Kolkata", () => {
    expect(formatDateTimeIST("2026-11-23T12:00:00Z")).toMatch(/23 Nov 2026, 05:30 PM IST/);
  });

  it("classifies deadline urgency", () => {
    const now = new Date("2026-11-11T00:00:00Z");
    expect(deadlineInfo("2026-11-10T00:00:00Z", now).tone).toBe("closed");
    expect(deadlineInfo("2026-11-12T00:00:00Z", now).tone).toBe("urgent");
    expect(deadlineInfo("2026-11-16T00:00:00Z", now)).toEqual({ label: "5 days left", tone: "soon" });
    expect(deadlineInfo("2026-12-11T00:00:00Z", now).tone).toBe("normal");
  });
});

describe("tender explorer URL state", () => {
  it("round-trips multi-select filters through the URL", () => {
    const f = updateFilters(DEFAULT_FILTERS, {
      q: "bridge",
      district: ["Bhopal", "Sehore"],
      eligibility: ["ELIGIBLE"],
      closing_within: 7,
      sort: "deadline",
    });
    const sp = serializeFilters(f);
    expect(sp.toString()).toBe("q=bridge&district=Bhopal&district=Sehore&eligibility=ELIGIBLE&closing_within=7&sort=deadline");
    expect(parseFilters(sp)).toEqual(f);
  });

  it("ignores invalid values and clamps page size", () => {
    const f = parseFilters(new URLSearchParams("sort=hack&page=-3&page_size=9999&order=sideways"));
    expect(f.sort).toBe("relevance");
    expect(f.page).toBe(1);
    expect(f.page_size).toBe(100);
    expect(f.order).toBeNull();
  });

  it("resets to page 1 when filters change", () => {
    const onPage3 = { ...DEFAULT_FILTERS, page: 3 };
    expect(updateFilters(onPage3, { district: ["Rewa"] }).page).toBe(1);
    expect(updateFilters(onPage3, { page: 4 }).page).toBe(4);
  });

  it("toggles sort direction on the same column and resets on a new one", () => {
    const byDeadline = toggleSort(DEFAULT_FILTERS, "deadline");
    expect(byDeadline).toMatchObject({ sort: "deadline", order: null });
    expect(toggleSort(byDeadline, "deadline").order).toBe("desc");
    expect(toggleSort(toggleSort(byDeadline, "deadline"), "deadline").order).toBe("asc");
    expect(toggleSort(DEFAULT_FILTERS, "relevance").order).toBe("asc");
  });
});
