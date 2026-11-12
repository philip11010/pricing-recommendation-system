"use client";

/**
 * The directory: calm.
 *
 * Public, so a visitor can read it before they have an account and a mentor
 * can see their own card on it. Newest first, which is what makes it worth
 * reading: a mentor who registered a minute ago is listed on the same terms
 * as anybody else, with their verification shown as what it is.
 *
 * Paging is a Load more button rather than numbered pages. The list is read
 * downwards, and a second page that replaced the first would lose where the
 * reader was.
 */

import { useCallback, useEffect, useState } from "react";

import { MentorCardTile } from "@/components/mentor-card";
import {
  Banner,
  Button,
  Column,
  EmptyState,
  ErrorNotice,
  LoadingBlock,
} from "@/components/ui";
import { api } from "@/lib/api-client";
import type { MentorCard, Option } from "@/lib/api-types";
import { messageFor } from "@/lib/errors";
import { useAsync } from "@/lib/use-async";

const PAGE_SIZE = 12;

function FieldFilters({
  fields,
  chosen,
  onChoose,
}: {
  fields: Option[];
  chosen: string;
  onChoose: (field: string) => void;
}) {
  const all: Option[] = [{ id: "", label: "All fields" }, ...fields];
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by field">
      {all.map((field) => (
        <button
          key={field.id || "all"}
          type="button"
          aria-pressed={chosen === field.id}
          onClick={() => onChoose(field.id)}
          className={`min-h-[44px] cursor-pointer rounded-pill border px-4 py-2 text-[0.9375rem] font-semibold transition-colors duration-[180ms] ease-entrance mid:min-h-[40px] ${
            chosen === field.id
              ? "border-accent-700 bg-accent-100 text-accent-800"
              : "border-line bg-surface text-ink-700 hover:bg-surface-sunk"
          }`}
        >
          {field.label}
        </button>
      ))}
    </div>
  );
}

export default function MentorsPage() {
  const options = useAsync((signal) => api.options(signal), "directory-options");

  const [field, setField] = useState("");
  const [mentors, setMentors] = useState<MentorCard[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  // Bumped by the retry button, so asking again with the same filter asks
  // again rather than doing nothing.
  const [attempt, setAttempt] = useState(0);

  const load = useCallback(
    async (chosenField: string, offset: number, signal?: AbortSignal) => {
      const page = await api.directory(
        {
          field: chosenField || undefined,
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      );
      return page;
    },
    [],
  );

  useEffect(() => {
    const controller = new AbortController();
    let live = true;
    setLoading(true);
    setFailure(null);

    load(field, 0, controller.signal)
      .then((page) => {
        if (live) {
          setMentors(page.items);
          setTotal(page.total);
          setLoading(false);
        }
      })
      .catch((error: unknown) => {
        if (!live || (error instanceof DOMException && error.name === "AbortError")) {
          return;
        }
        setFailure(messageFor(error));
        setLoading(false);
      });

    return () => {
      live = false;
      controller.abort();
    };
  }, [field, load, attempt]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const page = await load(field, mentors.length);
      setMentors((was) => [...was, ...page.items]);
      setTotal(page.total);
    } catch (error) {
      setFailure(messageFor(error));
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <>
      <Banner
        title="Browse mentors"
        lead="See who is here and what they charge for a session."
      />
      <Column wide className="py-10">
        {options.status === "ready" && options.data ? (
          <FieldFilters
            fields={options.data.fields}
            chosen={field}
            onChoose={setField}
          />
        ) : null}

        <p className="mt-4 text-small text-ink-500" aria-live="polite">
          {loading
            ? "Loading mentors"
            : `Showing ${mentors.length} of ${total} ${total === 1 ? "mentor" : "mentors"}`}
        </p>

        <div className="mt-4">
          {loading ? <LoadingBlock label="Loading mentors" /> : null}

          {!loading && failure ? (
            <ErrorNotice
              message={failure}
              onRetry={() => setAttempt((count) => count + 1)}
            />
          ) : null}

          {!loading && !failure && mentors.length === 0 ? (
            <EmptyState title="No mentors to show yet">
              {field
                ? "No one mentors in that field yet. Choose All fields to see everybody."
                : "Nobody has registered yet. Be the first and your card appears here straight away."}
            </EmptyState>
          ) : null}

          {!loading && mentors.length > 0 ? (
            <div className="grid gap-6 mid:grid-cols-2 lg:grid-cols-3">
              {mentors.map((mentor) => (
                <MentorCardTile key={mentor.id} mentor={mentor} />
              ))}
            </div>
          ) : null}
        </div>

        {!loading && mentors.length < total ? (
          <div className="mt-8">
            <Button
              variant="quiet"
              onClick={loadMore}
              disabled={loadingMore}
              aria-busy={loadingMore}
            >
              {loadingMore ? "Loading" : "Load more"}
            </Button>
          </div>
        ) : null}
      </Column>
    </>
  );
}
