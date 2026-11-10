"use client";

/**
 * The mentor's own page.
 *
 * Per service: what they charge, what was last suggested, where that sits
 * against the market, how they have answered the advice, and the record of
 * both over time.
 *
 * There are no earnings and no income anywhere on it. The system has no
 * bookings to count, so a total would have to invent a volume, and an
 * invented figure on the page a mentor trusts is worse than no figure at all.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ComparablesSummaryLine } from "@/components/comparables";
import { RequireMentor } from "@/components/require-mentor";
import { TimelineChart } from "@/components/timeline-chart";
import {
  Badge,
  Button,
  ButtonLink,
  Callout,
  Card,
  EmptyState,
  ErrorNotice,
  LoadingBlock,
  SectionHeading,
  Statistic,
} from "@/components/ui";
import { api } from "@/lib/api-client";
import type {
  Dashboard,
  DashboardService,
  Mentor,
  ServiceHistory,
} from "@/lib/api-types";
import {
  COMPARABLES_UNAVAILABLE_NOTE,
  POSITION_HEADINGS,
  POSITION_MESSAGES,
  decisionWord,
} from "@/lib/copy";
import { messageFor } from "@/lib/errors";
import {
  formatDateTime,
  formatMentees,
  formatMoney,
  formatPercent,
} from "@/lib/format";
import { useAsync } from "@/lib/use-async";

interface PageData {
  mentor: Mentor;
  dashboard: Dashboard;
  histories: Record<number, ServiceHistory | null>;
}

export default function DashboardPage() {
  return (
    <RequireMentor>{(mentorId) => <DashboardView mentorId={mentorId} />}</RequireMentor>
  );
}

function DashboardView({ mentorId }: { mentorId: number }) {
  const page = useAsync<PageData>(async (signal) => {
    const [mentor, dashboard] = await Promise.all([
      api.mentor(mentorId, signal),
      api.dashboard(mentorId, signal),
    ]);
    const loaded = await Promise.all(
      dashboard.services.map(async (service) => {
        const history = await api
          .history(mentorId, service.service_id, signal)
          .catch(() => null);
        return [service.service_id, history] as const;
      }),
    );
    const histories: Record<number, ServiceHistory | null> = {};
    for (const [serviceId, history] of loaded) {
      histories[serviceId] = history;
    }
    return { mentor, dashboard, histories };
  }, `dashboard-${mentorId}`);

  if (page.status === "loading") {
    return <LoadingBlock label="Loading your page" />;
  }

  if (page.status === "error" || page.data === null) {
    return <ErrorNotice message={messageFor(page.error)} onRetry={page.reload} />;
  }

  const { mentor, dashboard, histories } = page.data;
  const totals = dashboard.totals;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          {dashboard.display_name}
        </h1>
        {mentor.headline ? (
          <p className="mt-2 max-w-prose text-lg text-ink-muted">{mentor.headline}</p>
        ) : null}
        <div className="mt-4 flex flex-wrap gap-3">
          <ButtonLink href="/dashboard/add-service" tone="secondary">
            Add another service
          </ButtonLink>
        </div>
      </header>

      <Card>
        <SectionHeading
          title="Across your services"
          description="How you have answered the suggestions so far. No earnings are reported here: there are no bookings in the system, so there is no volume to turn a price into a total."
        />
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Statistic label="Services" value={totals.services} />
          <Statistic
            label="Services with a price"
            value={totals.services_with_a_price}
          />
          <Statistic label="Suggestions given" value={totals.recommendations} />
          <Statistic
            label="Average gap from the suggestion"
            value={
              totals.average_difference_percent === null
                ? "Not yet"
                : formatPercent(totals.average_difference_percent, { signed: true })
            }
            hint={
              totals.average_difference_percent === null
                ? "Answer a suggestion with a price and this fills in."
                : "Positive means you charged more than suggested."
            }
          />
        </dl>
        <dl className="mt-3 grid gap-3 sm:grid-cols-4">
          <Statistic label="Accepted" value={totals.decision_counts.accepted} />
          <Statistic label="Modified" value={totals.decision_counts.modified} />
          <Statistic label="Declined" value={totals.decision_counts.rejected} />
          <Statistic label="Pending" value={totals.decision_counts.pending} />
        </dl>
      </Card>

      {dashboard.services.length === 0 ? (
        <EmptyState
          title="You have no services yet"
          action={<ButtonLink href="/dashboard/add-service">Add a service</ButtonLink>}
        >
          Describe a session you offer and we will suggest a price for it.
        </EmptyState>
      ) : null}

      {dashboard.services.map((service) => (
        <ServiceCard
          key={service.service_id}
          mentorId={mentorId}
          service={service}
          history={histories[service.service_id] ?? null}
          comparablesAvailable={dashboard.comparables_available}
        />
      ))}
    </div>
  );
}

function ServiceCard({
  mentorId,
  service,
  history,
  comparablesAvailable,
}: {
  mentorId: number;
  service: DashboardService;
  history: ServiceHistory | null;
  comparablesAvailable: boolean;
}) {
  const router = useRouter();
  const [reviewing, setReviewing] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function reviewPrice() {
    setReviewing(true);
    setFailure(null);
    try {
      const recommendation = await api.createRecommendation(
        mentorId,
        service.service_id,
      );
      router.push(`/recommendation/${recommendation.id}`);
    } catch (error) {
      setFailure(messageFor(error));
      setReviewing(false);
    }
  }

  const latest = service.latest_recommendation;

  return (
    <Card>
      <SectionHeading
        title={service.field_label}
        description={`${service.session_label}, up to ${formatMentees(
          service.max_mentees,
        )} per session.`}
        action={
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void reviewPrice()} disabled={reviewing}>
              {reviewing ? "Working it out" : "Review my price"}
            </Button>
            {comparablesAvailable ? (
              <Link
                href={`/similar/${service.service_id}`}
                className="inline-flex min-h-[44px] items-center rounded-xl border border-line bg-white px-4 text-sm font-semibold text-ink-muted hover:bg-shell"
              >
                Similar mentors
              </Link>
            ) : null}
          </div>
        }
      />

      {failure ? (
        <div className="mb-4">
          <Callout tone="caution">{failure}</Callout>
        </div>
      ) : null}

      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Statistic
          label="You charge now"
          value={formatMoney(service.current_price)}
          hint="Per session"
        />
        <Statistic
          label="Latest suggestion"
          value={latest ? formatMoney(latest.recommended_price) : "None yet"}
          hint={latest ? formatDateTime(latest.generated_at) : undefined}
        />
        <Statistic
          label="Your place in the market"
          value={
            service.price_percentile === null
              ? "Not available"
              : formatPercent(service.price_percentile, { decimals: 0 })
          }
          hint={
            service.price_percentile === null
              ? "Needs a price and a group to compare with."
              : "Of comparable mentors charge the same or less."
          }
        />
        <Statistic
          label="Average gap from the suggestion"
          value={
            service.average_difference_percent === null
              ? "Not yet"
              : formatPercent(service.average_difference_percent, { signed: true })
          }
          hint={
            service.average_difference_percent === null
              ? "Answer a suggestion with a price and this fills in."
              : "Positive means you charged more than suggested."
          }
        />
      </dl>

      <div className="mt-4 grid gap-3 sm:grid-cols-4">
        <Statistic label="Accepted" value={service.decision_counts.accepted} />
        <Statistic label="Modified" value={service.decision_counts.modified} />
        <Statistic label="Declined" value={service.decision_counts.rejected} />
        <Statistic label="Pending" value={service.decision_counts.pending} />
      </div>

      {service.position_vs_range ? (
        <div className="mt-4">
          <Callout
            tone={service.position_vs_range === "within" ? "accent" : "caution"}
            title={POSITION_HEADINGS[service.position_vs_range]}
          >
            {POSITION_MESSAGES[service.position_vs_range]}
          </Callout>
        </div>
      ) : null}

      <div className="mt-6 border-t border-line pt-5">
        <h3 className="text-base font-semibold">Suggestions over time</h3>
        {service.timeline.length === 0 ? (
          <div className="mt-3">
            <EmptyState title="Nothing to plot yet">
              Ask for a price and answer it, and the suggestion and what you chose will
              both appear here.
            </EmptyState>
          </div>
        ) : (
          <div className="mt-3">
            <TimelineChart timeline={service.timeline} />
          </div>
        )}
      </div>

      <div className="mt-6 border-t border-line pt-5">
        <h3 className="text-base font-semibold">Every suggestion for this service</h3>
        {history === null ? (
          <p className="mt-2 text-sm text-ink-muted">
            We could not load the record for this service.
          </p>
        ) : history.items.length === 0 ? (
          <div className="mt-3">
            <EmptyState title="No suggestions yet">
              Use Review my price above to get one.
            </EmptyState>
          </div>
        ) : (
          <ul className="mt-3 divide-y divide-line">
            {history.items.map((item) => {
              const status = item.decision?.action ?? item.recommendation.status;
              return (
                <li
                  key={item.recommendation.id}
                  className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-3"
                >
                  <div>
                    <p className="text-sm font-medium">
                      {formatDateTime(item.recommendation.generated_at)}
                    </p>
                    <p className="text-xs text-ink-soft">
                      Suggested {formatMoney(item.recommendation.recommended_price)}
                      {item.decision?.final_price !== null &&
                      item.decision?.final_price !== undefined
                        ? `, you chose ${formatMoney(item.decision.final_price)}`
                        : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge tone={status === "pending" ? "quiet" : "accent"}>
                      {decisionWord(status)}
                    </Badge>
                    <Link
                      href={`/recommendation/${item.recommendation.id}`}
                      className="text-sm font-semibold text-accent-800 underline"
                    >
                      Open
                    </Link>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="mt-6 border-t border-line pt-5">
        <h3 className="text-base font-semibold">The group you are compared with</h3>
        <div className="mt-3">
          {service.comparables === null ? (
            <Callout tone="quiet">{COMPARABLES_UNAVAILABLE_NOTE}</Callout>
          ) : (
            <ComparablesSummaryLine summary={service.comparables} />
          )}
        </div>
      </div>
    </Card>
  );
}
