"use client";

/**
 * Every mentor this service is compared against.
 *
 * The summary at the top describes the whole match and never changes as the
 * list is paged or sorted, which is deliberate: what a mentor is told about
 * the market should not depend on which twenty rows they happen to be
 * looking at.
 *
 * The rows carry no names. This is a distribution, not a directory.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { ComparableRows, ComparablesSummaryLine } from "@/components/comparables";
import { RequireMentor } from "@/components/require-mentor";
import {
  Button,
  Card,
  ErrorNotice,
  LoadingBlock,
  PageHeading,
  SectionHeading,
} from "@/components/ui";
import { api } from "@/lib/api-client";
import type {
  ComparablesOrder,
  ComparablesResponse,
  ComparablesSort,
} from "@/lib/api-types";
import { isNotFound, isUnprepared, messageFor } from "@/lib/errors";
import { useAsync } from "@/lib/use-async";

const PAGE_SIZE = 20;

const SORTS: { id: ComparablesSort; label: string }[] = [
  { id: "price", label: "Price" },
  { id: "rating", label: "Rating" },
];

const ORDERS: { id: ComparablesOrder; label: string }[] = [
  { id: "asc", label: "Lowest first" },
  { id: "desc", label: "Highest first" },
];

export default function SimilarMentorsPage() {
  const params = useParams<{ serviceId: string }>();
  const serviceId = Number.parseInt(params?.serviceId ?? "", 10);

  if (!Number.isInteger(serviceId)) {
    return <ErrorNotice message="That is not a service we can look up." />;
  }

  return (
    <RequireMentor>
      {(mentorId) => <SimilarList mentorId={mentorId} serviceId={serviceId} />}
    </RequireMentor>
  );
}

function SimilarList({ mentorId, serviceId }: { mentorId: number; serviceId: number }) {
  const [sort, setSort] = useState<ComparablesSort>("price");
  const [order, setOrder] = useState<ComparablesOrder>("asc");
  const [offset, setOffset] = useState(0);

  const page = useAsync<ComparablesResponse>(
    (signal) =>
      api.comparables(
        mentorId,
        serviceId,
        { sort, order, limit: PAGE_SIZE, offset },
        signal,
      ),
    `comparables-${mentorId}-${serviceId}-${sort}-${order}-${offset}`,
  );

  function change(next: { sort?: ComparablesSort; order?: ComparablesOrder }) {
    if (next.sort) {
      setSort(next.sort);
    }
    if (next.order) {
      setOrder(next.order);
    }
    // Back to the first page: page four of a list sorted the other way is
    // not the same twenty mentors, and staying on it looks like a glitch.
    setOffset(0);
  }

  const summary = page.data?.summary;
  const total = summary?.count ?? 0;
  const shownFrom = total === 0 ? 0 : offset + 1;
  const shownTo = Math.min(offset + PAGE_SIZE, total);

  return (
    <div className="space-y-6">
      <PageHeading
        title="Similar mentors"
        lead="What mentors like you charge for one session, in Australian dollars. No names: this is the spread of the market, not a list of accounts."
      />

      <p>
        <Link
          href="/dashboard"
          className="text-sm font-semibold text-accent-800 underline"
        >
          Back to my page
        </Link>
      </p>

      {page.status === "loading" ? (
        <LoadingBlock label="Loading similar mentors" />
      ) : null}

      {page.status === "error" ? (
        isNotFound(page.error) ? (
          <ErrorNotice message="We cannot find that service. It may belong to another mentor." />
        ) : isUnprepared(page.error) ? (
          <ErrorNotice message={messageFor(page.error)} />
        ) : (
          <ErrorNotice message={messageFor(page.error)} onRetry={page.reload} />
        )
      ) : null}

      {page.status === "ready" && page.data ? (
        <>
          <Card>
            <SectionHeading title="The group you are compared with" />
            <ComparablesSummaryLine summary={page.data.summary} />
          </Card>

          <Card>
            <SectionHeading
              title="Every mentor in the comparison"
              description={
                total === 0
                  ? undefined
                  : `Showing ${shownFrom} to ${shownTo} of ${total}.`
              }
            />

            <div className="mb-4 flex flex-wrap gap-4">
              <fieldset>
                <legend className="text-sm font-semibold text-ink">Sort by</legend>
                <div className="mt-2 flex gap-2">
                  {SORTS.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      aria-pressed={sort === option.id}
                      onClick={() => change({ sort: option.id })}
                      className={`min-h-[44px] rounded-xl border px-4 text-sm font-semibold ${
                        sort === option.id
                          ? "border-accent-700 bg-accent-50 text-accent-800"
                          : "border-line bg-white text-ink-muted"
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </fieldset>

              <fieldset>
                <legend className="text-sm font-semibold text-ink">Order</legend>
                <div className="mt-2 flex gap-2">
                  {ORDERS.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      aria-pressed={order === option.id}
                      onClick={() => change({ order: option.id })}
                      className={`min-h-[44px] rounded-xl border px-4 text-sm font-semibold ${
                        order === option.id
                          ? "border-accent-700 bg-accent-50 text-accent-800"
                          : "border-line bg-white text-ink-muted"
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </fieldset>
            </div>

            <div aria-live="polite">
              <ComparableRows
                items={page.data.items}
                emptyMessage="There are no mentors on this page. Try the first page."
              />
            </div>

            {total > PAGE_SIZE ? (
              <nav
                aria-label="Pages of similar mentors"
                className="mt-5 flex flex-wrap items-center gap-3 border-t border-line pt-4"
              >
                <Button
                  tone="quiet"
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  disabled={offset === 0}
                >
                  Previous
                </Button>
                <Button
                  tone="quiet"
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                  disabled={shownTo >= total}
                >
                  Next
                </Button>
                <p className="text-sm text-ink-soft">
                  {shownFrom} to {shownTo} of {total}
                </p>
              </nav>
            ) : null}
          </Card>
        </>
      ) : null}
    </div>
  );
}
