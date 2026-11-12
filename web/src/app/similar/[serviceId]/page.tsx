"use client";

/**
 * Similar mentors: calm.
 *
 * What comparable mentors charge, and on what basis they were matched. The
 * sentence comes first, then the strip, then the table, and no mentor is
 * named: the API sends a price, a field and a group size for each one and
 * nothing that identifies them, which is the point rather than an oversight.
 *
 * Every price on this page is for a whole session, which is what the mentor
 * reading it charges. The per-seat figure exists and is useful, but mixing
 * the two on one axis is what made the two charts on the price screen
 * disagree, so this page uses one unit and says which one in words.
 *
 * The chart and the table are drawn from the API's distribution: the whole
 * match, evenly reduced by price rank. Asking for a page of a cheapest-first
 * sort and drawing it, which is what this used to do, showed the cheap end of
 * a market and called it the market.
 *
 * The three filters narrow the mentors listed here. They are named after the
 * two rules the match is made of, so what the buttons say and what the API
 * matched on are the same two things.
 */

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { DotStrip } from "@/components/dot-strip";
import { RequireAuth } from "@/components/require-auth";
import {
  Banner,
  Card,
  Column,
  EmptyState,
  ErrorNotice,
  LoadingBlock,
  TextLink,
} from "@/components/ui";
import { api } from "@/lib/api-client";
import type { ComparableItem, ComparablesResponse, Service } from "@/lib/api-types";
import { priceScale } from "@/lib/charts";
import { COMPARABLES_UNAVAILABLE_NOTE, WIDENED_NOTE } from "@/lib/copy";
import { isNotFound, isUnprepared, messageFor } from "@/lib/errors";
import { formatMoney } from "@/lib/format";
import {
  FROM_QUERY,
  RECOMMENDATION_QUERY,
  backFromOrigin,
  type BackLink,
} from "@/lib/origin";
import { groupWords } from "@/lib/session-label";
import { useAsync } from "@/lib/use-async";

type Narrowing = "all" | "field" | "size";

const NARROWINGS: { id: Narrowing; label: string }[] = [
  { id: "all", label: "Everyone we matched" },
  { id: "field", label: "Same field only" },
  { id: "size", label: "Same group size only" },
];

function median(values: number[]): number | null {
  if (values.length === 0) {
    return null;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? Math.round((sorted[middle - 1] + sorted[middle]) / 2)
    : sorted[middle];
}

function quartiles(values: number[]): { low: number; high: number } | null {
  if (values.length < 4) {
    return null;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const at = (share: number) =>
    sorted[
      Math.min(sorted.length - 1, Math.max(0, Math.round(share * (sorted.length - 1))))
    ];
  return { low: at(0.25), high: at(0.75) };
}

function narrow(
  items: ComparableItem[],
  mode: Narrowing,
  service: Service,
  fieldLabel: string | null,
): ComparableItem[] {
  if (mode === "field") {
    return fieldLabel ? items.filter((item) => item.field_label === fieldLabel) : items;
  }
  if (mode === "size") {
    return items.filter((item) => item.max_mentees === service.max_mentees);
  }
  return items;
}

function SimilarMentors({ serviceId, back }: { serviceId: number; back: BackLink }) {
  const [mode, setMode] = useState<Narrowing>("all");

  const service = useAsync(
    (signal) => api.service(serviceId, signal),
    `service-${serviceId}`,
  );
  const options = useAsync((signal) => api.options(signal), "similar-options");
  // The smallest page of items the endpoint allows. Everything this screen
  // draws comes out of the distribution, which is the whole match rather
  // than a page of it, so a larger page would be payload nobody reads.
  const comparables = useAsync(
    (signal): Promise<ComparablesResponse> =>
      api.comparables(serviceId, { limit: 1, sort: "price" }, signal),
    `similar-comparables-${serviceId}`,
  );

  if (service.status === "loading" || comparables.status === "loading") {
    return <LoadingBlock label="Loading similar mentors" />;
  }

  if (service.status === "error" || !service.data) {
    return (
      <ErrorNotice
        title={
          isNotFound(service.error)
            ? "We could not find that service"
            : "We could not load this"
        }
        message={
          isNotFound(service.error)
            ? "That service is not one of yours, or it no longer exists."
            : messageFor(service.error)
        }
        onRetry={isNotFound(service.error) ? undefined : service.reload}
      />
    );
  }

  if (comparables.status === "error" || !comparables.data) {
    return (
      <ErrorNotice
        message={
          isUnprepared(comparables.error)
            ? COMPARABLES_UNAVAILABLE_NOTE
            : messageFor(comparables.error)
        }
        onRetry={comparables.reload}
      />
    );
  }

  const fieldLabel =
    options.data?.fields.find((option) => option.id === service.data?.field)?.label ??
    null;

  const summary = comparables.data.summary;
  const drawn = comparables.data.distribution;
  const everyone = drawn.items;
  const shown = narrow(everyone, mode, service.data, fieldLabel);
  const prices = shown.map((item) => item.price);
  const yours = service.data.current_price;
  const sessionsOf = groupWords(service.data.max_mentees);

  // The whole match when nothing is narrowed, so the sentence reports the
  // API's own quantiles rather than quantiles of a sample of a sample.
  const whole = mode === "all";
  const typical = whole ? summary.median_price : median(prices);
  const middle = whole
    ? summary.p25_price !== null && summary.p75_price !== null
      ? { low: summary.p25_price, high: summary.p75_price }
      : null
    : quartiles(prices);

  const scale = priceScale([
    ...prices,
    middle?.low ?? null,
    middle?.high ?? null,
    yours,
  ]);

  const counted = whole ? drawn.total : prices.length;
  const sentence =
    prices.length === 0
      ? "No mentors match that narrowing. Widen it to see the whole set we compared you with."
      : `Of ${counted} similar mentors, a typical one charges ${formatMoney(typical)} for a session${
          middle
            ? `, and half of them charge between ${formatMoney(middle.low)} and ${formatMoney(middle.high)}`
            : ""
        }.${yours ? ` You charge ${formatMoney(yours)} for ${sessionsOf}.` : ""}`;

  const dotSentence = drawn.sampled
    ? `Each dot is one of ${prices.length} mentors spread evenly across the ${drawn.total} we compared you with. Every price is for a whole session.`
    : `Each dot is one of the ${prices.length} mentors we compared you with. Every price is for a whole session.`;

  return (
    <>
      <p className="mb-6">
        <TextLink href={back.href}>{back.label}</TextLink>
      </p>

      <div
        className="flex flex-wrap gap-2"
        role="group"
        aria-label="Narrow the mentors shown"
      >
        {NARROWINGS.map((option) => (
          <button
            key={option.id}
            type="button"
            aria-pressed={mode === option.id}
            onClick={() => setMode(option.id)}
            className={`min-h-[44px] cursor-pointer rounded-pill border px-4 py-2 text-[0.9375rem] font-semibold transition-colors duration-[180ms] ease-entrance mid:min-h-[40px] ${
              mode === option.id
                ? "border-accent-700 bg-accent-100 text-accent-800"
                : "border-line bg-surface text-ink-700 hover:bg-surface-sunk"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      <p className="mt-5 max-w-prose font-semibold text-ink-900">{sentence}</p>
      <p className="mt-2 max-w-prose text-small text-ink-500">
        We matched you with {summary.match_description}. Every price on this page is
        what the mentor charges for a whole session, not per person. Names are not
        shown: this page is about prices, not people.
      </p>
      {summary.widened ? (
        <p className="mt-2 max-w-prose text-small text-ink-500">{WIDENED_NOTE}</p>
      ) : null}

      {prices.length === 0 ? (
        <div className="mt-6">
          <EmptyState title="Nothing to show with that narrowing">
            Choose Everyone we matched to see the full set again.
          </EmptyState>
        </div>
      ) : (
        <>
          <Card className="mt-6">
            <DotStrip
              prices={prices}
              scale={scale}
              yours={yours}
              yoursLabel="You"
              sentence={dotSentence}
              tableCaption="What each similar mentor charges for a whole session, in AUD"
            />
          </Card>

          <Card className="mt-6 overflow-x-auto p-3">
            <table className="w-full border-collapse text-[0.9375rem]">
              <caption className="px-3 py-2 text-left text-small text-ink-500">
                {drawn.sampled
                  ? `${prices.length} of the ${drawn.total} similar mentors we matched, spread evenly across the price range, cheapest first. No mentor is named.`
                  : "Similar mentors, cheapest first. No mentor is named."}
              </caption>
              <thead>
                <tr>
                  {[
                    "Mentor",
                    "Field",
                    "Group size",
                    "Reviews",
                    "Price per session",
                  ].map((column) => (
                    <th
                      key={column}
                      scope="col"
                      className="border-b border-line px-3 py-2.5 text-left text-overline uppercase text-ink-500"
                    >
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...shown]
                  .sort((a, b) => a.price - b.price)
                  .map((item, index) => (
                    <tr key={`${item.price}-${index}`} className="even:bg-surface-sunk">
                      <td className="border-b border-line px-3 py-3">
                        Mentor {index + 1}
                      </td>
                      <td className="border-b border-line px-3 py-3">
                        {item.field_label}
                      </td>
                      <td className="tabular border-b border-line px-3 py-3">
                        {item.max_mentees}
                      </td>
                      <td className="tabular border-b border-line px-3 py-3">
                        {item.reviews_total}
                      </td>
                      <td className="tabular border-b border-line px-3 py-3">
                        {formatMoney(item.price)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </Card>
        </>
      )}

      <p className="mt-8">
        <TextLink href={back.href}>{back.label}</TextLink>
      </p>
    </>
  );
}

function SimilarScreen() {
  const params = useParams<{ serviceId: string }>();
  const search = useSearchParams();
  const serviceId = Number.parseInt(params?.serviceId ?? "", 10);
  const back = backFromOrigin(
    search?.get(FROM_QUERY),
    search?.get(RECOMMENDATION_QUERY),
  );

  return (
    <>
      <Banner
        title="What similar mentors charge"
        lead="The mentors we compared your price with. Names are not shown."
      />
      <Column wide className="py-10">
        {Number.isInteger(serviceId) ? (
          <SimilarMentors serviceId={serviceId} back={back} />
        ) : (
          <>
            <ErrorNotice
              title="We could not find that service"
              message="That link does not point at a service we hold."
            />
            <p className="mt-6">
              <TextLink href={back.href}>{back.label}</TextLink>
            </p>
          </>
        )}
      </Column>
    </>
  );
}

export default function SimilarPage() {
  return (
    <RequireAuth>
      {() => (
        <Suspense fallback={null}>
          <SimilarScreen />
        </Suspense>
      )}
    </RequireAuth>
  );
}
