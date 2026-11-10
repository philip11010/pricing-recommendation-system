/**
 * Money, and the things that can go wrong with it.
 *
 * Three of these matter more than the rest. A price with cents on it would
 * invite the question of what the cents mean, and the answer is nothing: every
 * figure in this system is a whole number of AUD. A missing price has to read
 * as missing rather than as free. And a difference has to keep its sign,
 * because "up 12 percent" and "down 12 percent" are opposite answers.
 */

import { describe, expect, it } from "vitest";

import {
  formatAmount,
  formatMentees,
  formatMoney,
  formatPercent,
  formatRange,
  formatRating,
  formatSessions,
} from "@/lib/format";

describe("formatMoney", () => {
  it("writes whole Australian dollars with no decimal places", () => {
    expect(formatMoney(342)).toBe("$342");
    expect(formatMoney(1)).toBe("$1");
  });

  it("groups thousands", () => {
    expect(formatMoney(1864)).toBe("$1,864");
    expect(formatMoney(5000)).toBe("$5,000");
  });

  it("rounds rather than showing cents", () => {
    expect(formatMoney(1913.07)).toBe("$1,913");
    expect(formatMoney(59.51)).toBe("$60");
  });

  it("says a missing price is missing, never zero", () => {
    expect(formatMoney(null)).toBe("Not set");
    expect(formatMoney(undefined)).toBe("Not set");
    expect(formatMoney(Number.NaN)).toBe("Not set");
  });

  it("writes a genuine zero as a zero", () => {
    expect(formatMoney(0)).toBe("$0");
  });
});

describe("formatAmount", () => {
  it("drops the currency symbol for an axis that names the unit once", () => {
    expect(formatAmount(1864)).toBe("1,864");
  });

  it("is empty rather than wrong when there is no figure", () => {
    expect(formatAmount(null)).toBe("");
  });
});

describe("formatRange", () => {
  it("writes both ends in words a mentor would read aloud", () => {
    expect(formatRange(235, 513)).toBe("$235 to $513");
  });

  it("needs both ends", () => {
    expect(formatRange(235, null)).toBe("Not set");
    expect(formatRange(null, 513)).toBe("Not set");
  });
});

describe("formatPercent", () => {
  it("keeps the sign where the direction is the point", () => {
    expect(formatPercent(12.4, { signed: true })).toBe("+12.4%");
    expect(formatPercent(-20.8, { signed: true })).toBe("-20.8%");
  });

  it("drops the sign for a plain share", () => {
    expect(formatPercent(62.5)).toBe("62.5%");
  });

  it("rounds to the decimals asked for", () => {
    expect(formatPercent(42.49, { decimals: 0 })).toBe("42%");
  });

  it("writes an exact zero without a sign", () => {
    expect(formatPercent(0, { signed: true })).toBe("0%");
  });

  it("says so when there is no figure", () => {
    expect(formatPercent(null)).toBe("Not available");
  });
});

describe("formatRating", () => {
  it("writes a rating out of five", () => {
    expect(formatRating(4.89)).toBe("4.9 out of 5");
  });

  it("distinguishes unrated from zero", () => {
    expect(formatRating(null)).toBe("Not rated");
  });
});

describe("counts", () => {
  it("agrees with itself about singulars", () => {
    expect(formatMentees(1)).toBe("1 mentee");
    expect(formatMentees(8)).toBe("8 mentees");
    expect(formatSessions(1)).toBe("1 session");
    expect(formatSessions(3)).toBe("3 sessions");
  });
});
