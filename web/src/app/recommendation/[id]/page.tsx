"use client";

/**
 * One suggested price, which is the page the whole application exists for.
 *
 * The order of it is the order a mentor asks the questions in: what should I
 * charge, how sure are you, how does that compare with what I charge now,
 * what do mentors like me charge, and what do you want me to do about it.
 *
 * The headline figure is what one mentee pays, because that is the number a
 * mentor quotes. For a session of one that is the same as the session price,
 * so there is one figure rather than the same number printed twice.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { ComparableRows, ComparablesSummaryLine } from "@/components/comparables";
import { DecisionPanel } from "@/components/decision-panel";
import { PriceHistogram } from "@/components/price-histogram";
import { RequireMentor } from "@/components/require-mentor";
import {
  Badge,
  Callout,
  Card,
  ErrorNotice,
  LoadingBlock,
  SectionHeading,
} from "@/components/ui";
import { api } from "@/lib/api-client";
import type {
  ComparablesResponse,
  Decision,
  Mentor,
  Recommendation,
  Service,
  ServiceHistory,
} from "@/lib/api-types";
import {
  COMPARABLES_UNAVAILABLE_NOTE,
  LOW_CONFIDENCE_NOTE,
  NO_PRICE_SET,
  POSITION_HEADINGS,
  POSITION_MESSAGES,
  WITH_HISTORY_NOTE,
} from "@/lib/copy";
import { isNotFound, messageFor } from "@/lib/errors";
import { formatMoney, formatPercent, formatRange } from "@/lib/format";
import { isOneToOne } from "@/lib/session-label";
import { useAsync } from "@/lib/use-async";

const COMPARABLE_PREVIEW = 5;

interface PageData {
  recommendation: Recommendation;
  mentor: Mentor;
  comparables: ComparablesResponse | null;
  history: ServiceHistory | null;
}

export default function RecommendationPage() {
  const params = useParams<{ id: string }>();
  const recommendationId = Number.parseInt(params?.id ?? "", 10);

  if (!Number.isInteger(recommendationId)) {
    return <ErrorNotice message="That is not a suggestion we can look up." />;
  }

  return (
    <RequireMentor>
      {(mentorId) => (
        <RecommendationView mentorId={mentorId} recommendationId={recommendationId} />
      )}
    </RequireMentor>
  );
}

function RecommendationView({
  mentorId,
  recommendationId,
}: {
  mentorId: number;
  recommendationId: number;
}) {
  const [decision, setDecision] = useState<Decision | null>(null);

  const page = useAsync<PageData>(async (signal) => {
    const recommendation = await api.recommendation(mentorId, recommendationId, signal);
    const [mentor, comparables, history] = await Promise.all([
      api.mentor(mentorId, signal),
      // A server with no comparison table still prices perfectly well, and
      // the only thing it cannot do is say what other mentors charge. That
      // is a missing panel, not a broken page.
      api
        .comparables(
          mentorId,
          recommendation.service_id,
          { limit: COMPARABLE_PREVIEW },
          signal,
        )
        .catch(() => null),
      recommendation.status === "pending"
        ? Promise.resolve(null)
        : api.history(mentorId, recommendation.service_id, signal).catch(() => null),
    ]);
    return { recommendation, mentor, comparables, history };
  }, `recommendation-${mentorId}-${recommendationId}`);

  if (page.status === "loading") {
    return <LoadingBlock label="Working out your suggestion" />;
  }

  if (page.status === "error" || page.data === null) {
    if (isNotFound(page.error)) {
      return (
        <ErrorNotice message="We cannot find that suggestion. It may belong to another mentor, or it may never have existed." />
      );
    }
    return <ErrorNotice message={messageFor(page.error)} onRetry={page.reload} />;
  }

  const { recommendation, mentor, comparables, history } = page.data;
  const service = mentor.services.find(
    (candidate) => candidate.id === recommendation.service_id,
  );
  const alreadyDecided =
    decision ??
    history?.items.find((item) => item.recommendation.id === recommendation.id)
      ?.decision ??
    null;

  return (
    <div className="space-y-6">
      <PriceHeadline recommendation={recommendation} service={service} />

      <Card>
        <SectionHeading
          title="How sure we are"
          description={
            recommendation.low_confidence ? LOW_CONFIDENCE_NOTE : WITH_HISTORY_NOTE
          }
        />
        <div className="flex flex-wrap gap-2">
          <Badge tone={recommendation.low_confidence ? "caution" : "accent"}>
            {recommendation.low_confidence ? "First estimate" : "Based on your record"}
          </Badge>
          {service?.profile_verified ? (
            <Badge tone="quiet">Profile verified</Badge>
          ) : null}
        </div>
      </Card>

      <CurrentPriceCard recommendation={recommendation} />

      <Card>
        <SectionHeading
          title="What similar mentors charge"
          action={
            comparables && comparables.summary.count > 0 ? (
              <Link
                href={`/similar/${recommendation.service_id}`}
                className="text-sm font-semibold text-accent-800 underline"
              >
                See all similar mentors
              </Link>
            ) : undefined
          }
        />
        {comparables === null ? (
          <Callout tone="quiet">{COMPARABLES_UNAVAILABLE_NOTE}</Callout>
        ) : (
          <div className="space-y-5">
            <ComparablesSummaryLine summary={comparables.summary} />
            {comparables.summary.count > 0 ? (
              <>
                <PriceHistogram
                  histogram={comparables.histogram}
                  suggestedPrice={recommendation.recommended_price}
                  currentPrice={recommendation.current_price}
                  totalCount={comparables.summary.count}
                />
                <div>
                  <h3 className="text-sm font-semibold text-ink">
                    A few of them, at a glance
                  </h3>
                  <ComparableRows items={comparables.items} />
                </div>
              </>
            ) : null}
          </div>
        )}
      </Card>

      <Card>
        <DecisionPanel
          mentorId={mentorId}
          recommendation={recommendation}
          existingDecision={alreadyDecided}
          onDecided={setDecision}
        />
      </Card>
    </div>
  );
}

/**
 * The figure the mentor came to read.
 *
 * Per mentee in large type, because that is what a mentee is quoted and what
 * a mentor compares with another mentor. The session total sits under it with
 * the range, labelled as the whole group, so a group session never reads as
 * though one mentee pays the lot.
 */
function PriceHeadline({
  recommendation,
  service,
}: {
  recommendation: Recommendation;
  service: Service | undefined;
}) {
  const maxMentees = service?.max_mentees ?? 1;
  const single = isOneToOne(maxMentees);

  return (
    <Card className="bg-white">
      <p className="text-sm font-semibold uppercase tracking-wide text-accent-700">
        Suggested price
      </p>
      <p className="tabular mt-2 text-figure font-bold text-ink">
        {formatMoney(
          single ? recommendation.recommended_price : recommendation.price_per_mentee,
        )}
      </p>
      <p className="mt-1 text-lg font-medium text-ink-muted">
        {single ? "per session" : "per mentee"}
      </p>

      <dl className="mt-6 grid gap-3 sm:grid-cols-2">
        {single ? (
          <div className="rounded-xl border border-line bg-shell p-4">
            <dt className="text-sm text-ink-soft">Suggested range, per session</dt>
            <dd className="tabular mt-1 text-lg font-semibold">
              {formatRange(recommendation.price_low, recommendation.price_high)}
            </dd>
          </div>
        ) : (
          <>
            <div className="rounded-xl border border-line bg-shell p-4">
              <dt className="text-sm text-ink-soft">
                Per session (whole group of up to {maxMentees})
              </dt>
              <dd className="tabular mt-1 text-lg font-semibold">
                {formatMoney(recommendation.recommended_price)}
              </dd>
            </div>
            <div className="rounded-xl border border-line bg-shell p-4">
              <dt className="text-sm text-ink-soft">
                Suggested range, per session (whole group)
              </dt>
              <dd className="tabular mt-1 text-lg font-semibold">
                {formatRange(recommendation.price_low, recommendation.price_high)}
              </dd>
            </div>
            <div className="rounded-xl border border-line bg-shell p-4 sm:col-span-2">
              <dt className="text-sm text-ink-soft">Suggested range, per mentee</dt>
              <dd className="tabular mt-1 text-lg font-semibold">
                {formatRange(
                  recommendation.price_per_mentee_low,
                  recommendation.price_per_mentee_high,
                )}
              </dd>
            </div>
          </>
        )}
      </dl>

      <p className="mt-5 text-sm leading-relaxed text-ink-muted">
        This is a suggestion, not a decision. You can accept it, change it or decline it
        below. All figures are in Australian dollars.
      </p>
    </Card>
  );
}

/** The suggestion against what the mentor charges today, when they charge anything. */
function CurrentPriceCard({ recommendation }: { recommendation: Recommendation }) {
  const current = recommendation.current_price;
  const position = recommendation.position_vs_range;

  if (current === null || position === null) {
    return (
      <Card>
        <SectionHeading title="Against your current price" />
        <Callout tone="quiet">{NO_PRICE_SET}</Callout>
      </Card>
    );
  }

  const tone = position === "within" ? "accent" : "caution";

  return (
    <Card>
      <SectionHeading title="Against your current price" />
      <dl className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-line bg-shell p-4">
          <dt className="text-sm text-ink-soft">You charge now, per session</dt>
          <dd className="tabular mt-1 text-xl font-semibold">{formatMoney(current)}</dd>
        </div>
        <div className="rounded-xl border border-line bg-shell p-4">
          <dt className="text-sm text-ink-soft">The suggestion against that</dt>
          <dd className="tabular mt-1 text-xl font-semibold">
            {formatPercent(recommendation.difference_vs_current_percent, {
              signed: true,
            })}
          </dd>
        </div>
      </dl>
      <div className="mt-4">
        <Callout tone={tone} title={POSITION_HEADINGS[position]}>
          {POSITION_MESSAGES[position]}
        </Callout>
      </div>
    </Card>
  );
}
