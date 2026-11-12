/**
 * The arithmetic behind the three charts.
 *
 * A marker in the wrong place on a price ladder is a lie about where a mentor
 * sits, and nobody reading the page can tell. These are the sums that decide
 * it, tested away from any rendering, because what is being checked is the
 * number rather than the pixel.
 */

import { describe, expect, it } from "vitest";

import {
  MINIMUM_CHART_POINTS,
  bandGeometry,
  dotStripLayout,
  monthLabel,
  monthShort,
  positionPercent,
  priceScale,
  reviewStats,
} from "@/lib/charts";

describe("the price axis", () => {
  it("leaves room either side, so a marker never sits on the end", () => {
    const scale = priceScale([120, 300]);

    expect(scale.min).toBeLessThan(120);
    expect(scale.max).toBeGreaterThan(300);
  });

  it("never goes below zero, because no price does", () => {
    expect(priceScale([5, 8]).min).toBe(0);
    expect(priceScale([10, 20]).min).toBeGreaterThanOrEqual(0);
  });

  it("still has two ends when every value is the same", () => {
    const scale = priceScale([200, 200, 200]);

    expect(scale.max).toBeGreaterThan(scale.min);
  });

  it("ignores the values it cannot use", () => {
    const scale = priceScale([null, undefined, 150, Number.NaN, 250]);

    expect(scale.min).toBeLessThanOrEqual(150);
    expect(scale.max).toBeGreaterThanOrEqual(250);
  });

  it("has an answer when there is nothing to scale at all", () => {
    expect(priceScale([])).toEqual({ min: 0, max: 100 });
  });
});

describe("where a marker sits", () => {
  const scale = { min: 100, max: 300 };

  it("puts the middle of the range in the middle of the track", () => {
    expect(positionPercent(200, scale)).toBe(50);
  });

  it("puts the two ends at the two ends", () => {
    expect(positionPercent(100, scale)).toBe(0);
    expect(positionPercent(300, scale)).toBe(100);
  });

  it("holds a value outside the range on the track rather than off it", () => {
    expect(positionPercent(40, scale)).toBe(0);
    expect(positionPercent(900, scale)).toBe(100);
  });

  it("does not move on a scale with no width", () => {
    expect(positionPercent(200, { min: 200, max: 200 })).toBe(0);
  });
});

describe("the band for the middle of the group", () => {
  const scale = { min: 100, max: 300 };

  it("starts and ends where the two quartiles are", () => {
    const band = bandGeometry(150, 250, scale);

    expect(band.leftPercent).toBe(25);
    expect(band.widthPercent).toBe(50);
  });

  it("reads the two ends whichever way round they arrive", () => {
    expect(bandGeometry(250, 150, scale)).toEqual(bandGeometry(150, 250, scale));
  });

  it("stays wide enough for its two edge rules to be apart", () => {
    expect(bandGeometry(200, 200, scale).widthPercent).toBeGreaterThan(0);
  });
});

describe("the dot strip", () => {
  const scale = { min: 0, max: 100 };

  it("keeps one dot per mentor", () => {
    const placed = dotStripLayout([10, 20, 30, 40], scale);

    expect(placed).toHaveLength(4);
    expect(placed.map((dot) => dot.price)).toEqual([10, 20, 30, 40]);
  });

  it("places them cheapest first, whatever order they arrive in", () => {
    const placed = dotStripLayout([40, 10, 30, 20], scale);

    expect(placed.map((dot) => dot.price)).toEqual([10, 20, 30, 40]);
  });

  it("leaves well spread prices on one row", () => {
    const placed = dotStripLayout([0, 25, 50, 75, 100], scale);

    expect(placed.every((dot) => dot.row === 0)).toBe(true);
  });

  it("stacks mentors who charge about the same, so a cluster is not one dot", () => {
    const placed = dotStripLayout([50, 50.2, 50.4, 50.6], scale, {
      minGapPercent: 2.4,
    });

    expect(new Set(placed.map((dot) => dot.row)).size).toBe(4);
  });

  it("never uses more rows than it is allowed", () => {
    const crowded = Array.from({ length: 30 }, (_, index) => 50 + index * 0.01);
    const placed = dotStripLayout(crowded, scale, { rows: 5 });

    expect(Math.max(...placed.map((dot) => dot.row))).toBeLessThan(5);
  });

  it("puts each dot where its price is", () => {
    const placed = dotStripLayout([25, 75], scale);

    expect(placed[0].xPercent).toBe(25);
    expect(placed[1].xPercent).toBe(75);
  });
});

describe("months", () => {
  it("writes a month the way a person says it", () => {
    expect(monthShort("2024-10-01")).toBe("Oct");
    expect(monthLabel("2024-10-01")).toBe("October 2024");
  });

  it("says nothing about a month it cannot read", () => {
    expect(monthShort("")).toBe("");
    expect(monthLabel("not-a-date")).toBe("");
  });
});

describe("the reviews statistics", () => {
  const twelve = Array.from(
    { length: 12 },
    (_, index) => `2024-${String(index + 1).padStart(2, "0")}-01`,
  );
  const twentyFour = [
    ...Array.from(
      { length: 12 },
      (_, index) => `2023-${String(index + 1).padStart(2, "0")}-01`,
    ),
    ...twelve,
  ];

  it("adds up the most recent twelve months", () => {
    const stats = reviewStats(twelve, [2, 3, 4, 6, 7, 5, 3, 3, 5, 8, 4, 3]);

    expect(stats.recent).toBe(53);
    expect(stats.recentMonths).toBe(12);
  });

  it("compares the last twelve months with the twelve before", () => {
    const stats = reviewStats(twentyFour, [
      ...Array.from({ length: 12 }, () => 2),
      ...Array.from({ length: 12 }, () => 4),
    ]);

    expect(stats.recent).toBe(48);
    expect(stats.previous).toBe(24);
    expect(stats.direction).toBe("more");
  });

  it("says a fall is a fall", () => {
    const stats = reviewStats(twentyFour, [
      ...Array.from({ length: 12 }, () => 5),
      ...Array.from({ length: 12 }, () => 1),
    ]);

    expect(stats.direction).toBe("fewer");
  });

  it("claims no comparison when there is no earlier stretch to compare with", () => {
    const stats = reviewStats(
      twelve,
      Array.from({ length: 12 }, () => 3),
    );

    expect(stats.previousMonths).toBe(0);
    expect(stats.previous).toBe(0);
    expect(stats.direction).toBe("unknown");
  });

  it("finds the busiest month and names it", () => {
    const stats = reviewStats(twelve, [2, 3, 4, 6, 7, 5, 3, 3, 5, 8, 4, 3]);

    expect(stats.busiest).toEqual({
      iso: "2024-10-01",
      label: "October 2024",
      count: 8,
    });
  });

  it("keeps the first of two equally busy months rather than the last", () => {
    const stats = reviewStats(twelve, [9, 1, 1, 1, 1, 1, 1, 1, 1, 9, 1, 1]);

    expect(stats.busiest?.iso).toBe("2024-01-01");
  });

  it("names no busiest month when there are no reviews at all", () => {
    const stats = reviewStats(
      twelve,
      Array.from({ length: 12 }, () => 0),
    );

    expect(stats.busiest).toBeNull();
    expect(stats.total).toBe(0);
  });

  it("treats a missing count as none rather than failing", () => {
    const stats = reviewStats(["2024-01-01", "2024-02-01"], [3]);

    expect(stats.recent).toBe(3);
    expect(stats.recentMonths).toBe(2);
  });

  it("has nothing to say about a mentor with no months at all", () => {
    const stats = reviewStats([], []);

    expect(stats.recent).toBe(0);
    expect(stats.busiest).toBeNull();
  });

  it("agrees with the rule that decides chart against statistic card", () => {
    expect(MINIMUM_CHART_POINTS).toBe(4);
  });
});
