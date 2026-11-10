"use client";

/**
 * Pick a mentor to act as.
 *
 * This page exists because there is no authentication. The mentors listed are
 * the ones created for the demonstration, each with a track record behind
 * them, which is the only way to see the half of the system that prices a
 * mentor on their own history rather than on a form.
 *
 * It is the one mentor-related request that carries no identity header: it is
 * the list an identity is chosen from.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  Badge,
  Card,
  EmptyState,
  ErrorNotice,
  LoadingBlock,
  PageHeading,
} from "@/components/ui";
import { api } from "@/lib/api-client";
import type { DemoMentor } from "@/lib/api-types";
import { messageFor } from "@/lib/errors";
import { writeMentorId } from "@/lib/mentor-session";
import { useAsync } from "@/lib/use-async";

export default function MentorsPage() {
  const router = useRouter();
  const mentors = useAsync<DemoMentor[]>((signal) => api.demoMentors(signal), "demo");
  const [chosen, setChosen] = useState<number | null>(null);

  function choose(mentor: DemoMentor) {
    setChosen(mentor.id);
    writeMentorId(mentor.id, mentor.display_name);
    router.push("/dashboard");
  }

  return (
    <div>
      <PageHeading
        title="Open an existing mentor"
        lead="These mentors already have ratings and booking history, so their suggestions are worked out from their record rather than from a form. Choose one to see their page."
      />

      {mentors.status === "loading" ? <LoadingBlock label="Loading mentors" /> : null}

      {mentors.status === "error" ? (
        <ErrorNotice message={messageFor(mentors.error)} onRetry={mentors.reload} />
      ) : null}

      {mentors.status === "ready" && (mentors.data?.length ?? 0) === 0 ? (
        <EmptyState title="There are no mentors to open yet">
          The demonstration mentors have not been created on this server. Someone needs
          to run the seed step, or you can register as a new mentor instead.
        </EmptyState>
      ) : null}

      {mentors.status === "ready" && mentors.data ? (
        <ul className="grid gap-4 sm:grid-cols-2">
          {mentors.data.map((mentor) => (
            <li key={mentor.id}>
              <Card className="flex h-full flex-col justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-lg font-semibold">{mentor.display_name}</h2>
                    {mentor.has_history ? (
                      <Badge tone="accent">Has a track record</Badge>
                    ) : null}
                  </div>
                  {mentor.headline ? (
                    <p className="mt-2 text-sm leading-relaxed text-ink-muted">
                      {mentor.headline}
                    </p>
                  ) : null}
                  <dl className="mt-4 space-y-1 text-sm">
                    <div className="flex gap-2">
                      <dt className="text-ink-soft">Field</dt>
                      <dd className="font-medium">{mentor.field_label}</dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="text-ink-soft">Session</dt>
                      <dd className="font-medium">{mentor.session_label}</dd>
                    </div>
                  </dl>
                </div>
                <button
                  type="button"
                  onClick={() => choose(mentor)}
                  disabled={chosen !== null}
                  className="inline-flex min-h-[44px] items-center justify-center rounded-xl bg-accent-700 px-5 font-semibold text-white hover:bg-accent-800 disabled:opacity-60"
                >
                  {chosen === mentor.id
                    ? "Opening their page"
                    : `Continue as ${mentor.display_name}`}
                </button>
              </Card>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
