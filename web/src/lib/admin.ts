/**
 * The arithmetic and the sentences behind the administration charts.
 *
 * Kept out of the components for the same reason as `charts.ts`: a sentence
 * that states the answer above a chart is the part a screen reader is given
 * in place of the chart, so it has to be right, and it can only be tested
 * where it can be called.
 *
 * Nothing here knows a colour or a pixel. It returns numbers, labels and
 * sentences, which the components turn into marks.
 *
 * Two rules run through all of it.
 *
 * **Null is not zero.** A day with no calls has no median response time and a
 * platform with no decisions has no acceptance rate. Every sentence here says
 * so in words rather than printing a zero, because a zero is a measurement
 * and these are the absence of one.
 *
 * **Dates are read off the string.** `new Date("2026-11-16")` is midnight UTC,
 * and formatting that in a browser west of Greenwich prints the day before.
 * The API sends plain dates, so they are parsed by position instead.
 */

import type {
  AdminDecisionCounts,
  AdminLatencyDay,
  AdminModelShare,
  AdminOutputs,
  AdminSignups,
  AdminUsageDay,
  HistogramBucket,
  LabelledCount,
} from "./api-types";
import { formatMoney } from "./format";

/* ------------------------------------------------------------------ dates */

const MONTHS_SHORT = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

const MONTHS_LONG = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

function parts(iso: string): { year: string; month: number; day: number } | null {
  const text = iso ?? "";
  const year = text.slice(0, 4);
  const month = Number.parseInt(text.slice(5, 7), 10);
  const day = Number.parseInt(text.slice(8, 10), 10);
  if (year.length !== 4 || !Number.isInteger(month) || month < 1 || month > 12) {
    return null;
  }
  return { year, month, day: Number.isInteger(day) ? day : 1 };
}

/** "2026-11-16" as "16 Nov", for an axis tick. */
export function dayTick(iso: string): string {
  const found = parts(iso);
  return found ? `${found.day} ${MONTHS_SHORT[found.month - 1]}` : "";
}

/** "2026-11-16" as "16 November 2026", for a table cell. */
export function dayLabel(iso: string): string {
  const found = parts(iso);
  return found ? `${found.day} ${MONTHS_LONG[found.month - 1]} ${found.year}` : "";
}

/** The Monday of a week, as "week of 16 Nov". */
export function weekTick(iso: string): string {
  const tick = dayTick(iso);
  return tick ? tick : "";
}

/** The Monday of a week, as "Week of 16 November 2026". */
export function weekLabel(iso: string): string {
  const label = dayLabel(iso);
  return label ? `Week of ${label}` : "";
}

/* ----------------------------------------------------------------- counts */

/** "1 call", "14 calls". */
export function calls(count: number): string {
  return `${count.toLocaleString()} ${count === 1 ? "call" : "calls"}`;
}

/** A duration in milliseconds, or the words for not having measured one. */
export function formatMilliseconds(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "Not measured yet";
  }
  return `${Math.round(value).toLocaleString()} ms`;
}

/** One histogram bucket, written as the half-open interval it is. */
export function bucketTick(bucket: HistogramBucket): string {
  return bucket.low.toLocaleString();
}

/** One histogram bucket in words, for a table and a screen reader. */
export function bucketLabel(bucket: HistogramBucket, currency: string): string {
  return `${formatMoney(bucket.low)} to under ${formatMoney(bucket.high)} ${currency}`;
}

/* -------------------------------------------------------------- sentences */

export const NO_ACTIVITY = "No activity yet";

/**
 * Calls per day, split by model, in one sentence.
 *
 * Says the no-model count out loud when there is one. Those are calls the
 * service did work for and priced nothing: a refused preview, or a request
 * for a record that was not the caller's. Leaving them out of the sentence
 * while they sit in the total would make the three figures fail to add up.
 */
export function usageSummary(days: AdminUsageDay[], share: AdminModelShare): string {
  const total = days.reduce((sum, day) => sum + day.total, 0);
  if (total === 0) {
    return `No pricing calls have been logged in the last ${days.length} days.`;
  }
  const busiest = days.reduce((most, day) => (day.total > most.total ? day : most));
  const refused =
    share.no_model > 0
      ? ` ${calls(share.no_model)} reached no model, because they were refused or asked for a record that was not the caller's.`
      : "";
  return (
    `${calls(total)} over the last ${days.length} days: ` +
    `${share.core.toLocaleString()} answered by the core model and ` +
    `${share.full.toLocaleString()} by the full model. ` +
    `The busiest day was ${dayLabel(busiest.day)}, with ${calls(busiest.total)}.` +
    refused
  );
}

/** The share each model answered, in one sentence. */
export function shareSummary(share: AdminModelShare): string {
  if (share.total === 0) {
    return "No pricing calls have been logged, so neither model has answered one.";
  }
  const core = share.core_percent ?? 0;
  const full = share.full_percent ?? 0;
  return (
    `Of ${calls(share.total)}, the core model answered ${core}% and the full ` +
    `model ${full}%. The core model prices a mentor with no track record, so ` +
    `every registration preview falls to it.`
  );
}

/** Response times over the window, in one sentence. */
export function latencySummary(days: AdminLatencyDay[]): string {
  if (days.length === 0) {
    return "No calls have been logged, so there is no response time to report.";
  }
  const medians = days.map((day) => day.median_ms);
  const slowest = days.reduce((most, day) => (day.p95_ms > most.p95_ms ? day : most));
  const typical = medians.reduce((sum, value) => sum + value, 0) / medians.length;
  return (
    `Over ${days.length} ${days.length === 1 ? "day" : "days"} with calls, the ` +
    `median response was about ${Math.round(typical).toLocaleString()} ms. The ` +
    `highest 95th percentile was ${formatMilliseconds(slowest.p95_ms)}, on ` +
    `${dayLabel(slowest.day)}.`
  );
}

/** Which paths were called, in one sentence. */
export function endpointSummary(rows: LabelledCount[]): string {
  const total = rows.reduce((sum, row) => sum + row.count, 0);
  if (total === 0) {
    return "No pricing calls have been logged, so no path has been used yet.";
  }
  const busiest = rows.reduce((most, row) => (row.count > most.count ? row : most));
  return (
    `${calls(total)} across ${rows.length} paths. The most used was ` +
    `${busiest.label}, with ${calls(busiest.count)}.`
  );
}

/** The distribution of advised prices, in one sentence. */
export function priceSummary(outputs: AdminOutputs): string {
  if (outputs.recommendations === 0 || outputs.price_buckets.length === 0) {
    return "No prices have been advised yet, so there is no distribution to show.";
  }
  const fullest = outputs.price_buckets.reduce((most, bucket) =>
    bucket.count > most.count ? bucket : most,
  );
  return (
    `${outputs.recommendations.toLocaleString()} prices advised, with a median of ` +
    `${formatMoney(outputs.median_price)} ${outputs.currency}. Most fall between ` +
    `${formatMoney(fullest.low)} and ${formatMoney(fullest.high)}.`
  );
}

/** What was advised in each field, in one sentence. */
export function fieldSummary(outputs: AdminOutputs): string {
  if (outputs.by_field.length === 0) {
    return "No prices have been advised yet, so no field has one to report.";
  }
  const busiest = outputs.by_field[0];
  return (
    `${outputs.by_field.length} ${outputs.by_field.length === 1 ? "field has" : "fields have"} ` +
    `had a price advised. The most was ${busiest.label}, with ` +
    `${busiest.count.toLocaleString()} and a median of ` +
    `${formatMoney(busiest.median_price)} ${outputs.currency}.`
  );
}

/** How wide the advised ranges are, in one sentence. */
export function rangeSummary(outputs: AdminOutputs): string {
  const widths = outputs.range_widths;
  if (widths.median === null) {
    return "No prices have been advised yet, so there is no range to measure.";
  }
  return (
    `The middle range is ${formatMoney(widths.median)} ${outputs.currency} wide, ` +
    `which is ${widths.median_percent_of_price ?? 0}% of the price it sits around.`
  );
}

/**
 * What mentors did with the advice, in one sentence.
 *
 * The acceptance rate is only stated when there is one. A platform whose
 * advice nobody has answered has no rate, and "0% accepted" would read as
 * advice that everybody rejected.
 */
export function decisionSummary(decisions: AdminDecisionCounts): string {
  if (decisions.total === 0) {
    return decisions.pending > 0
      ? `No prices have been answered yet. ${decisions.pending.toLocaleString()} are waiting on a mentor.`
      : "No prices have been advised, so none has been answered.";
  }
  const rate = decisions.acceptance_rate_percent ?? 0;
  const waiting =
    decisions.pending > 0
      ? ` ${decisions.pending.toLocaleString()} more are waiting on a mentor.`
      : "";
  return (
    `${decisions.total.toLocaleString()} prices answered: ` +
    `${decisions.accepted.toLocaleString()} accepted, ` +
    `${decisions.modified.toLocaleString()} changed and ` +
    `${decisions.rejected.toLocaleString()} declined, so ${rate}% were taken as ` +
    `advised.${waiting}`
  );
}

/** New accounts over the weeks, in one sentence. */
export function signupSummary(signups: AdminSignups): string {
  if (signups.accounts === 0) {
    return "No mentors have registered yet.";
  }
  const inWindow = signups.per_week.reduce((sum, week) => sum + week.accounts, 0);
  const busiest = signups.per_week.reduce((most, week) =>
    week.accounts > most.accounts ? week : most,
  );
  const recent =
    inWindow === 0
      ? `None of them registered in the last ${signups.weeks} weeks.`
      : `${inWindow.toLocaleString()} registered in the last ${signups.weeks} weeks, ` +
        `most in the ${weekLabel(busiest.week).toLowerCase()}.`;
  return (
    `${signups.accounts.toLocaleString()} mentor accounts, of which ` +
    `${signups.verified.toLocaleString()} have been verified and ` +
    `${signups.unverified.toLocaleString()} have not. ${recent}`
  );
}

/* --------------------------------------------------------------- segments */

export interface ShareSegment {
  id: string;
  label: string;
  count: number;
  percent: number;
}

/**
 * Counts as the segments of one horizontal bar.
 *
 * Percentages are worked out here rather than in the component so that they
 * are the figures the table shows as well. A zero count keeps its segment in
 * the list, because the component prints the legend from it and a category
 * that disappeared at zero would make the legend change shape as data
 * arrived.
 */
export function shareSegments(
  entries: Array<{ id: string; label: string; count: number }>,
): ShareSegment[] {
  const total = entries.reduce((sum, entry) => sum + entry.count, 0);
  return entries.map((entry) => ({
    ...entry,
    percent: total > 0 ? Math.round((entry.count * 1000) / total) / 10 : 0,
  }));
}

/** Whether a series has anything in it at all. */
export function hasAny(values: number[]): boolean {
  return values.some((value) => value > 0);
}
