/**
 * Where one price sits against what similar mentors charge.
 *
 * A horizontal low to high track, a shaded band for the middle of the group,
 * a filled triangle for the suggested price and an open circle for the price
 * the mentor charges now. The bullet chart form rather than a gauge: this is
 * a performance against range question, it reads at a glance, and it fits a
 * phone without a legend of series.
 *
 * The band is never identified by its fill alone. It carries two edge rules
 * and a text label with both end values, and the two markers differ in shape
 * as well as in colour, so the chart survives in greyscale. Nothing is
 * revealed on hover, so there is nothing for a keyboard to miss.
 */

import { DataDisclosure } from "@/components/data-disclosure";
import { bandGeometry, positionPercent, type Scale } from "@/lib/charts";
import { formatMoney } from "@/lib/format";

export interface PriceLadderProps {
  scale: Scale;
  /** The middle of the group, usually the quartiles. */
  bandLow: number | null;
  bandHigh: number | null;
  suggested?: number | null;
  current?: number | null;
  /** States the answer in words. Read before the chart, by everyone. */
  sentence: string;
  tableCaption: string;
  suggestedLabel?: string;
  currentLabel?: string;
}

export function PriceLadder({
  scale,
  bandLow,
  bandHigh,
  suggested = null,
  current = null,
  sentence,
  tableCaption,
  suggestedLabel = "Suggested",
  currentLabel = "Your price now",
}: PriceLadderProps) {
  const hasBand = bandLow !== null && bandHigh !== null;
  const band = hasBand ? bandGeometry(bandLow, bandHigh, scale) : null;

  const rows: string[][] = [
    ["Lowest shown", formatMoney(scale.min)],
    ["Highest shown", formatMoney(scale.max)],
  ];
  if (hasBand) {
    rows.splice(1, 0, [
      "Where most mentors sit",
      `${formatMoney(bandLow)} to ${formatMoney(bandHigh)}`,
    ]);
  }
  if (suggested !== null) {
    rows.push([suggestedLabel, formatMoney(suggested)]);
  }
  if (current !== null) {
    rows.push([currentLabel, formatMoney(current)]);
  }

  return (
    <div>
      <p className="max-w-prose text-ink-700">{sentence}</p>

      <div role="img" aria-label={sentence} className="mt-5 min-w-0 pt-6">
        <div className="relative h-3 rounded-bar bg-chart-track">
          {band ? (
            <div
              className="absolute inset-y-0 border-l-2 border-r-2 border-chart-edge bg-chart-band"
              style={{ left: `${band.leftPercent}%`, width: `${band.widthPercent}%` }}
            />
          ) : null}

          {suggested !== null ? (
            <span
              aria-hidden="true"
              className="absolute -top-[9px] h-0 w-0 -translate-x-2 border-x-8 border-t-[12px] border-x-transparent border-t-accent-700"
              style={{ left: `${positionPercent(suggested, scale)}%` }}
            />
          ) : null}

          {current !== null ? (
            <span
              aria-hidden="true"
              className="absolute -top-[3px] h-4 w-4 -translate-x-2 rounded-pill border-2 border-ink-900 bg-surface"
              style={{ left: `${positionPercent(current, scale)}%` }}
            />
          ) : null}
        </div>

        <div className="mt-2 flex flex-wrap justify-between gap-2 text-[0.8125rem] text-ink-500">
          <span>{formatMoney(scale.min)}</span>
          {hasBand ? (
            <span>
              {formatMoney(bandLow)} to {formatMoney(bandHigh)} typical
            </span>
          ) : null}
          <span>{formatMoney(scale.max)}</span>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-4 text-[0.8125rem] text-ink-700">
        {suggested !== null ? (
          <span className="inline-flex items-center gap-1.5">
            <i
              aria-hidden="true"
              className="h-0 w-0 border-x-[6px] border-t-[9px] border-x-transparent border-t-accent-700"
            />
            {suggestedLabel} {formatMoney(suggested)}
          </span>
        ) : null}
        {current !== null ? (
          <span className="inline-flex items-center gap-1.5">
            <i
              aria-hidden="true"
              className="h-3 w-3 rounded-pill border-2 border-ink-900"
            />
            {currentLabel} {formatMoney(current)}
          </span>
        ) : null}
        {hasBand ? (
          <span className="inline-flex items-center gap-1.5">
            <i
              aria-hidden="true"
              className="h-2.5 w-[18px] border-x-2 border-chart-edge bg-chart-band"
            />
            Where most mentors sit
          </span>
        ) : null}
      </div>

      <DataDisclosure
        caption={tableCaption}
        columns={["What", "Price in AUD"]}
        rows={rows}
      />
    </div>
  );
}
