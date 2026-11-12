"use client";

/**
 * The price screen: a bold hero, then calm sections.
 *
 * This is the payload. The hero gradient holds the headline, one line on what
 * the price was based on, and the price card: the figure on white inside the
 * card, the range, the advisory sentence, the low confidence note when it
 * applies, and the three answers.
 *
 * Below the gradient, on white, the two comparisons. Each opens with a plain
 * language sentence and then the visual, never the other way round.
 */

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { DecisionPanel } from "@/components/decision-panel";
import { DotStrip } from "@/components/dot-strip";
import { PriceLadder } from "@/components/price-ladder";
import { RequireAuth } from "@/components/require-auth";
import {
  Card,
  Chip,
  Column,
  ErrorNotice,
  LoadingBlock,
  Note,
  Overline,
  RaisedCard,
  TextLink,
} from "@/components/ui";
import { api } from "@/lib/api-client";
import type { Mentor, Recommendation } from "@/lib/api-types";
import { priceScale } from "@/lib/charts";
import {
  ADVISORY_LINE,
  COMPARABLES_UNAVAILABLE_NOTE,
  LOW_CONFIDENCE_NOTE,
  LOW_CONFIDENCE_TITLE,
  NO_COMPARABLES_NOTE,
  WIDENED_NOTE,
  WITH_HISTORY_NOTE,
  decisionWord,
} from "@/lib/copy";
import { isNotFound, isUnprepared, messageFor } from "@/lib/errors";
import { formatMoney } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

function firstNameOf(name: string): string {
  return (name ?? "").trim().split(/\s+/)[0] ?? "";
}

function sessionWords(recommendation: Recommendation): string {
  return recommendation.max_mentees <= 1
    ? "AUD, one to one"
    : `AUD, group of ${recommendation.max_mentees}`;
}

function Comparisons({ recommendation }: { recommendation: Recommendation }) {
  const { status, data, error } = useAsync(
    (signal) =>
      api.comparables(recommendation.service_id, { limit: 60, sort: "price" }, signal),
    `comparables-${recommendation.service_id}`,
  );

  if (status === "loading") {
    return <LoadingBlock label="Loading what similar mentors charge" />;
  }

  if (status === "error") {
    return (
      <Card>
        <h2 className="text-h3 font-semibold">Mentors like you</h2>
        <p className="mt-2 text-ink-700">
          {isUnprepared(error) ? COMPARABLES_UNAVAILABLE_NOTE : messageFor(error)}
        </p>
      </Card>
    );
  }

  const summary = data?.summary;
  const items = data?.items ?? [];

  if (!summary || summary.count === 0) {
    return (
      <Card>
        <h2 className="text-h3 font-semibold">Mentors like you</h2>
        <p className="mt-2 text-ink-700">{NO_COMPARABLES_NOTE}</p>
      </Card>
    );
  }

  const prices = items.map((item) => item.price);
  const scale = priceScale([
    ...prices,
    summary.p25_price,
    summary.p75_price,
    recommendation.recommended_price,
  ]);

  const band =
    summary.p25_price !== null && summary.p75_price !== null
      ? { low: summary.p25_price, high: summary.p75_price }
      : null;

  const inside =
    band !== null &&
    recommendation.recommended_price >= band.low &&
    recommendation.recommended_price <= band.high;

  const ladderSentence = band
    ? inside
      ? `Your suggested price is in the middle of what similar mentors charge. Most of them charge between ${formatMoney(band.low)} and ${formatMoney(band.high)}.`
      : recommendation.recommended_price < band.low
        ? `Your suggested price is below the middle of what similar mentors charge, which is ${formatMoney(band.low)} to ${formatMoney(band.high)}.`
        : `Your suggested price is above the middle of what similar mentors charge, which is ${formatMoney(band.low)} to ${formatMoney(band.high)}.`
    : `We have ${summary.count} similar mentors to compare you with, but not enough of them to say where the middle sits.`;

  return (
    <div className="grid gap-6 wide:grid-cols-2">
      <Card>
        <h2 className="text-h3 font-semibold">Where your price sits</h2>
        <div className="mt-2">
          <PriceLadder
            scale={scale}
            bandLow={band?.low ?? null}
            bandHigh={band?.high ?? null}
            suggested={recommendation.recommended_price}
            sentence={ladderSentence}
            tableCaption="Where the suggested price sits, in AUD"
          />
        </div>
        {summary.widened ? (
          <Note tone="caution" className="mt-4">
            {WIDENED_NOTE}
          </Note>
        ) : null}
      </Card>

      <Card>
        <h2 className="text-h3 font-semibold">Mentors like you</h2>
        <div className="mt-2">
          {prices.length > 0 ? (
            <DotStrip
              prices={prices}
              scale={scale}
              yours={recommendation.recommended_price}
              yoursLabel="You"
              sentence={`${summary.match_description}. Each dot is one of the ${prices.length} we compared you with.`}
              tableCaption="What each similar mentor charges per session, in AUD"
            />
          ) : (
            <p className="mt-2 text-ink-700">{NO_COMPARABLES_NOTE}</p>
          )}
        </div>
        <p className="mt-4">
          <TextLink href={`/similar/${recommendation.service_id}`}>
            See all similar mentors
          </TextLink>
        </p>
      </Card>
    </div>
  );
}

function PriceScreen({ mentor }: { mentor: Mentor }) {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const recommendationId = Number.parseInt(params?.id ?? "", 10);
  const [answered, setAnswered] = useState(false);

  const { status, data, error, reload } = useAsync(
    (signal) => api.recommendation(recommendationId, signal),
    `recommendation-${recommendationId}`,
  );

  if (!Number.isInteger(recommendationId)) {
    return (
      <Column className="py-10">
        <ErrorNotice
          title="We could not find that price"
          message="That link does not point at a price we hold."
        />
      </Column>
    );
  }

  if (status === "loading") {
    return (
      <Column className="py-10">
        <LoadingBlock label="Loading your suggested price" />
      </Column>
    );
  }

  if (status === "error" || !data) {
    return (
      <Column className="py-10">
        <ErrorNotice
          title={
            isNotFound(error)
              ? "We could not find that price"
              : "We could not load this"
          }
          message={
            isNotFound(error)
              ? "That price is not one of yours, or it no longer exists."
              : messageFor(error)
          }
          onRetry={isNotFound(error) ? undefined : reload}
        />
      </Column>
    );
  }

  const recommendation = data;
  const decided = recommendation.decision ?? null;

  return (
    <>
      <section className="on-gradient bg-hero text-surface">
        <div className="mx-auto grid w-full max-w-site items-center gap-10 px-4 pb-16 pt-10 sm:px-6 wide:grid-cols-2">
          <div>
            <Overline className="text-on-gradient-fine">Your suggestion</Overline>
            <h1 className="mt-2 max-w-[14ch] text-balance font-display text-display">
              Here is what we suggest,{" "}
              <em className="accent-word">{firstNameOf(mentor.full_name)}</em>.
            </h1>
            <p className="mt-4 max-w-lead text-body-lg text-on-gradient-lead">
              Based on your field, group size and skills, compared with similar mentors.
            </p>
          </div>

          <RaisedCard className="mx-auto w-full max-w-[460px]">
            <Overline>Suggested session price</Overline>
            <p className="tabular mt-2.5 font-display text-figure">
              {formatMoney(recommendation.recommended_price)}
              <span className="ml-2 text-base font-semibold tracking-normal text-ink-500">
                {sessionWords(recommendation)}
              </span>
            </p>
            <p className="mt-1.5 font-medium text-ink-700">
              Similar mentors charge {formatMoney(recommendation.price_low)} to{" "}
              {formatMoney(recommendation.price_high)}
            </p>
            <p className="mt-4 text-ink-700">{ADVISORY_LINE}</p>

            {recommendation.low_confidence ? (
              <Note className="mt-4" title={LOW_CONFIDENCE_TITLE}>
                {LOW_CONFIDENCE_NOTE}
              </Note>
            ) : (
              <Note tone="info" className="mt-4">
                {WITH_HISTORY_NOTE}
              </Note>
            )}

            {decided ? (
              <div className="mt-6">
                <Chip tone={decided.action === "rejected" ? "declined" : "accepted"}>
                  {decisionWord(decided.action)}
                </Chip>
                <p className="mt-3 text-ink-700">
                  You have already answered this price
                  {decided.final_price !== null
                    ? `, and your price is now ${formatMoney(decided.final_price)}.`
                    : "."}{" "}
                  Ask for a fresh price from your dashboard if you want to decide again.
                </p>
                <p className="mt-3">
                  <TextLink href="/dashboard">Go to your dashboard</TextLink>
                </p>
              </div>
            ) : answered ? (
              <p role="status" className="mt-6 text-ink-700">
                Saved. Taking you to your dashboard.
              </p>
            ) : (
              <DecisionPanel
                recommendation={recommendation}
                onDecided={() => {
                  setAnswered(true);
                  router.push("/dashboard");
                }}
              />
            )}
          </RaisedCard>
        </div>
      </section>

      <Column wide className="py-12">
        <Comparisons recommendation={recommendation} />
      </Column>
    </>
  );
}

export default function RecommendationPage() {
  return <RequireAuth>{(mentor) => <PriceScreen mentor={mentor} />}</RequireAuth>;
}
