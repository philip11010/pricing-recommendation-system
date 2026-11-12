"use client";

/**
 * Similar mentors: calm.
 *
 * What comparable mentors charge, and on what basis they were matched. The
 * sentence comes first, then the strip, then the table, and no mentor is
 * named: the API sends a price, a field and a group size for each one and
 * nothing that identifies them, which is the point rather than an oversight.
 *
 * The three filters narrow the set the API matched. They are named after the
 * two rules the match is made of, so what the buttons say and what the API
 * matched on are the same two things.
 */

import { useParams } from "next/navigation";
import { useState } from "react";

import { DotStrip } from "@/components/dot-strip";
import { RequireAuth } from "@/components/require-auth";
import {
  Banner,
  Card,
  Column,
  EmptyState,
  ErrorNotice,
  LoadingBlock,
} from "@/components/ui";
import { api } from "@/lib/api-client";
import type { ComparableItem, ComparablesResponse, Service } from "@/lib/api-types";
import { priceScale } from "@/lib/charts";
import { COMPARABLES_UNAVAILABLE_NOTE, WIDENED_NOTE } from "@/lib/copy";
import { isNotFound, isUnprepared, messageFor } from "@/lib/errors";
import { formatMoney } from "@/lib/format";
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

function SimilarMentors({ serviceId }: { serviceId: number }) {
  const [mode, setMode] = useState<Narrowing>("all");

  const service = useAsync(
    (signal) => api.service(serviceId, signal),
    `service-${serviceId}`,
  );
  const options = useAsync((signal) => api.options(signal), "similar-options");
  const comparables = useAsync(
    (signal): Promise<ComparablesResponse> =>
      api.comparables(serviceId, { limit: 200, sort: "price" }, signal),
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

  const everyone = comparables.data.items;
  const shown = narrow(everyone, mode, service.data, fieldLabel);
  const prices = shown.map((item) => item.price);
  const yours = service.data.current_price;

  const typical = median(prices);
  const middle = quartiles(prices);
  const scale = priceScale([...prices, yours]);

  const sentence =
    prices.length === 0
      ? "No mentors match that narrowing. Widen it to see the whole set we compared you with."
      : `Of ${prices.length} similar mentors, a typical one charges ${formatMoney(typical)}${
          middle
            ? `, and half of them charge between ${formatMoney(middle.low)} and ${formatMoney(middle.high)}`
            : ""
        }.${yours ? ` You charge ${formatMoney(yours)}.` : ""}`;

  return (
    <>
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
        We matched you with {comparables.data.summary.match_description}. Names are not
        shown: this page is about prices, not people.
      </p>
      {comparables.data.summary.widened ? (
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
              sentence={`Each dot is one of the ${prices.length} mentors we compared you with.`}
              tableCaption="What each similar mentor charges per session, in AUD"
            />
          </Card>

          <Card className="mt-6 overflow-x-auto p-3">
            <table className="w-full border-collapse text-[0.9375rem]">
              <caption className="px-3 py-2 text-left text-small text-ink-500">
                Similar mentors, cheapest first. No mentor is named.
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
    </>
  );
}

export default function SimilarPage() {
  const params = useParams<{ serviceId: string }>();
  const serviceId = Number.parseInt(params?.serviceId ?? "", 10);

  return (
    <RequireAuth>
      {() => (
        <>
          <Banner
            title="What similar mentors charge"
            lead="The mentors we compared your price with. Names are not shown."
          />
          <Column wide className="py-10">
            {Number.isInteger(serviceId) ? (
              <SimilarMentors serviceId={serviceId} />
            ) : (
              <ErrorNotice
                title="We could not find that service"
                message="That link does not point at a service we hold."
              />
            )}
          </Column>
        </>
      )}
    </RequireAuth>
  );
}
