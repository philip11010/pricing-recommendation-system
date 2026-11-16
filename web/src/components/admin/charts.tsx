"use client";

/**
 * The charts the administration pages are built from.
 *
 * Five shapes, each with the same four parts, in the same order, because
 * DESIGN.md section 8 asks for all four on every chart in the product and an
 * operations page is no exception:
 *
 * 1. a heading,
 * 2. the plain-language sentence that states the answer,
 * 3. the chart, wrapped as `role="img"` with that same sentence as its label,
 * 4. the same figures as a real table, behind a disclosure.
 *
 * **The series scale.** Where a chart needs more than one series these use
 * three steps and no more: `accent-700` indigo, the pale `chart-band` blue
 * with a 2px `chart-band-edge` rule, and `ink-500`. Measured against each
 * other, indigo to band is 5.95:1 and band to ink is 5.55:1, so adjacent
 * segments of a stack are told apart in greyscale as well as in colour. The
 * pale band is 1.33:1 on white, which is why it never appears without its
 * edge rule: that is the same belt-and-braces the price ladder uses, for the
 * same reason.
 *
 * **Nothing is carried by colour alone.** Every stack is in a fixed order
 * with a swatch legend naming each step, every line chart labels its second
 * series directly, and every chart is followed by the table.
 *
 * Recharts animation is off throughout. An animated chart delays the figure
 * somebody opened the page for.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import type { ReactNode } from "react";

import { DataDisclosure } from "@/components/data-disclosure";
import { EmptyState } from "@/components/ui";
import { NO_ACTIVITY, type ShareSegment } from "@/lib/admin";

/** The three fills, in the order a stack uses them. */
const SERIES = ["var(--accent-700)", "var(--chart-band)", "var(--ink-500)"];

/** The pale middle step never appears without its edge rule. */
const SERIES_EDGE = ["none", "var(--chart-band-edge)", "none"];

/** The same three as a background class, for the legend swatches. */
const SWATCH = [
  "bg-accent-700",
  "bg-chart-band ring-2 ring-inset ring-chart-edge",
  "bg-ink-500",
];

const AXIS = {
  tickLine: false as const,
  tick: { fill: "var(--ink-500)", fontSize: 12 },
};

/**
 * A chart and everything that has to sit around one.
 *
 * A region rather than a plain div, so the page can be navigated section by
 * section and so a test can address one chart without guessing at its markup.
 */
export function ChartCard({
  title,
  sentence,
  note,
  legend,
  empty,
  children,
  caption,
  columns,
  rows,
}: {
  title: string;
  sentence: string;
  note?: ReactNode;
  /** A swatch legend, where the chart has more than one series. */
  legend?: ReactNode;
  /** True when there is nothing to draw, which is a state and not a failure. */
  empty: boolean;
  children: ReactNode;
  caption: string;
  columns: string[];
  rows: ReactNode[][];
}) {
  return (
    <section
      aria-label={title}
      className="min-w-0 rounded-chart border border-line bg-surface p-5 mid:p-6"
    >
      <h3 className="text-h3 font-bold">{title}</h3>
      <p className="mt-2 max-w-prose text-small text-ink-700">{sentence}</p>
      {note ? <p className="mt-1 max-w-prose text-small text-ink-500">{note}</p> : null}

      {empty ? (
        <div className="mt-4">
          <EmptyState title={NO_ACTIVITY}>
            There is nothing to draw here until the platform has been used.
          </EmptyState>
        </div>
      ) : (
        <>
          {legend}
          <div role="img" aria-label={sentence} className="mt-4 w-full min-w-0">
            {children}
          </div>
          <DataDisclosure caption={caption} columns={columns} rows={rows} />
        </>
      )}
    </section>
  );
}

/**
 * The swatch legend a stacked chart carries instead of a colour key.
 *
 * Every entry names its series in words beside its swatch, so the stack is
 * readable without telling the three fills apart, and the order of the
 * entries is the order of the stack.
 */
export function Legend({ segments }: { segments: ShareSegment[] }) {
  return (
    <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
      {segments.map((segment, index) => (
        <li
          key={segment.id}
          className="flex items-center gap-2 text-small text-ink-700"
        >
          <span
            aria-hidden="true"
            className={`h-3 w-3 flex-none rounded-[3px] ${SWATCH[index % SWATCH.length]}`}
          />
          <span>
            {segment.label}
            <span className="tabular ml-1.5 font-semibold text-ink-900">
              {segment.count.toLocaleString()}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * One horizontal bar divided into its shares.
 *
 * Used where the question is "how does this divide" rather than "how has it
 * moved", which is a single bar and not a pie: a pie of three slices spends a
 * lot of space saying what three numbers say, and the labels have nowhere to
 * go on a phone.
 *
 * Plain markup rather than a chart library, because a one-bar chart is two
 * divs and a percentage.
 */
export function ShareBar({
  segments,
  title,
  sentence,
  caption,
}: {
  segments: ShareSegment[];
  title: string;
  sentence: string;
  caption: string;
}) {
  const total = segments.reduce((sum, segment) => sum + segment.count, 0);

  return (
    <section
      aria-label={title}
      className="min-w-0 rounded-chart border border-line bg-surface p-5 mid:p-6"
    >
      <h3 className="text-h3 font-bold">{title}</h3>
      <p className="mt-2 max-w-prose text-small text-ink-700">{sentence}</p>

      {total === 0 ? (
        <div className="mt-4">
          <EmptyState title={NO_ACTIVITY}>
            There is nothing to divide up until the platform has been used.
          </EmptyState>
        </div>
      ) : (
        <>
          <Legend segments={segments} />
          <div
            role="img"
            aria-label={sentence}
            className="mt-4 flex h-8 w-full min-w-0 overflow-hidden rounded-pill border border-line"
          >
            {segments.map((segment, index) =>
              segment.count === 0 ? null : (
                <span
                  key={segment.id}
                  style={{
                    width: `${segment.percent}%`,
                    background: SERIES[index % SERIES.length],
                    boxShadow:
                      SERIES_EDGE[index % SERIES_EDGE.length] === "none"
                        ? undefined
                        : `inset 0 0 0 2px ${SERIES_EDGE[index % SERIES_EDGE.length]}`,
                  }}
                />
              ),
            )}
          </div>
          <DataDisclosure
            caption={caption}
            columns={["Category", "Count", "Share"]}
            rows={segments.map((segment) => [
              segment.label,
              <span key={`${segment.id}-count`} className="tabular">
                {segment.count.toLocaleString()}
              </span>,
              <span key={`${segment.id}-share`} className="tabular">
                {segment.percent}%
              </span>,
            ])}
          />
        </>
      )}
    </section>
  );
}

/**
 * The legend for a chart whose series are lines rather than blocks.
 *
 * The swatch reproduces the stroke it stands for, dash pattern included, so
 * the dashed series is identified by its dashes and not only by being the
 * paler of two greys. DESIGN.md 8.2 allows a second series as a dashed
 * ink-500 line, and this is how the reader is told which one it is.
 */
export function LineLegend({
  series,
}: {
  series: Array<{ id: string; label: string; dashed?: boolean }>;
}) {
  return (
    <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
      {series.map((entry) => (
        <li key={entry.id} className="flex items-center gap-2 text-small text-ink-700">
          <svg
            width="22"
            height="8"
            viewBox="0 0 22 8"
            aria-hidden="true"
            focusable="false"
            className="flex-none"
          >
            <line
              x1="1"
              y1="4"
              x2="21"
              y2="4"
              stroke={entry.dashed ? "var(--ink-500)" : "var(--accent-700)"}
              strokeWidth={entry.dashed ? 2 : 2.5}
              strokeDasharray={entry.dashed ? "5 3" : undefined}
            />
          </svg>
          <span>{entry.label}</span>
        </li>
      ))}
    </ul>
  );
}

export interface StackSeries {
  key: string;
  label: string;
}

/**
 * Counts over time, stacked.
 *
 * Bars rather than a line, by the rule in DESIGN.md 8.1: these are discrete
 * per-day tallies rather than a continuous quantity, and a line through them
 * would read as a rate.
 */
export function StackedBars<Row>({
  data,
  xKey,
  series,
  tickFormatter,
  height = 240,
}: {
  data: Row[];
  xKey: string;
  series: StackSeries[];
  tickFormatter: (value: string) => string;
  height?: number;
}) {
  return (
    <div style={{ height }} className="w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
          <XAxis
            dataKey={xKey}
            tickFormatter={tickFormatter}
            axisLine={{ stroke: "var(--line-strong)" }}
            interval="preserveStartEnd"
            minTickGap={24}
            {...AXIS}
          />
          <YAxis allowDecimals={false} axisLine={false} width={36} {...AXIS} />
          {series.map((entry, index) => (
            <Bar
              key={entry.key}
              dataKey={entry.key}
              name={entry.label}
              stackId="one"
              fill={SERIES[index % SERIES.length]}
              stroke={SERIES_EDGE[index % SERIES_EDGE.length]}
              strokeWidth={SERIES_EDGE[index % SERIES_EDGE.length] === "none" ? 0 : 2}
              isAnimationActive={false}
              // Only the top of the stack is rounded, so the segments of one
              // day read as one bar rather than as stacked pills.
              radius={index === series.length - 1 ? [4, 4, 0, 0] : undefined}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/**
 * One series of counts across named categories, drawn horizontally.
 *
 * Horizontal because the categories are sentences, and DESIGN.md 8.3 says a
 * chart whose tick labels would have to rotate past 45 degrees becomes
 * horizontal instead.
 */
export function CategoryBars({
  data,
  height,
}: {
  data: Array<{ label: string; count: number }>;
  height?: number;
}) {
  return (
    <div
      style={{ height: height ?? Math.max(160, data.length * 40 + 40) }}
      className="w-full min-w-0"
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 16, bottom: 0, left: 0 }}
        >
          <CartesianGrid horizontal={false} stroke="var(--chart-grid)" />
          <XAxis
            type="number"
            allowDecimals={false}
            axisLine={{ stroke: "var(--line-strong)" }}
            {...AXIS}
          />
          <YAxis
            type="category"
            dataKey="label"
            axisLine={false}
            width={132}
            {...AXIS}
          />
          <Bar
            dataKey="count"
            fill="var(--accent-700)"
            radius={[0, 4, 4, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** A histogram: counts per half-open bucket, vertical bars, one series. */
export function HistogramBars({
  data,
  height = 220,
}: {
  data: Array<{ tick: string; count: number }>;
  height?: number;
}) {
  return (
    <div style={{ height }} className="w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
          <XAxis
            dataKey="tick"
            axisLine={{ stroke: "var(--line-strong)" }}
            interval="preserveStartEnd"
            minTickGap={16}
            {...AXIS}
          />
          <YAxis allowDecimals={false} axisLine={false} width={36} {...AXIS} />
          <Bar
            dataKey="count"
            fill="var(--accent-700)"
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/**
 * Two durations over time: the middle one solid, the slow tail dashed.
 *
 * The second series is `ink-500` and dashed, which is what DESIGN.md 8.2
 * allows for a second series, so the two lines are told apart by dash pattern
 * as well as by colour.
 *
 * Only drawn from four days or more. Below that the section shows statistic
 * cards instead, by the rule in DESIGN.md 8.1: a line through three points
 * invents a trend, and the whole purpose of this chart is to show one.
 */
export function LatencyLines({
  data,
  height = 240,
}: {
  data: Array<{ day: string; median_ms: number; p95_ms: number }>;
  height?: number;
}) {
  return (
    <div style={{ height }} className="w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
          <XAxis
            dataKey="day"
            tickFormatter={(value: string) => value.slice(8, 10)}
            axisLine={{ stroke: "var(--line-strong)" }}
            interval="preserveStartEnd"
            minTickGap={20}
            {...AXIS}
          />
          <YAxis allowDecimals={false} axisLine={false} width={44} {...AXIS} />
          <Line
            dataKey="p95_ms"
            name="95th percentile"
            stroke="var(--ink-500)"
            strokeWidth={2}
            strokeDasharray="6 4"
            dot={{ r: 2.5, fill: "var(--ink-500)" }}
            isAnimationActive={false}
          />
          <Line
            dataKey="median_ms"
            name="Median"
            stroke="var(--accent-700)"
            strokeWidth={2.5}
            dot={{ r: 3, fill: "var(--accent-700)" }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
