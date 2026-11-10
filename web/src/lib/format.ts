/**
 * How figures are written on the page.
 *
 * Every price in this system is a whole number of AUD and there is no
 * currency conversion anywhere, so there is one formatter and it has no
 * decimal places. A price shown as "$342.00" invites the question of what the
 * cents mean, and the answer is nothing.
 */

export const CURRENCY = "AUD";
export const LOCALE = "en-AU";

const money = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: CURRENCY,
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

const plain = new Intl.NumberFormat(LOCALE, {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

/** A price, or a dash when there is no price rather than a zero. */
export function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "Not set";
  }
  return money.format(Math.round(value));
}

/** A price with no currency symbol, for an axis where the unit is stated once. */
export function formatAmount(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "";
  }
  return plain.format(Math.round(value));
}

/** The two ends of a range, written as a mentor would read them aloud. */
export function formatRange(
  low: number | null | undefined,
  high: number | null | undefined,
): string {
  if (low === null || low === undefined || high === null || high === undefined) {
    return "Not set";
  }
  return `${formatMoney(low)} to ${formatMoney(high)}`;
}

/**
 * A percentage, with its sign kept when the direction is the point.
 *
 * `signed` is for a difference, where "up 12%" and "down 12%" are opposite
 * answers. Unsigned is for a share, where a sign would be noise.
 */
export function formatPercent(
  value: number | null | undefined,
  options: { signed?: boolean; decimals?: number } = {},
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "Not available";
  }
  const { signed = false, decimals = 1 } = options;
  const rounded = Number(value.toFixed(decimals));
  const body = `${Math.abs(rounded).toLocaleString(LOCALE, {
    minimumFractionDigits: 0,
    maximumFractionDigits: decimals,
  })}%`;
  if (!signed) {
    return body;
  }
  if (rounded > 0) {
    return `+${body}`;
  }
  if (rounded < 0) {
    return `-${body}`;
  }
  return body;
}

/** A rating out of five, to one decimal place. */
export function formatRating(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "Not rated";
  }
  return `${value.toFixed(1)} out of 5`;
}

const dateFormatter = new Intl.DateTimeFormat(LOCALE, {
  day: "numeric",
  month: "short",
  year: "numeric",
});

const dateTimeFormatter = new Intl.DateTimeFormat(LOCALE, {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

export function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  return dateFormatter.format(parsed);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  return dateTimeFormatter.format(parsed);
}

/** "1 mentee", "4 mentees". */
export function formatMentees(count: number): string {
  return `${count} ${count === 1 ? "mentee" : "mentees"}`;
}

/** "1 session", "3 sessions". */
export function formatSessions(count: number): string {
  return `${count} ${count === 1 ? "session" : "sessions"}`;
}
