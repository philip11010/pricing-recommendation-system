"use client";

/**
 * The mentor's own page: calm, with a banner.
 *
 * What it shows is decided by what the platform actually measures. There is a
 * record of reviews month by month, so there is one bar chart of those. There
 * is no record of how busy a mentor has been or of what they charged in past
 * months, so there is no chart of either: a line through months the platform
 * cannot measure would be an invention.
 *
 * Four statistics, a sentence with the ladder under it, one chart, and the
 * table of services with what the mentor decided about each price.
 */

import { ReviewsChart } from "@/components/reviews-chart";
import { PriceLadder } from "@/components/price-ladder";
import { RequireAuth } from "@/components/require-auth";
import {
  Banner,
  ButtonLink,
  Card,
  CheckIcon,
  Chip,
  Column,
  EmptyState,
  ErrorNotice,
  LoadingBlock,
  Statistic,
} from "@/components/ui";
import { api } from "@/lib/api-client";
import type { Activity, Dashboard, Mentor } from "@/lib/api-types";
import {
  MINIMUM_CHART_POINTS,
  priceScale,
  reviewStats,
  type ReviewStats,
} from "@/lib/charts";
import { COMPARABLES_UNAVAILABLE_NOTE, decisionWord } from "@/lib/copy";
import { messageFor } from "@/lib/errors";
import { formatMoney } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

function firstNameOf(name: string): string {
  return (name ?? "").trim().split(/\s+/)[0] ?? "";
}

/** How the reviews statistic reads under its own figure. */
function reviewsNote(stats: ReviewStats): string {
  if (stats.previousMonths === 0) {
    return stats.recentMonths > 0
      ? `over the last ${stats.recentMonths} months`
      : "nothing recorded yet";
  }
  if (stats.direction === "more") {
    return `up from ${stats.previous} the period before`;
  }
  if (stats.direction === "fewer") {
    return `down from ${stats.previous} the period before`;
  }
  return `the same as the period before`;
}

function HeadlineStatistics({
  dashboard,
  activity,
  stats,
}: {
  dashboard: Dashboard;
  activity: Activity | null;
  stats: ReviewStats;
}) {
  const headline = dashboard.headline;
  const main = dashboard.services[0] ?? null;

  return (
    <div className="grid gap-6 mid:grid-cols-2 lg:grid-cols-4">
      <Statistic
        label="Your price now"
        value={headline.your_price ? formatMoney(headline.your_price) : "Not set yet"}
        note={
          main
            ? main.max_mentees <= 1
              ? "per one to one session"
              : `per session of ${main.max_mentees}`
            : "add a service to set one"
        }
      />
      <Statistic
        label="Similar mentors"
        value={
          headline.similar_typical
            ? formatMoney(headline.similar_typical)
            : "Not available"
        }
        note={
          dashboard.comparables_available
            ? "typical price"
            : "no comparison on this server"
        }
      />
      <Statistic
        label="Reviews this year"
        value={activity?.has_history ? String(stats.recent) : "None yet"}
        note={activity?.has_history ? reviewsNote(stats) : "your reviews appear here"}
      />
      <Statistic
        label="Busiest month"
        value={stats.busiest ? stats.busiest.label : "None yet"}
        note={
          stats.busiest
            ? `${stats.busiest.count} ${stats.busiest.count === 1 ? "review" : "reviews"}`
            : "no reviews recorded"
        }
      />
    </div>
  );
}

function HowYouCompare({ dashboard }: { dashboard: Dashboard }) {
  const headline = dashboard.headline;
  const main = dashboard.services[0] ?? null;
  const comparables = main?.comparables ?? null;

  if (!dashboard.comparables_available) {
    return (
      <Card role="region" aria-label="How you compare">
        <h2 className="text-h3 font-semibold">How you compare</h2>
        <p className="mt-2 text-ink-700">{COMPARABLES_UNAVAILABLE_NOTE}</p>
      </Card>
    );
  }

  const band =
    comparables && comparables.p25_price !== null && comparables.p75_price !== null
      ? { low: comparables.p25_price, high: comparables.p75_price }
      : null;

  if (!band || headline.your_price === null) {
    return (
      <Card role="region" aria-label="How you compare">
        <h2 className="text-h3 font-semibold">How you compare</h2>
        <p className="mt-2 max-w-prose text-ink-700">{headline.sentence}</p>
      </Card>
    );
  }

  const scale = priceScale([
    band.low,
    band.high,
    headline.your_price,
    headline.similar_typical,
    comparables?.median_price ?? null,
  ]);

  return (
    <Card role="region" aria-label="How you compare">
      <h2 className="text-h3 font-semibold">How you compare</h2>
      <div className="mt-2">
        <PriceLadder
          scale={scale}
          bandLow={band.low}
          bandHigh={band.high}
          current={headline.your_price}
          sentence={headline.sentence}
          tableCaption="Your price against similar mentors, in AUD"
        />
      </div>
    </Card>
  );
}

function ReviewsSection({ activity }: { activity: Activity | null }) {
  if (!activity || !activity.has_history || activity.months.length === 0) {
    return (
      <Card role="region" aria-label="Reviews each month">
        <h2 className="text-h3 font-semibold">Reviews each month</h2>
        <p className="mt-2 max-w-prose text-ink-700">
          You have no reviews recorded yet. Once mentees start reviewing your sessions,
          this is where you will see how they arrive month by month.
        </p>
      </Card>
    );
  }

  const stats = reviewStats(activity.months, activity.reviews_by_month);

  if (activity.months.length < MINIMUM_CHART_POINTS) {
    return (
      <Card role="region" aria-label="Reviews each month">
        <h2 className="text-h3 font-semibold">Reviews each month</h2>
        <p className="mt-2 max-w-prose text-ink-700">{activity.note}</p>
        <div className="mt-4 grid gap-6 mid:grid-cols-2">
          <Statistic
            label="Reviews recorded"
            value={String(stats.total)}
            note={`over ${activity.months.length} ${activity.months.length === 1 ? "month" : "months"}`}
          />
          <Statistic
            label="Busiest month"
            value={stats.busiest ? stats.busiest.label : "None yet"}
            note={stats.busiest ? `${stats.busiest.count} reviews` : undefined}
          />
        </div>
        <p className="mt-4 text-small text-ink-500">
          We show a chart once there are at least {MINIMUM_CHART_POINTS} months to read
          it from.
        </p>
      </Card>
    );
  }

  return (
    <Card role="region" aria-label="Reviews each month">
      <h2 className="text-h3 font-semibold">Reviews each month</h2>
      <div className="mt-2">
        <ReviewsChart
          months={activity.months}
          reviews={activity.reviews_by_month}
          sentence={activity.note}
          caption="Reviews received by month"
        />
      </div>
    </Card>
  );
}

function ServicesTable({ dashboard }: { dashboard: Dashboard }) {
  if (dashboard.services.length === 0) {
    return (
      <Card>
        <h2 className="text-h3 font-semibold">Your services</h2>
        <div className="mt-4">
          <EmptyState
            title="You have no services yet"
            action={
              <ButtonLink href="/dashboard/add-service" small>
                Add a service
              </ButtonLink>
            }
          >
            Add what you offer and we will suggest a price for it.
          </EmptyState>
        </div>
      </Card>
    );
  }

  return (
    <Card role="region" aria-label="Your services">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-h3 font-semibold">Your services</h2>
        <ButtonLink href="/dashboard/add-service" variant="quiet" small>
          Add a service
        </ButtonLink>
      </div>

      <div
        className="mt-4 max-w-full overflow-x-auto"
        tabIndex={0}
        role="group"
        aria-label="Your services"
      >
        <table className="w-full border-collapse text-[0.9375rem]">
          <caption className="px-3 py-2 text-left text-small text-ink-500">
            What you charge for each service, what we suggested, and what you decided.
          </caption>
          <thead>
            <tr>
              {["Service", "People", "Your price", "Suggested", "Decision"].map(
                (column) => (
                  <th
                    key={column}
                    scope="col"
                    className="border-b border-line px-3 py-2.5 text-left text-overline uppercase text-ink-500"
                  >
                    {column}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {dashboard.services.map((service) => {
              const latest = service.latest_recommendation;
              /*
               * What the mentor decided about the latest price.
               *
               * This response reports the decision beside each price rather
               * than on it, so the recommendation here carries no decision of
               * its own: the answer is its status, and the price the mentor
               * settled on is the last point on the timeline, which runs
               * oldest first. Read in that order, with the decision on the
               * recommendation first for the day it is filled in.
               */
              const timeline = service.timeline;
              const last = timeline.length > 0 ? timeline[timeline.length - 1] : null;
              const decision = latest?.decision ?? null;
              const action =
                decision?.action ?? last?.action ?? latest?.status ?? "pending";
              const settledPrice =
                decision?.final_price ?? last?.final_price ?? service.current_price;
              return (
                <tr key={service.service_id} className="even:bg-surface-sunk">
                  <td className="border-b border-line px-3 py-3">
                    {service.field_label}
                  </td>
                  <td className="tabular border-b border-line px-3 py-3">
                    {service.max_mentees}
                  </td>
                  <td className="tabular border-b border-line px-3 py-3">
                    {formatMoney(service.current_price)}
                  </td>
                  <td className="tabular border-b border-line px-3 py-3">
                    {latest ? formatMoney(latest.recommended_price) : "Not yet"}
                  </td>
                  <td className="border-b border-line px-3 py-3">
                    {action === "accepted" ? (
                      <Chip tone="accepted" icon={<CheckIcon />}>
                        {decisionWord(action)}
                      </Chip>
                    ) : action === "rejected" ? (
                      <Chip tone="declined">{decisionWord(action)}</Chip>
                    ) : action === "modified" ? (
                      <Chip tone="neutral">
                        {decisionWord(action)} to {formatMoney(settledPrice)}
                      </Chip>
                    ) : (
                      <Chip tone="neutral">{decisionWord(action)}</Chip>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function DashboardScreen({ mentor }: { mentor: Mentor }) {
  const dashboard = useAsync(
    (signal) => api.dashboard(mentor.id, signal),
    `dashboard-${mentor.id}`,
  );
  const activity = useAsync(
    (signal) => api.activity(mentor.id, signal),
    `activity-${mentor.id}`,
  );

  const stats = reviewStats(
    activity.data?.months ?? [],
    activity.data?.reviews_by_month ?? [],
  );

  return (
    <>
      <Banner
        title={`Hello, ${firstNameOf(mentor.full_name)}`}
        lead="Here is what you charge, how it compares, and how your reviews have come in."
        action={
          <ButtonLink href="/dashboard/add-service" variant="white">
            Add a service
          </ButtonLink>
        }
      />

      <Column wide className="py-10">
        {dashboard.status === "loading" ? (
          <LoadingBlock label="Loading your page" />
        ) : null}

        {dashboard.status === "error" ? (
          <ErrorNotice
            message={messageFor(dashboard.error)}
            onRetry={dashboard.reload}
          />
        ) : null}

        {dashboard.status === "ready" && dashboard.data ? (
          <div className="grid gap-6">
            {dashboard.data.services.length === 0 ? (
              <EmptyState
                title="You have not added a service yet"
                action={
                  <ButtonLink href="/dashboard/add-service">
                    Add your first service
                  </ButtonLink>
                }
              >
                Tell us what you offer and we will suggest a price for it. Your figures
                and your comparison appear here once you have one.
              </EmptyState>
            ) : (
              <>
                <HeadlineStatistics
                  dashboard={dashboard.data}
                  activity={activity.data}
                  stats={stats}
                />
                <HowYouCompare dashboard={dashboard.data} />
                <ReviewsSection activity={activity.data} />
              </>
            )}
            <ServicesTable dashboard={dashboard.data} />
          </div>
        ) : null}
      </Column>
    </>
  );
}

export default function DashboardPage() {
  return <RequireAuth>{(mentor) => <DashboardScreen mentor={mentor} />}</RequireAuth>;
}
