"use client";

/**
 * The spread of session prices among comparable mentors.
 *
 * A histogram rather than a single average, because that is the honest shape
 * of the answer: prices in any field have a long upper tail, and a mean sits
 * above most of the mentors it claims to describe. A mentor reading a bar
 * chart can see that for themselves.
 *
 * The API sends edges and counts and no drawing instructions, so everything
 * about how it looks is decided here.
 *
 * Two annotations sit on top of the bars: where the suggestion falls, and
 * where the mentor's own price falls. Both are labelled in words as well as
 * drawn, so neither depends on telling two colours apart, and the same
 * figures are available as a table underneath for anyone who would rather
 * read them.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { PriceHistogram as PriceHistogramData } from "@/lib/api-types";
import { formatAmount, formatMoney } from "@/lib/format";

/** The one hue the bars use. A single series needs no second colour. */
const BAR = "#0f9b8e";
/** The bin the suggestion falls in, drawn a shade darker. */
const BAR_SUGGESTED = "#115553";
/** The mentor's own price. Validated against the bar hue for colour vision. */
const CURRENT = "#a3521a";
const INK = "#111827";

interface Bin {
  name: string;
  start: number;
  end: number;
  count: number;
}

function toBins(histogram: PriceHistogramData): Bin[] {
  const { bin_edges: edges, counts } = histogram;
  if (edges.length < 2 || counts.length === 0) {
    return [];
  }
  const bins: Bin[] = [];
  for (let index = 0; index < counts.length; index += 1) {
    const start = edges[index];
    const end = edges[index + 1];
    const count = counts[index];
    if (start === undefined || end === undefined || count === undefined) {
      continue;
    }
    bins.push({ name: formatAmount(start), start, end, count });
  }
  return bins;
}

/**
 * Which bar a price belongs over.
 *
 * A price outside the whole spread is pinned to the nearest end rather than
 * dropped: "your price is off the right hand end" is the most useful thing
 * the chart could possibly say, and the exact figure is in the label beside
 * it.
 */
function binIndexOf(bins: Bin[], price: number): number | null {
  if (bins.length === 0) {
    return null;
  }
  for (let index = 0; index < bins.length; index += 1) {
    const bin = bins[index];
    if (!bin) {
      continue;
    }
    const last = index === bins.length - 1;
    if (price >= bin.start && (price < bin.end || (last && price <= bin.end))) {
      return index;
    }
  }
  const first = bins[0];
  return first && price < first.start ? 0 : bins.length - 1;
}

function BinTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload?: Bin }[];
}) {
  const bin = active ? payload?.[0]?.payload : undefined;
  if (!bin) {
    return null;
  }
  return (
    <div className="rounded-lg border border-line bg-white px-3 py-2 text-xs shadow-card">
      <p className="font-semibold text-ink">
        {formatMoney(bin.start)} to {formatMoney(bin.end)}
      </p>
      <p className="mt-0.5 text-ink-muted">
        {bin.count} {bin.count === 1 ? "mentor" : "mentors"}
      </p>
    </div>
  );
}

export function PriceHistogram({
  histogram,
  suggestedPrice,
  currentPrice,
  totalCount,
}: {
  histogram: PriceHistogramData;
  suggestedPrice: number;
  currentPrice?: number | null;
  /** How many mentors the whole spread covers, for the text summary. */
  totalCount: number;
}) {
  const bins = toBins(histogram);

  if (bins.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-line bg-shell p-4 text-sm text-ink-muted">
        There are not enough comparable mentors to show a spread of prices.
      </p>
    );
  }

  const suggestedIndex = binIndexOf(bins, suggestedPrice);
  const currentIndex =
    currentPrice === null || currentPrice === undefined
      ? null
      : binIndexOf(bins, currentPrice);

  const busiest = bins.reduce(
    (best, bin) => (bin.count > best.count ? bin : best),
    bins[0]!,
  );

  const summary = [
    `A spread of session prices for ${totalCount} comparable ${
      totalCount === 1 ? "mentor" : "mentors"
    }, in ${bins.length} price bands from ${formatMoney(bins[0]!.start)} to ${formatMoney(
      bins[bins.length - 1]!.end,
    )}.`,
    `Most of them, ${busiest.count} in all, charge between ${formatMoney(
      busiest.start,
    )} and ${formatMoney(busiest.end)}.`,
    `Your suggested price of ${formatMoney(suggestedPrice)} falls in the band from ${formatMoney(
      bins[suggestedIndex ?? 0]!.start,
    )}.`,
    currentIndex !== null && currentPrice
      ? `You currently charge ${formatMoney(currentPrice)}.`
      : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <figure className="mt-2">
      <figcaption className="text-sm text-ink-muted">
        What comparable mentors charge for one session, and where your figures sit.
      </figcaption>

      <p className="sr-only">{summary}</p>

      <div aria-hidden="true" className="mt-3 h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={bins} margin={{ top: 18, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="#e3e6ea" vertical={false} />
            <XAxis
              dataKey="name"
              tick={{ fill: "#6b7280", fontSize: 11 }}
              stroke="#e3e6ea"
              interval="preserveStartEnd"
              minTickGap={24}
              tickFormatter={(value: string) => `$${value}`}
            />
            <YAxis
              tick={{ fill: "#6b7280", fontSize: 11 }}
              stroke="#e3e6ea"
              allowDecimals={false}
              width={34}
            />
            <Tooltip
              content={<BinTooltip />}
              cursor={{ fill: "rgba(17, 24, 39, 0.04)" }}
            />
            <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={44}>
              {bins.map((bin, index) => (
                <Cell
                  key={bin.name}
                  fill={index === suggestedIndex ? BAR_SUGGESTED : BAR}
                />
              ))}
            </Bar>
            {suggestedIndex !== null ? (
              <ReferenceLine
                x={bins[suggestedIndex]!.name}
                stroke={INK}
                strokeWidth={2}
                label={{
                  value: "Suggested",
                  position: "top",
                  fill: INK,
                  fontSize: 11,
                  fontWeight: 600,
                }}
              />
            ) : null}
            {currentIndex !== null ? (
              <ReferenceLine
                x={bins[currentIndex]!.name}
                stroke={CURRENT}
                strokeWidth={2}
                strokeDasharray="5 3"
                label={{
                  value: "Your price",
                  position: "top",
                  fill: CURRENT,
                  fontSize: 11,
                  fontWeight: 600,
                }}
              />
            ) : null}
          </BarChart>
        </ResponsiveContainer>
      </div>

      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-muted">
        <li className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className="h-2.5 w-2.5 rounded-sm"
            style={{ background: BAR }}
          />
          Comparable mentors
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden="true" className="h-0.5 w-4" style={{ background: INK }} />
          Suggested {formatMoney(suggestedPrice)}
        </li>
        {currentPrice ? (
          <li className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="h-0.5 w-4"
              style={{ background: CURRENT }}
            />
            You charge {formatMoney(currentPrice)}
          </li>
        ) : null}
      </ul>

      <details className="mt-3">
        <summary className="cursor-pointer text-sm font-medium text-accent-800">
          Show these figures as a table
        </summary>
        <table className="mt-2 w-full text-left text-sm">
          <caption className="sr-only">
            Comparable mentors counted by session price band
          </caption>
          <thead>
            <tr className="text-ink-soft">
              <th scope="col" className="py-1 font-medium">
                Price band
              </th>
              <th scope="col" className="py-1 font-medium">
                Mentors
              </th>
            </tr>
          </thead>
          <tbody className="tabular">
            {bins.map((bin) => (
              <tr key={bin.name} className="border-t border-line">
                <td className="py-1">
                  {formatMoney(bin.start)} to {formatMoney(bin.end)}
                </td>
                <td className="py-1">{bin.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
