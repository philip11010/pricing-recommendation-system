"use client";

/**
 * One dot per comparable mentor, on the same price axis.
 *
 * A short, unaggregated set is better shown as the actual points than
 * summarised: a box plot needs roughly twenty points per group to mean
 * anything, and a histogram of a dozen mentors describes the bin width rather
 * than the market.
 *
 * This mentor is a ring of a different size and colour with a labelled leader
 * line, so they are told apart by shape as well as by hue. Every dot is
 * focusable and says its own price, and what hover shows is exactly what
 * focus shows. The same figures are in the table underneath.
 */

import { useState } from "react";

import { DataDisclosure } from "@/components/data-disclosure";
import { dotStripLayout, positionPercent, type Scale } from "@/lib/charts";
import { formatMoney } from "@/lib/format";

const WIDTH = 640;
const HEIGHT = 160;
const LEFT = 24;
const RIGHT = 24;
const AXIS_Y = 112;
const FIRST_ROW_Y = 96;
const ROW_GAP = 13;

function xOf(price: number, scale: Scale): number {
  return LEFT + ((WIDTH - LEFT - RIGHT) * positionPercent(price, scale)) / 100;
}

function ticksFor(scale: Scale, count = 5): number[] {
  const step = (scale.max - scale.min) / (count - 1);
  return Array.from({ length: count }, (_, index) =>
    Math.round(scale.min + step * index),
  );
}

export function DotStrip({
  prices,
  scale,
  yours = null,
  sentence,
  tableCaption,
  yoursLabel = "You",
}: {
  prices: number[];
  scale: Scale;
  yours?: number | null;
  /** States the answer in words. Read before the chart, by everyone. */
  sentence: string;
  tableCaption: string;
  yoursLabel?: string;
}) {
  const [active, setActive] = useState<number | null>(null);
  const placed = dotStripLayout(prices, scale);

  const sorted = [...prices].sort((a, b) => a - b);
  const rows = sorted.map((price, index) => [`${index + 1}`, formatMoney(price)]);

  return (
    <div>
      <p className="max-w-prose text-ink-700">{sentence}</p>

      <div className="mt-4 min-w-0">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="block h-auto w-full"
          role="img"
          aria-label={sentence}
          style={{ minHeight: 180 }}
        >
          <line
            x1={LEFT}
            x2={WIDTH - RIGHT}
            y1={AXIS_Y}
            y2={AXIS_Y}
            stroke="var(--line-strong)"
          />
          {ticksFor(scale).map((tick) => (
            <text
              key={tick}
              x={xOf(tick, scale)}
              y={AXIS_Y + 20}
              textAnchor="middle"
              fontSize="12"
              fill="var(--ink-500)"
            >
              {formatMoney(tick)}
            </text>
          ))}

          {placed.map((dot, index) => (
            <circle
              key={`${dot.price}-${index}`}
              cx={xOf(dot.price, scale)}
              cy={FIRST_ROW_Y - dot.row * ROW_GAP}
              r={active === index ? 8 : 6}
              fill="var(--ink-500)"
              tabIndex={0}
              role="img"
              aria-label={`A similar mentor charging ${formatMoney(dot.price)}`}
              onMouseEnter={() => setActive(index)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(index)}
              onBlur={() => setActive(null)}
            />
          ))}

          {yours !== null ? (
            <g>
              <text
                x={xOf(yours, scale)}
                y={18}
                textAnchor="middle"
                fontSize="13"
                fontWeight="700"
                fill="var(--accent-700)"
              >
                {yoursLabel} {formatMoney(yours)}
              </text>
              <line
                x1={xOf(yours, scale)}
                x2={xOf(yours, scale)}
                y1={24}
                y2={AXIS_Y - 10}
                stroke="var(--accent-700)"
                strokeWidth="1.5"
              />
              <circle
                cx={xOf(yours, scale)}
                cy={AXIS_Y}
                r={9}
                fill="var(--surface)"
                stroke="var(--accent-700)"
                strokeWidth="3"
              />
            </g>
          ) : null}
        </svg>
      </div>

      <p className="tabular min-h-[1.5rem] text-small text-ink-500" aria-live="polite">
        {active !== null && placed[active]
          ? `Highlighted: a mentor charging ${formatMoney(placed[active].price)}`
          : ""}
      </p>

      <DataDisclosure
        caption={tableCaption}
        columns={["Cheapest first", "Price per session in AUD"]}
        rows={rows}
      />
    </div>
  );
}
