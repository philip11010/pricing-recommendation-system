"use client";

/**
 * Who a price is compared against, and what they charge.
 *
 * The rows carry no names and no ids, because this is a distribution rather
 * than a list of other people's accounts. Every figure on a row is one a
 * mentor would recognise about themselves: their field, the size of their
 * session, what they charge, their rating and how much of their offered time
 * gets booked.
 *
 * The summary describes the whole match however few rows are on screen, so
 * paging through them never changes what the mentor is told about the market.
 */

import type { ComparableItem, ComparablesSummary } from "@/lib/api-types";
import { NO_COMPARABLES_NOTE, WIDENED_NOTE } from "@/lib/copy";
import { formatMentees, formatMoney, formatPercent, formatRating } from "@/lib/format";

import { Badge, Callout } from "./ui";

/**
 * The one sentence a mentor reads before anything else.
 *
 * Median and quartiles rather than an average: a mean sits above most of the
 * mentors it claims to describe, which would quietly tell every mentor they
 * are underpriced.
 */
export function ComparablesSummaryLine({ summary }: { summary: ComparablesSummary }) {
  if (summary.count === 0) {
    return <Callout tone="quiet">{NO_COMPARABLES_NOTE}</Callout>;
  }

  return (
    <div className="space-y-3">
      <p className="text-base leading-relaxed">
        The middle of this group charges{" "}
        <strong className="tabular font-semibold">
          {formatMoney(summary.median_price)}
        </strong>{" "}
        a session, and the middle half of them charge between{" "}
        <strong className="tabular font-semibold">
          {formatMoney(summary.p25_price)}
        </strong>{" "}
        and{" "}
        <strong className="tabular font-semibold">
          {formatMoney(summary.p75_price)}
        </strong>
        .
      </p>
      <p className="flex flex-wrap items-center gap-2 text-sm text-ink-muted">
        <span>
          Based on {summary.count} {summary.count === 1 ? "mentor" : "mentors"}:{" "}
          {summary.match_description}.
        </span>
        {summary.widened ? <Badge tone="caution">Showing a wider set</Badge> : null}
      </p>
      {summary.widened ? <Callout tone="caution">{WIDENED_NOTE}</Callout> : null}
    </div>
  );
}

/** One comparable mentor, written as a line rather than a table row. */
function ComparableRow({ item }: { item: ComparableItem }) {
  return (
    <li className="border-t border-line py-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="text-sm font-medium text-ink">
          {item.field_label}
          <span className="text-ink-soft"> · </span>
          {item.session_label}
          <span className="text-ink-soft">
            {" "}
            · up to {formatMentees(item.max_mentees)}
          </span>
        </p>
        <p className="tabular text-sm font-semibold">
          {formatMoney(item.price)}
          <span className="font-normal text-ink-soft">
            {" "}
            ({formatMoney(item.price_per_mentee)} per mentee)
          </span>
        </p>
      </div>
      <p className="mt-1 text-xs text-ink-soft">
        Rated {formatRating(item.rating_overall)} from {item.reviews_total}{" "}
        {item.reviews_total === 1 ? "review" : "reviews"}
        <span> · </span>
        {formatPercent(item.booked_share_percent, { decimals: 0 })} of their offered
        time booked over the last year
      </p>
    </li>
  );
}

export function ComparableRows({
  items,
  emptyMessage = "No mentors to show on this page.",
}: {
  items: ComparableItem[];
  emptyMessage?: string;
}) {
  if (items.length === 0) {
    return <p className="py-4 text-sm text-ink-muted">{emptyMessage}</p>;
  }
  return (
    <ul className="mt-1">
      {items.map((item, index) => (
        <ComparableRow
          key={`${item.price}-${item.rating_overall}-${index}`}
          item={item}
        />
      ))}
    </ul>
  );
}
