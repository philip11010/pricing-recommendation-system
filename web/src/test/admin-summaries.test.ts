/**
 * The sentences and the arithmetic behind the administration charts.
 *
 * These are tested apart from the components because of what they are: the
 * sentence above each chart is also the label a screen reader is given in
 * place of the chart, so it is the whole of what some readers get, and a
 * sentence that disagrees with the chart beside it is a lie rather than a
 * wording problem.
 *
 * The date helpers get their own tests for one specific bug they exist to
 * avoid. `new Date("2026-11-16")` is midnight UTC, and formatting that in a
 * browser west of Greenwich prints the fifteenth. The API sends plain dates,
 * so these read the string by position instead.
 */

import { describe, expect, it } from "vitest";

import {
  bucketLabel,
  calls,
  dayLabel,
  dayTick,
  decisionSummary,
  endpointSummary,
  formatMilliseconds,
  hasAny,
  latencySummary,
  shareSegments,
  shareSummary,
  weekLabel,
} from "@/lib/admin";
import type { AdminDecisionCounts } from "@/lib/api-types";

describe("dates", () => {
  it("reads the day off the string, whatever the browser's timezone is", () => {
    expect(dayTick("2026-11-16")).toBe("16 Nov");
    expect(dayLabel("2026-11-16")).toBe("16 November 2026");
    expect(weekLabel("2026-11-16")).toBe("Week of 16 November 2026");
  });

  it("handles the first of a month and the last of a year", () => {
    expect(dayLabel("2026-01-01")).toBe("1 January 2026");
    expect(dayLabel("2026-12-31")).toBe("31 December 2026");
  });

  it("returns nothing readable rather than guessing at a bad value", () => {
    expect(dayTick("")).toBe("");
    expect(dayLabel("not-a-date")).toBe("");
    expect(weekLabel("2026-13-01")).toBe("");
  });
});

describe("counts and durations", () => {
  it("writes one call in the singular", () => {
    expect(calls(1)).toBe("1 call");
    expect(calls(2)).toBe("2 calls");
  });

  it("says a duration was not measured rather than printing a zero", () => {
    expect(formatMilliseconds(null)).toBe("Not measured yet");
    expect(formatMilliseconds(undefined)).toBe("Not measured yet");
    expect(formatMilliseconds(37)).toBe("37 ms");
    // Zero is a measurement and is printed as one.
    expect(formatMilliseconds(0)).toBe("0 ms");
  });

  it("writes a histogram bucket as the half-open interval it is", () => {
    expect(bucketLabel({ low: 200, high: 300, count: 4 }, "AUD")).toBe(
      "$200 to under $300 AUD",
    );
  });

  it("knows whether a series has anything in it", () => {
    expect(hasAny([0, 0, 0])).toBe(false);
    expect(hasAny([0, 1])).toBe(true);
    expect(hasAny([])).toBe(false);
  });
});

describe("shares", () => {
  it("works out each percentage to one place", () => {
    const segments = shareSegments([
      { id: "a", label: "A", count: 29 },
      { id: "b", label: "B", count: 9 },
      { id: "c", label: "C", count: 2 },
    ]);

    expect(segments.map((segment) => segment.percent)).toEqual([72.5, 22.5, 5]);
  });

  it("keeps a category at zero rather than dropping it", () => {
    const segments = shareSegments([
      { id: "a", label: "A", count: 0 },
      { id: "b", label: "B", count: 0 },
    ]);

    // The legend is printed from this list, so a category that vanished at
    // zero would make the legend change shape as data arrived.
    expect(segments).toHaveLength(2);
    expect(segments.every((segment) => segment.percent === 0)).toBe(true);
  });
});

describe("the model share sentence", () => {
  const share = (over: Partial<Record<string, number | null>> = {}) => ({
    core: 29,
    full: 9,
    no_model: 2,
    total: 40,
    core_percent: 72.5,
    full_percent: 22.5,
    ...over,
  });

  it("states both shares", () => {
    expect(shareSummary(share())).toContain(
      "the core model answered 72.5% and the full model 22.5%",
    );
  });

  it("says nothing has been logged rather than reporting zero percent", () => {
    expect(shareSummary(share({ total: 0, core: 0, full: 0, no_model: 0 }))).toContain(
      "neither model has answered one",
    );
  });
});

describe("the response time sentence", () => {
  it("names the day with the slowest tail", () => {
    const sentence = latencySummary([
      { day: "2026-10-29", median_ms: 31, p95_ms: 74, requests: 13 },
      { day: "2026-10-30", median_ms: 34, p95_ms: 96, requests: 27 },
    ]);

    expect(sentence).toContain("95th percentile was 96 ms");
    expect(sentence).toContain("30 October 2026");
  });

  it("says there is no response time rather than reporting zero", () => {
    expect(latencySummary([])).toContain("no response time to report");
  });
});

describe("the paths sentence", () => {
  it("names the busiest path", () => {
    const sentence = endpointSummary([
      { id: "preview", label: "Registration preview", count: 26 },
      { id: "registration", label: "Registration", count: 6 },
    ]);

    expect(sentence).toContain("32 calls across 2 paths");
    expect(sentence).toContain("Registration preview, with 26 calls");
  });

  it("says no path has been used rather than naming one at zero", () => {
    const sentence = endpointSummary([
      { id: "preview", label: "Registration preview", count: 0 },
      { id: "registration", label: "Registration", count: 0 },
    ]);

    expect(sentence).toContain("no path has been used yet");
  });
});

describe("the decisions sentence", () => {
  const counts = (over: Partial<AdminDecisionCounts> = {}): AdminDecisionCounts => ({
    accepted: 12,
    modified: 5,
    rejected: 3,
    total: 20,
    acceptance_rate_percent: 60,
    pending: 11,
    ...over,
  });

  it("reports the three actions and the rate", () => {
    const sentence = decisionSummary(counts());

    expect(sentence).toContain("12 accepted");
    expect(sentence).toContain("5 changed");
    expect(sentence).toContain("3 declined");
    expect(sentence).toContain("60% were taken as advised");
    expect(sentence).toContain("11 more are waiting");
  });

  it("never prints a rate of zero percent for advice nobody has answered", () => {
    const sentence = decisionSummary(
      counts({
        accepted: 0,
        modified: 0,
        rejected: 0,
        total: 0,
        acceptance_rate_percent: null,
        pending: 4,
      }),
    );

    // "0% accepted" would read as advice that everybody rejected, which is a
    // different claim from nobody having answered.
    expect(sentence).not.toContain("0%");
    expect(sentence).toContain("No prices have been answered yet");
    expect(sentence).toContain("4 are waiting on a mentor");
  });

  it("says nothing has been advised when there is nothing at all", () => {
    const sentence = decisionSummary(
      counts({
        accepted: 0,
        modified: 0,
        rejected: 0,
        total: 0,
        acceptance_rate_percent: null,
        pending: 0,
      }),
    );

    expect(sentence).toBe("No prices have been advised, so none has been answered.");
  });
});
