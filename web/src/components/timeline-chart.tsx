"use client";

/**
 * What was suggested against what the mentor settled on, over time.
 *
 * The two lines are the whole point of keeping a record of decisions: the gap
 * between them is the only evidence this system will ever have about whether
 * its advice is worth taking.
 *
 * Both series are prices in AUD, so they share one axis. The chosen line
 * breaks wherever a suggestion has not been answered yet, rather than being
 * drawn through the gap, because a straight line across a pending decision
 * would invent a price the mentor never named.
 */

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { TimelinePoint } from "@/lib/api-types";
import { decisionWord } from "@/lib/copy";
import { formatAmount, formatDate, formatMoney } from "@/lib/format";

const SUGGESTED = "#0f9b8e";
const CHOSEN = "#a3521a";

interface Point {
  label: string;
  suggested: number;
  chosen: number | null;
  action: string | null;
}

function toPoints(timeline: TimelinePoint[]): Point[] {
  return timeline.map((point) => ({
    label: formatDate(point.generated_at),
    suggested: point.recommended_price,
    chosen: point.final_price,
    action: point.action,
  }));
}

function PointTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload?: Point }[];
}) {
  const point = active ? payload?.[0]?.payload : undefined;
  if (!point) {
    return null;
  }
  return (
    <div className="rounded-lg border border-line bg-white px-3 py-2 text-xs shadow-card">
      <p className="font-semibold text-ink">{point.label}</p>
      <p className="mt-0.5 text-ink-muted">Suggested {formatMoney(point.suggested)}</p>
      <p className="text-ink-muted">
        {point.chosen === null
          ? decisionWord(point.action)
          : `${decisionWord(point.action)} at ${formatMoney(point.chosen)}`}
      </p>
    </div>
  );
}

export function TimelineChart({ timeline }: { timeline: TimelinePoint[] }) {
  const points = toPoints(timeline);

  if (points.length === 0) {
    return null;
  }

  const answered = points.filter((point) => point.chosen !== null);
  const summary = [
    `${points.length} ${
      points.length === 1 ? "suggestion" : "suggestions"
    } for this service, oldest first, from ${points[0]!.label} to ${
      points[points.length - 1]!.label
    }.`,
    `The suggestions ran from ${formatMoney(
      Math.min(...points.map((point) => point.suggested)),
    )} to ${formatMoney(Math.max(...points.map((point) => point.suggested)))}.`,
    answered.length > 0
      ? `${answered.length} of them were answered with a price, from ${formatMoney(
          Math.min(...answered.map((point) => point.chosen as number)),
        )} to ${formatMoney(Math.max(...answered.map((point) => point.chosen as number)))}.`
      : "None of them has been answered with a price yet.",
  ].join(" ");

  return (
    <figure>
      <figcaption className="text-sm text-ink-muted">
        Suggested price against the price you settled on, in AUD.
      </figcaption>

      <p className="sr-only">{summary}</p>

      <div aria-hidden="true" className="mt-3 h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="#e3e6ea" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: "#6b7280", fontSize: 11 }}
              stroke="#e3e6ea"
              interval="preserveStartEnd"
              minTickGap={24}
            />
            <YAxis
              tick={{ fill: "#6b7280", fontSize: 11 }}
              stroke="#e3e6ea"
              width={48}
              tickFormatter={(value: number) => `$${formatAmount(value)}`}
            />
            <Tooltip content={<PointTooltip />} />
            <Legend
              verticalAlign="bottom"
              height={28}
              wrapperStyle={{ fontSize: 12, color: "#4b5563" }}
            />
            <Line
              type="monotone"
              name="Suggested"
              dataKey="suggested"
              stroke={SUGGESTED}
              strokeWidth={2}
              dot={{ r: 4, fill: SUGGESTED, stroke: "#ffffff", strokeWidth: 2 }}
              activeDot={{ r: 6 }}
            />
            <Line
              type="monotone"
              name="You chose"
              dataKey="chosen"
              stroke={CHOSEN}
              strokeWidth={2}
              strokeDasharray="5 3"
              connectNulls={false}
              dot={{ r: 4, fill: CHOSEN, stroke: "#ffffff", strokeWidth: 2 }}
              activeDot={{ r: 6 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <details className="mt-2">
        <summary className="cursor-pointer text-sm font-medium text-accent-800">
          Show these figures as a table
        </summary>
        <table className="mt-2 w-full text-left text-sm">
          <caption className="sr-only">
            Suggested price and the price settled on, oldest first
          </caption>
          <thead>
            <tr className="text-ink-soft">
              <th scope="col" className="py-1 font-medium">
                Date
              </th>
              <th scope="col" className="py-1 font-medium">
                Suggested
              </th>
              <th scope="col" className="py-1 font-medium">
                You chose
              </th>
            </tr>
          </thead>
          <tbody className="tabular">
            {points.map((point, index) => (
              <tr key={`${point.label}-${index}`} className="border-t border-line">
                <td className="py-1">{point.label}</td>
                <td className="py-1">{formatMoney(point.suggested)}</td>
                <td className="py-1">
                  {point.chosen === null
                    ? decisionWord(point.action)
                    : formatMoney(point.chosen)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
