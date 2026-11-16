"use client";

/**
 * Activity over the recent months, as a small chart.
 *
 * The one thing the platform measures month by month is how many reviews a
 * mentor received, so that is what this draws. There is no record of how
 * busy a mentor was in a given month and none of what they charged in one,
 * so neither is drawn here: a line through months nobody measured would be
 * an invention dressed as a chart.
 *
 * Bars rather than a line, by the rule in DESIGN.md 8.1: these are discrete
 * per-month tallies rather than a continuous quantity.
 *
 * It describes and never advises. A busy month is not a reason to charge
 * more and a quiet one is not a reason to charge less, and this card is in
 * no position to know which way either should go, so it says what the months
 * hold and stops there.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";

import { DataDisclosure } from "@/components/data-disclosure";
import { monthLabel, monthShort } from "@/lib/charts";

/** How many months the small chart draws. Twelve would be the other chart. */
export const DEMAND_CHART_MONTHS = 6;

export interface DemandPoint {
  iso: string;
  reviews: number;
}

/** The most recent months of the series, newest last. */
export function recentMonths(
  months: string[],
  reviews: number[],
  count: number = DEMAND_CHART_MONTHS,
): DemandPoint[] {
  const start = Math.max(0, months.length - count);
  return months.slice(start).map((iso, index) => {
    const value = reviews[start + index];
    return {
      iso,
      reviews: typeof value === "number" && Number.isFinite(value) ? value : 0,
    };
  });
}

/**
 * What the chart shows, in a sentence, with no claim about price in it.
 *
 * Read aloud by a screen reader in place of the chart, and printed above it
 * for everybody else, so the two audiences are told the same thing.
 */
export function demandSummary(points: DemandPoint[]): string {
  if (points.length === 0) {
    return "No reviews have been recorded yet.";
  }
  const total = points.reduce((sum, point) => sum + point.reviews, 0);
  const span =
    points.length === 1
      ? monthLabel(points[0].iso)
      : `${monthLabel(points[0].iso)} to ${monthLabel(points[points.length - 1].iso)}`;
  const busiest = points.reduce((most, point) =>
    point.reviews > most.reviews ? point : most,
  );
  const reviews = total === 1 ? "review" : "reviews";
  if (busiest.reviews === 0) {
    return `No reviews were recorded from ${span}.`;
  }
  return `${total} ${reviews} from ${span}, with the most in ${monthLabel(busiest.iso)}.`;
}

export function DemandChart({
  months,
  reviews,
  caption,
}: {
  months: string[];
  reviews: number[];
  caption: string;
}) {
  const points = recentMonths(months, reviews);
  const sentence = demandSummary(points);

  return (
    <div>
      <p className="max-w-prose text-ink-700">{sentence}</p>

      {/* 180px is the floor in DESIGN.md 8.4, and the width is unconstrained
          so the six bars stay apart at 360px. */}
      <div role="img" aria-label={sentence} className="mt-4 h-[180px] w-full min-w-0">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis
              dataKey="iso"
              tickFormatter={monthShort}
              tickLine={false}
              axisLine={{ stroke: "var(--line-strong)" }}
              tick={{ fill: "var(--ink-500)", fontSize: 12 }}
              interval={0}
            />
            <YAxis
              allowDecimals={false}
              tickLine={false}
              axisLine={false}
              width={32}
              tick={{ fill: "var(--ink-500)", fontSize: 12 }}
            />
            <Bar
              dataKey="reviews"
              fill="var(--accent-700)"
              radius={[6, 6, 0, 0]}
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <DataDisclosure
        caption={caption}
        summaryLabel="View the numbers"
        columns={["Month", "Reviews"]}
        rows={points.map((point) => [
          monthLabel(point.iso),
          <span key={point.iso} className="tabular">
            {point.reviews}
          </span>,
        ])}
      />
    </div>
  );
}
