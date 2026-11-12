"use client";

/**
 * Why we suggest this price: the account, under the price it accounts for.
 *
 * A calm card on white, under the suggestion and before the two charts, which
 * is the order a mentor asks the questions in: what is the number, why is it
 * that number, and what are other people charging.
 *
 * **It never takes the price screen down with it.** The account is a second
 * request, and a mentor whose account fails to load still has their price and
 * their three answers. So a failure here is a quiet notice with a retry inside
 * this card, not an error state for the page.
 *
 * **Nothing is said in colour alone.** Every row carries an arrow, the word
 * "raises" or "lowers", and a signed percentage. Remove the colour and the row
 * still reads; remove the arrow and it still reads. The bar beside it is
 * scaled against the largest effect on the card, so two bars of a length are
 * two effects of a size, and the sign is never left to the bar.
 *
 * **The arithmetic is open.** The card prints what the effects come to when
 * they are applied one after another, rather than reprinting the price it was
 * given, and the disclosure under it is a real table of every line. A mentor
 * who wants to check the sum can.
 *
 * **The two fixed lines are not small print.** What these patterns are, and
 * the fact that experience and credentials do not change the suggestion, are
 * shown at full size and are never collapsed behind anything.
 */

import { DataDisclosure } from "@/components/data-disclosure";
import { Card, LoadingBlock, Note, WarningIcon } from "@/components/ui";
import { api } from "@/lib/api-client";
import type { Explanation, PriceFactor } from "@/lib/api-types";
import { messageFor } from "@/lib/errors";
import {
  barPercent,
  describeEffect,
  formatEffect,
  largestEffect,
  percentilePhrase,
  positionWords,
  reconciledPrice,
} from "@/lib/explanation";
import { formatMoney } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

/** The anchor the price card links to, and the heading focus lands on. */
export const EXPLANATION_ANCHOR = "why-this-price";

const HEADING = "Why we suggest this price";
const COMPARISON_HEADING = "How this compares with similar mentors";

// Named lists, so the rows that moved the price and the ways this mentor
// differs from the others can be told apart by someone reading with a screen
// reader, and by a test, without counting list items on the page.
const FACTORS_LABEL = "What moved your price";
const DIFFERENCES_LABEL = "How your service differs from theirs";

/**
 * Reserved while the account loads, so the charts below do not jump.
 *
 * Tall enough for a baseline line, five rows and the fixed lines, which is
 * what almost every account comes to.
 */
const RESERVED = "min-h-[520px]";

function Arrow({ direction }: { direction: string }) {
  if (direction === "little effect") {
    return (
      <svg viewBox="0 0 16 16" aria-hidden="true" className="h-4 w-4 flex-none">
        <path d="M3 8h10" stroke="currentColor" strokeWidth="2" fill="none" />
      </svg>
    );
  }
  const up = direction === "raises";
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="h-4 w-4 flex-none">
      <path
        d={up ? "M8 13V3M4 7l4-4 4 4" : "M8 3v10M4 9l4 4 4-4"}
        stroke="currentColor"
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function FactorRow({ factor, largest }: { factor: PriceFactor; largest: number }) {
  const width = barPercent(factor.effect_pct, largest);
  const lowers = factor.direction === "lowers";
  return (
    <li className="border-b border-line py-3 last:border-b-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="min-w-0 font-semibold">{factor.label}</p>
        <p className="flex items-center gap-1.5 font-semibold text-ink-700">
          <Arrow direction={factor.direction} />
          <span>{factor.direction}</span>
          <span className="tabular">{formatEffect(factor.effect_pct)}</span>
        </p>
      </div>

      {/* The bar repeats the figure beside it and never replaces it. It is
          hidden from assistive technology because the row already says the
          same thing in words. */}
      <div
        aria-hidden="true"
        className="mt-2 h-1.5 w-full overflow-hidden rounded-pill bg-chart-track"
      >
        <div
          className={`h-full rounded-pill ${lowers ? "bg-ink-500" : "bg-accent-700"}`}
          style={{ width: `${width}%` }}
        />
      </div>

      <p className="mt-2 max-w-prose text-ink-700">{factor.sentence}</p>
    </li>
  );
}

function Comparison({ explanation }: { explanation: Explanation }) {
  const comparison = explanation.comparison;
  const phrase = percentilePhrase(comparison.percentile);
  return (
    <section className="mt-8" aria-labelledby={`${EXPLANATION_ANCHOR}-comparison`}>
      <h3 id={`${EXPLANATION_ANCHOR}-comparison`} className="text-h3 font-semibold">
        {COMPARISON_HEADING}
      </h3>
      <p className="mt-2 max-w-prose font-semibold">{comparison.sentence}</p>
      <p className="mt-1 text-ink-700">
        <span className="font-semibold">{positionWords(comparison.position)}.</span>{" "}
        {phrase ? phrase : null}
      </p>
      <p className="mt-1 text-small text-ink-500">
        Compared with {comparison.compared_with} of {comparison.matched_total}{" "}
        {comparison.match_description}.
      </p>

      {comparison.differences.length > 0 ? (
        <ul className="mt-3 grid gap-2" aria-label={DIFFERENCES_LABEL}>
          {comparison.differences.map((difference) => (
            <li key={difference.key} className="max-w-prose text-ink-700">
              <span className="font-semibold">{difference.label}. </span>
              {difference.sentence}
            </li>
          ))}
        </ul>
      ) : null}

      {comparison.explains_gap ? (
        <Note tone="caution" className="mt-4 flex items-start gap-2">
          <WarningIcon className="mt-0.5 h-4 w-4 flex-none" />
          <span>{comparison.explains_gap}</span>
        </Note>
      ) : null}
    </section>
  );
}

function Account({ explanation }: { explanation: Explanation }) {
  const rows = explanation.other_small_effects
    ? [...explanation.factors, explanation.other_small_effects]
    : explanation.factors;
  const largest = largestEffect(explanation.factors);
  const reached = reconciledPrice(explanation.baseline_price, rows);

  return (
    <>
      <p className="max-w-prose text-ink-700">{explanation.baseline_sentence}</p>
      {/* The line that places the suggestion against that typical price,
          directly above the rows that move it, so a reader knows which
          direction the list below is working in before they start it. */}
      <p className="mt-2 max-w-prose font-semibold text-ink-900 tabular">
        {explanation.summary_sentence}
      </p>

      <ul className="mt-4" aria-label={FACTORS_LABEL}>
        {explanation.factors.map((factor) => (
          <FactorRow key={factor.key} factor={factor} largest={largest} />
        ))}
        {explanation.other_small_effects ? (
          <FactorRow factor={explanation.other_small_effects} largest={largest} />
        ) : null}
      </ul>

      <p className="mt-3 max-w-prose text-small text-ink-500">
        {explanation.combination_note}
      </p>

      <p className="mt-4 max-w-prose font-semibold">
        That comes to{" "}
        <span className="tabular">{formatMoney(Math.round(reached))}</span> for a
        session.
      </p>

      <DataDisclosure
        caption="From a typical mentor's price to yours, in AUD"
        summaryLabel="View the numbers"
        columns={["Line", "Effect", "Running total"]}
        rows={[
          [
            "A typical mentor's price",
            "",
            <span key="start" className="tabular">
              {formatMoney(explanation.baseline_price)}
            </span>,
          ],
          ...rows.flatMap((factor, index) => {
            const running = reconciledPrice(
              explanation.baseline_price,
              rows.slice(0, index + 1),
            );
            const line = [
              factor.label,
              <span key={`${factor.key}-effect`} className="tabular">
                {describeEffect(factor)}
              </span>,
              <span key={`${factor.key}-total`} className="tabular">
                {formatMoney(Math.round(running))}
              </span>,
            ];
            // A row that stands for more than one measured thing lists those
            // things under itself. The sentence above groups them; this is
            // where the numbers behind the grouping stay readable.
            return [
              line,
              ...factor.components.map((part) => [
                <span key={`${part.key}-label`} className="pl-4 text-ink-500">
                  {part.label}
                </span>,
                <span key={`${part.key}-effect`} className="tabular text-ink-500">
                  {formatEffect(part.effect_pct)}
                </span>,
                "",
              ]),
            ];
          }),
          [
            "Our suggestion",
            "",
            <span key="final" className="tabular font-semibold">
              {formatMoney(explanation.suggested_price)}
            </span>,
          ],
        ]}
      />

      <Comparison explanation={explanation} />

      <p className="mt-6 max-w-prose text-ink-700">{explanation.limitation}</p>
      <p className="mt-2 max-w-prose text-ink-700">{explanation.profile_note}</p>
    </>
  );
}

export function PriceExplanation({ recommendationId }: { recommendationId: number }) {
  const { status, data, error, reload } = useAsync(
    (signal) => api.explanation(recommendationId, signal),
    `explanation-${recommendationId}`,
  );

  return (
    <Card
      id={`${EXPLANATION_ANCHOR}-card`}
      className={status === "ready" ? "" : RESERVED}
      role="region"
      aria-labelledby={EXPLANATION_ANCHOR}
    >
      <h2
        id={EXPLANATION_ANCHOR}
        // Focusable so that the link beside the price can move focus here
        // rather than only scrolling the page under somebody.
        tabIndex={-1}
        className="text-h3 font-semibold outline-offset-4"
      >
        {HEADING}
      </h2>

      <div className="mt-3">
        {status === "loading" ? <LoadingBlock label="Working out why" /> : null}

        {status === "error" ? (
          <div>
            <p className="max-w-prose text-ink-700">
              We could not put together the reasons behind this price just now. Your
              price and your three answers above are unaffected.
            </p>
            <p className="mt-1 text-small text-ink-500">{messageFor(error)}</p>
            <button
              type="button"
              onClick={reload}
              className="mt-3 min-h-[44px] cursor-pointer font-semibold text-link-700 underline underline-offset-[3px] hover:text-link-800 mid:min-h-[40px]"
            >
              Try again
            </button>
          </div>
        ) : null}

        {status === "ready" && data ? <Account explanation={data} /> : null}
      </div>
    </Card>
  );
}
