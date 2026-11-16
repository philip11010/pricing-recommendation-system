/**
 * The window the demand chart draws, and the sentence it is read by.
 *
 * The sentence is the part that matters most. It is what a screen reader is
 * given in place of the chart, so it has to say what the chart says, and it
 * has to say nothing else: no claim that activity is a reason to charge more
 * or less, which is a claim this card is in no position to make.
 */

import { describe, expect, it } from "vitest";

import {
  DEMAND_CHART_MONTHS,
  demandSummary,
  recentMonths,
} from "@/components/demand-chart";

const MONTHS = [
  "2025-01-01",
  "2025-02-01",
  "2025-03-01",
  "2025-04-01",
  "2025-05-01",
  "2025-06-01",
  "2025-07-01",
  "2025-08-01",
];

describe("recentMonths", () => {
  it("takes the most recent months, newest last", () => {
    const points = recentMonths(MONTHS, [1, 2, 3, 4, 5, 6, 7, 8]);

    expect(points).toHaveLength(DEMAND_CHART_MONTHS);
    expect(points[0].iso).toBe("2025-03-01");
    expect(points[points.length - 1].iso).toBe("2025-08-01");
    expect(points.map((point) => point.reviews)).toEqual([3, 4, 5, 6, 7, 8]);
  });

  it("takes everything there is when there are fewer months than that", () => {
    const points = recentMonths(MONTHS.slice(0, 3), [1, 2, 3]);

    expect(points.map((point) => point.iso)).toEqual(MONTHS.slice(0, 3));
  });

  it("reads a missing count as none rather than dropping the month", () => {
    const points = recentMonths(["2025-07-01", "2025-08-01"], [4]);

    expect(points).toHaveLength(2);
    expect(points[1].reviews).toBe(0);
  });

  it("has nothing to draw from an empty series", () => {
    expect(recentMonths([], [])).toEqual([]);
  });
});

describe("demandSummary", () => {
  it("states the total, the span and the busiest month", () => {
    const said = demandSummary(recentMonths(MONTHS, [1, 2, 3, 4, 5, 6, 9, 1]));

    expect(said).toBe(
      "28 reviews from March 2025 to August 2025, with the most in July 2025.",
    );
  });

  it("writes a single review in the singular", () => {
    expect(demandSummary(recentMonths(["2025-08-01"], [1]))).toBe(
      "1 review from August 2025, with the most in August 2025.",
    );
  });

  it("says so plainly when nothing came in", () => {
    expect(demandSummary(recentMonths(["2025-07-01", "2025-08-01"], [0, 0]))).toBe(
      "No reviews were recorded from July 2025 to August 2025.",
    );
    expect(demandSummary([])).toBe("No reviews have been recorded yet.");
  });

  it("never says anything about a price", () => {
    for (const counts of [
      [0, 0, 0, 0, 0, 0],
      [1, 1, 1, 1, 1, 1],
      [9, 8, 7, 6, 5, 4],
      [1, 2, 3, 9, 20, 40],
    ]) {
      const said = demandSummary(recentMonths(MONTHS.slice(0, 6), counts));

      for (const banned of [
        "price",
        "charge",
        "raise",
        "higher",
        "lower",
        "demand",
        "consider",
        "%",
      ]) {
        expect(said.toLowerCase()).not.toContain(banned);
      }
    }
  });
});
