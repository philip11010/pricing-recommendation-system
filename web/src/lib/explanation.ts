/**
 * How an account of a price is written out on the page.
 *
 * Pure functions, kept apart from the card that draws them, because these are
 * the parts that have to be right rather than the parts that have to look
 * right. A bar scaled against the wrong number, or a position phrased as
 * though it were a score, would both read perfectly well and both be wrong.
 *
 * Three rules sit behind them.
 *
 * **The sign is in the words.** Every effect is written with its own sign and
 * named with a direction, so the meaning survives a black and white printout
 * and a reader who cannot tell the two colours apart. The colour and the arrow
 * repeat the same thing; they never carry it alone.
 *
 * **The bars are comparable.** Every bar on the card is scaled against the
 * largest effect on that card, so two bars of the same length mean two effects
 * of the same size. Scaling each to its own row would turn the chart into
 * decoration.
 *
 * **A position is not a score.** "Higher than about 70 out of 100 of the
 * mentors we compared" says what a percentile means. "The 70th percentile"
 * says it to somebody who already knew, and reads as a mark out of a hundred
 * to everybody else.
 */

import type { PriceFactor } from "@/lib/api-types";

/** The shortest bar that is still visibly a bar rather than a smudge. */
export const MINIMUM_BAR_PERCENT = 4;

export const DIRECTION_WORDS: Record<string, string> = {
  raises: "raises",
  lowers: "lowers",
  "little effect": "little effect",
};

/** An effect as it is written beside its row: always signed, never bare. */
export function formatEffect(effectPct: number): string {
  if (effectPct === 0) {
    return "0%";
  }
  return `${effectPct > 0 ? "+" : "-"}${Math.abs(effectPct)}%`;
}

/** The row read as a sentence fragment, for a screen reader and for a table. */
export function describeEffect(factor: PriceFactor): string {
  if (factor.effect_pct === 0 || factor.direction === "little effect") {
    return `${factor.label}: little effect`;
  }
  return `${factor.label}: ${factor.direction} the price by ${Math.abs(
    factor.effect_pct,
  )}%`;
}

/**
 * How wide one bar is drawn, as a share of the widest on the card.
 *
 * Always against the largest effect present, so the bars can be compared with
 * each other. A row with no effect at all draws nothing, and every other row
 * draws at least a sliver, because a bar that rounds away looks like a missing
 * value rather than a small one.
 */
export function barPercent(effectPct: number, largest: number): number {
  const widest = Math.abs(largest);
  if (widest === 0 || effectPct === 0) {
    return 0;
  }
  const share = (Math.abs(effectPct) / widest) * 100;
  return Math.max(MINIMUM_BAR_PERCENT, Math.min(100, Math.round(share)));
}

/** The largest effect on a card, which every bar on it is scaled against. */
export function largestEffect(factors: PriceFactor[]): number {
  return factors.reduce(
    (widest, factor) => Math.max(widest, Math.abs(factor.effect_pct)),
    0,
  );
}

/**
 * What the effects shown come to, applied one after another to the baseline.
 *
 * The page does this arithmetic itself rather than printing the price it was
 * handed, so that the numbers a mentor can see are the numbers that produced
 * the total. If the two ever disagreed, the page would be the place it showed.
 */
export function reconciledPrice(baseline: number, factors: PriceFactor[]): number {
  return factors.reduce(
    (running, factor) => running * (1 + factor.effect_pct / 100),
    baseline,
  );
}

/** A percentile said the way somebody reads it rather than scores it. */
export function percentilePhrase(percentile: number | null): string | null {
  if (percentile === null || !Number.isFinite(percentile)) {
    return null;
  }
  const outOfHundred = Math.max(0, Math.min(100, Math.round(percentile)));
  if (outOfHundred >= 100) {
    return "Higher than every similar mentor we compared you with.";
  }
  if (outOfHundred <= 0) {
    return "Lower than every similar mentor we compared you with.";
  }
  return (
    `Higher than about ${outOfHundred} out of 100 of the similar mentors ` +
    `we compared you with.`
  );
}

/** The heading a position gets, in words rather than in a colour. */
export function positionWords(position: string): string {
  if (position === "above") {
    return "Above the middle";
  }
  if (position === "below") {
    return "Below the middle";
  }
  if (position === "within") {
    return "In the middle";
  }
  return "Not enough to say";
}
