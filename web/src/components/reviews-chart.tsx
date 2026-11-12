"use client";

/**
 * Reviews each month: one series, vertical bars.
 *
 * Bars rather than a line, because these are discrete per month tallies
 * rather than a continuous quantity. One accent, no second series, no
 * gradient fill, and the colours come from the custom properties so the chart
 * and the buttons are the same indigo.
 *
 * Animation is off. An animated chart delays the figure a mentor came for.
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

export function ReviewsChart({
  months,
  reviews,
  sentence,
  caption,
}: {
  months: string[];
  reviews: number[];
  /** States the answer in words. Read before the chart, by everyone. */
  sentence: string;
  caption: string;
}) {
  const data = months.map((iso, index) => ({
    iso,
    month: monthShort(iso),
    reviews: reviews[index] ?? 0,
  }));

  return (
    <div>
      <p className="max-w-prose text-ink-700">{sentence}</p>

      <div role="img" aria-label={sentence} className="mt-4 h-[240px] w-full min-w-0">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis
              dataKey="month"
              tickLine={false}
              axisLine={{ stroke: "var(--line-strong)" }}
              tick={{ fill: "var(--ink-500)", fontSize: 12 }}
              interval="preserveStartEnd"
            />
            <YAxis
              allowDecimals={false}
              tickLine={false}
              axisLine={false}
              width={36}
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
        columns={["Month", "Reviews"]}
        rows={data.map((point) => [monthLabel(point.iso), String(point.reviews)])}
      />
    </div>
  );
}
