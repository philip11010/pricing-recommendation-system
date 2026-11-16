"use client";

/**
 * The five sections of the administration page, and the activity table.
 *
 * Each section takes the answers it needs and renders them. None of them
 * fetches anything: the page above decides what to load for the section that
 * is open, so a section is a pure function of what came back and can be
 * rendered in a test from a fixture.
 *
 * Two things every chart here has, without exception, because an operations
 * page is read by somebody deciding whether to trust what it says:
 *
 * * **The sentence before the chart.** It states the answer in words, and it
 *   is the label a screen reader is given in place of the chart.
 * * **An empty state.** Nothing here draws an axis with no marks on it. A
 *   platform nobody has used yet says "No activity yet", which is the truth,
 *   rather than a chart of zeros, which reads as a measurement.
 *
 * Nothing on this page claims the price responds to demand. The dashboard
 * reports what the service did and what the models scored, and neither is a
 * statement about what moves a price.
 */

import {
  CategoryBars,
  ChartCard,
  HistogramBars,
  LatencyLines,
  Legend,
  LineLegend,
  ShareBar,
  StackedBars,
} from "@/components/admin/charts";
import {
  ChartGrid,
  SectionHeading,
  StatCard,
  StatRow,
} from "@/components/admin/chrome";
import { DataDisclosure } from "@/components/data-disclosure";
import { EmptyState, Note } from "@/components/ui";
import {
  NO_ACTIVITY,
  bucketLabel,
  bucketTick,
  dayLabel,
  dayTick,
  decisionSummary,
  endpointSummary,
  fieldSummary,
  formatMilliseconds,
  hasAny,
  latencySummary,
  priceSummary,
  rangeSummary,
  shareSegments,
  shareSummary,
  signupSummary,
  usageSummary,
  weekLabel,
  weekTick,
} from "@/lib/admin";
import { MINIMUM_CHART_POINTS } from "@/lib/charts";
import type {
  AdminLatencyDay,
  AdminModels,
  AdminOutputs,
  AdminRecent,
  AdminSignups,
  AdminSummary,
  AdminUsage,
} from "@/lib/api-types";
import { formatDateTime, formatMoney, formatPercent } from "@/lib/format";

/* ---------------------------------------------------------------- shared */

/**
 * Calls per day, split by which model answered.
 *
 * Two series and not three. The calls that reached no model are real and are
 * counted, and they are reported in the sentence and in the table rather than
 * as a third segment: a stack of three pale steps on a phone is harder to
 * read than two, and those calls are the smallest of the three by a long way.
 */
function RequestsPerDay({ usage }: { usage: AdminUsage }) {
  const sentence = usageSummary(usage.per_day, usage.model_share);
  const segments = shareSegments([
    { id: "core", label: "Core model", count: usage.model_share.core },
    { id: "full", label: "Full model", count: usage.model_share.full },
  ]);

  return (
    <ChartCard
      title="Pricing calls per day"
      sentence={sentence}
      legend={<Legend segments={segments} />}
      empty={!hasAny(usage.per_day.map((day) => day.total))}
      caption="Pricing calls per day, by the model that answered"
      columns={["Day", "Core", "Full", "No model", "Total"]}
      rows={usage.per_day.map((day) => [
        dayLabel(day.day),
        <span key={`${day.day}-core`} className="tabular">
          {day.core}
        </span>,
        <span key={`${day.day}-full`} className="tabular">
          {day.full}
        </span>,
        <span key={`${day.day}-none`} className="tabular">
          {day.no_model}
        </span>,
        <span key={`${day.day}-total`} className="tabular">
          {day.total}
        </span>,
      ])}
    >
      <StackedBars
        data={usage.per_day}
        xKey="day"
        series={[
          { key: "core", label: "Core model" },
          { key: "full", label: "Full model" },
        ]}
        tickFormatter={dayTick}
      />
    </ChartCard>
  );
}

/**
 * Response times when there are too few days to draw a line.
 *
 * DESIGN.md 8.1 puts the floor at four points and says what to show instead:
 * a statistic card. A line through two days of measurements would draw a
 * trend out of two numbers, and the direction it happened to slope would be
 * read as one.
 */
function LatencyStatistics({ days }: { days: AdminLatencyDay[] }) {
  const medians = days.map((day) => day.median_ms);
  const typical = Math.round(
    medians.reduce((sum, value) => sum + value, 0) / medians.length,
  );
  const slowest = days.reduce((most, day) => (day.p95_ms > most.p95_ms ? day : most));
  const calls = days.reduce((sum, day) => sum + day.requests, 0);

  return (
    <section
      aria-label="Response time by day"
      className="min-w-0 rounded-chart border border-line bg-surface p-5 mid:p-6"
    >
      <h3 className="text-h3 font-bold">Response time by day</h3>
      <p className="mt-2 max-w-prose text-small text-ink-700">{latencySummary(days)}</p>
      <p className="mt-1 max-w-prose text-small text-ink-500">
        {days.length === 1 ? "One day has" : `${days.length} days have`} had calls,
        which is too few to plot against time: a line through them would draw a trend
        out of
        {days.length === 1 ? " one measurement" : " a couple of measurements"}.
      </p>

      <div className="mt-4 grid gap-4 mid:grid-cols-3">
        <StatCard label="Median" value={formatMilliseconds(typical)} />
        <StatCard
          label="Highest 95th percentile"
          value={formatMilliseconds(slowest.p95_ms)}
          note={dayLabel(slowest.day)}
        />
        <StatCard label="Calls measured" value={calls.toLocaleString()} />
      </div>

      <DataDisclosure
        caption="Median and 95th percentile response time, per day, in milliseconds"
        columns={["Day", "Median", "95th percentile", "Calls"]}
        rows={days.map((day) => [
          dayLabel(day.day),
          <span key={`${day.day}-median`} className="tabular">
            {day.median_ms}
          </span>,
          <span key={`${day.day}-p95`} className="tabular">
            {day.p95_ms}
          </span>,
          <span key={`${day.day}-calls`} className="tabular">
            {day.requests}
          </span>,
        ])}
      />
    </section>
  );
}

/* -------------------------------------------------------------- overview */

export function OverviewSection({
  summary,
  usage,
}: {
  summary: AdminSummary;
  usage: AdminUsage;
}) {
  const decisions = summary.decisions;

  return (
    <div className="space-y-6">
      <SectionHeading
        title="Overview"
        lead="What is on the platform, and what it has been asked to do."
      />

      <StatRow>
        <StatCard
          label="Accounts"
          value={summary.accounts.toLocaleString()}
          note={
            summary.mentors === summary.accounts
              ? undefined
              : `${summary.mentors.toLocaleString()} are mentors`
          }
        />
        <StatCard
          label="Mentors"
          value={summary.mentors.toLocaleString()}
          note={
            summary.demo_mentors > 0
              ? `${summary.demo_mentors.toLocaleString()} seeded for the demo`
              : undefined
          }
        />
        <StatCard
          label="Recommendations"
          value={summary.recommendations.toLocaleString()}
          note={
            decisions.pending > 0
              ? `${decisions.pending.toLocaleString()} not answered yet`
              : undefined
          }
        />
        <StatCard
          label="Accepted as advised"
          value={
            decisions.acceptance_rate_percent === null
              ? "Not yet"
              : formatPercent(decisions.acceptance_rate_percent)
          }
          note={
            decisions.total === 0
              ? "no prices answered yet"
              : `of ${decisions.total.toLocaleString()} answered`
          }
        />
        <StatCard
          label="Calls, last 24 hours"
          value={summary.requests_last_24h.toLocaleString()}
        />
        <StatCard
          label="Median response"
          value={formatMilliseconds(summary.median_response_ms)}
          note={
            summary.logged_requests > 0
              ? `over ${summary.logged_requests.toLocaleString()} logged calls`
              : undefined
          }
        />
      </StatRow>

      <RequestsPerDay usage={usage} />
    </div>
  );
}

/* ----------------------------------------------------------- model usage */

export function UsageSection({ usage }: { usage: AdminUsage }) {
  const share = shareSegments([
    { id: "core", label: "Core model", count: usage.model_share.core },
    { id: "full", label: "Full model", count: usage.model_share.full },
    { id: "none", label: "No model reached", count: usage.model_share.no_model },
  ]);

  return (
    <div className="space-y-6">
      <SectionHeading
        title="Model usage"
        lead={`Which path was called, which model answered, and how long it took. The last ${usage.days} days.`}
      />

      <ChartGrid>
        <ChartCard
          title="Calls by path"
          sentence={endpointSummary(usage.by_endpoint)}
          empty={!hasAny(usage.by_endpoint.map((row) => row.count))}
          caption="Pricing calls by the path that was called"
          columns={["Path", "Calls"]}
          rows={usage.by_endpoint.map((row) => [
            row.label,
            <span key={row.id} className="tabular">
              {row.count.toLocaleString()}
            </span>,
          ])}
        >
          <CategoryBars
            data={usage.by_endpoint.map((row) => ({
              label: row.label,
              count: row.count,
            }))}
          />
        </ChartCard>

        {usage.latency_per_day.length > 0 &&
        usage.latency_per_day.length < MINIMUM_CHART_POINTS ? (
          <LatencyStatistics days={usage.latency_per_day} />
        ) : (
          <ChartCard
            title="Response time by day"
            sentence={latencySummary(usage.latency_per_day)}
            note="Measured around the whole request, which is what the caller waited for."
            legend={
              <LineLegend
                series={[
                  { id: "median", label: "Median" },
                  { id: "p95", label: "95th percentile", dashed: true },
                ]}
              />
            }
            empty={usage.latency_per_day.length === 0}
            caption="Median and 95th percentile response time, per day, in milliseconds"
            columns={["Day", "Median", "95th percentile", "Calls"]}
            rows={usage.latency_per_day.map((day) => [
              dayLabel(day.day),
              <span key={`${day.day}-median`} className="tabular">
                {day.median_ms}
              </span>,
              <span key={`${day.day}-p95`} className="tabular">
                {day.p95_ms}
              </span>,
              <span key={`${day.day}-calls`} className="tabular">
                {day.requests}
              </span>,
            ])}
          >
            <LatencyLines data={usage.latency_per_day} />
          </ChartCard>
        )}
      </ChartGrid>

      <ShareBar
        segments={share}
        title="Core against full"
        sentence={shareSummary(usage.model_share)}
        caption="Pricing calls by the model that answered"
      />

      <RequestsPerDay usage={usage} />
    </div>
  );
}

/* --------------------------------------------------------------- outputs */

export function OutputsSection({ outputs }: { outputs: AdminOutputs }) {
  const decisions = shareSegments([
    { id: "accepted", label: "Accepted", count: outputs.decisions.accepted },
    { id: "modified", label: "Changed", count: outputs.decisions.modified },
    { id: "rejected", label: "Declined", count: outputs.decisions.rejected },
  ]);

  return (
    <div className="space-y-6">
      <SectionHeading
        title="Outputs"
        lead="What the models advised, and what mentors did about it. Every price is advice: the mentor decides."
      />

      <ChartGrid>
        <ChartCard
          title="Advised prices"
          sentence={priceSummary(outputs)}
          note={`Per session, in ${outputs.currency}. Each bar covers its lower figure up to, and not including, its upper one.`}
          empty={outputs.price_buckets.length === 0}
          caption={`Advised prices by band, in ${outputs.currency}`}
          columns={["Band", "Recommendations"]}
          rows={outputs.price_buckets.map((bucket) => [
            bucketLabel(bucket, outputs.currency),
            <span key={bucket.low} className="tabular">
              {bucket.count.toLocaleString()}
            </span>,
          ])}
        >
          <HistogramBars
            data={outputs.price_buckets.map((bucket) => ({
              tick: bucketTick(bucket),
              count: bucket.count,
            }))}
          />
        </ChartCard>

        <ChartCard
          title="Recommendations by field"
          sentence={fieldSummary(outputs)}
          empty={outputs.by_field.length === 0}
          caption={`Recommendations and median advised price by field, in ${outputs.currency}`}
          columns={["Field", "Recommendations", "Median price"]}
          rows={outputs.by_field.map((row) => [
            row.label,
            <span key={`${row.id}-count`} className="tabular">
              {row.count.toLocaleString()}
            </span>,
            <span key={`${row.id}-median`} className="tabular">
              {formatMoney(row.median_price)}
            </span>,
          ])}
        >
          <CategoryBars
            data={outputs.by_field.map((row) => ({
              label: row.label,
              count: row.count,
            }))}
          />
        </ChartCard>
      </ChartGrid>

      <ChartGrid>
        <ShareBar
          segments={decisions}
          title="Decisions by type"
          sentence={decisionSummary(outputs.decisions)}
          caption="What mentors did with the prices they were advised"
        />

        <ChartCard
          title="How wide the ranges are"
          sentence={rangeSummary(outputs)}
          note={`The distance from the low end of an advised range to the high end, in ${outputs.currency}.`}
          empty={outputs.range_widths.buckets.length === 0}
          caption={`Width of the advised range, by band, in ${outputs.currency}`}
          columns={["Width", "Recommendations"]}
          rows={outputs.range_widths.buckets.map((bucket) => [
            bucketLabel(bucket, outputs.currency),
            <span key={bucket.low} className="tabular">
              {bucket.count.toLocaleString()}
            </span>,
          ])}
        >
          <HistogramBars
            data={outputs.range_widths.buckets.map((bucket) => ({
              tick: bucketTick(bucket),
              count: bucket.count,
            }))}
          />
        </ChartCard>
      </ChartGrid>
    </div>
  );
}

/* ----------------------------------------------------------------- users */

export function UsersSection({ signups }: { signups: AdminSignups }) {
  const segments = shareSegments([
    { id: "verified", label: "Verified", count: signups.verified },
    { id: "unverified", label: "Not verified yet", count: signups.unverified },
  ]);

  return (
    <div className="space-y-6">
      <SectionHeading
        title="Users"
        lead={`Mentor accounts, and how many of them have been checked. The last ${signups.weeks} weeks.`}
      />

      <StatRow>
        <StatCard label="Mentor accounts" value={signups.accounts.toLocaleString()} />
        <StatCard label="Verified" value={signups.verified.toLocaleString()} />
        <StatCard
          label="Not verified yet"
          value={signups.unverified.toLocaleString()}
        />
      </StatRow>

      <ChartCard
        title="New accounts per week"
        sentence={signupSummary(signups)}
        note="The verified split is as the accounts stand now. The platform records that a mentor was checked, not when, so a week-by-week split would be invented."
        legend={<Legend segments={segments} />}
        empty={!hasAny(signups.per_week.map((week) => week.accounts))}
        caption="New mentor accounts per week, by whether they have been verified"
        columns={["Week", "Verified", "Not verified", "Total"]}
        rows={signups.per_week.map((week) => [
          weekLabel(week.week),
          <span key={`${week.week}-v`} className="tabular">
            {week.verified}
          </span>,
          <span key={`${week.week}-u`} className="tabular">
            {week.unverified}
          </span>,
          <span key={`${week.week}-t`} className="tabular">
            {week.accounts}
          </span>,
        ])}
      >
        <StackedBars
          data={signups.per_week}
          xKey="week"
          series={[
            { key: "verified", label: "Verified" },
            { key: "unverified", label: "Not verified yet" },
          ]}
          tickFormatter={weekTick}
        />
      </ChartCard>
    </div>
  );
}

/* ---------------------------------------------------------------- models */

/**
 * How many decimal places one score is worth printing.
 *
 * An R squared and a log RMSE live between 0 and 1, so three places say
 * something. A figure in dollars does not: a model whose mean error is 119.75
 * is a model whose mean error is about 120, and the extra digits imply a
 * precision the measurement has not got.
 */
function metricValue(id: string, value: number): string {
  const places = id === "mae" || id === "rmse" ? 0 : 3;
  return value.toLocaleString(undefined, {
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  });
}

export function ModelsSection({ models }: { models: AdminModels }) {
  return (
    <div className="space-y-6">
      <SectionHeading
        title="Models"
        lead={`Two models are deployed. Every score below was measured on ${models.measured_on}.`}
      />

      {models.report_available ? null : (
        <Note tone="caution" title="No scores on this machine.">
          The training report is an output of a local training run and is not kept in
          the repository, so the figures were not measured here. The cards below still
          name the deployed files and what each model is given.
        </Note>
      )}

      <div className="grid gap-5 xl:grid-cols-2">
        {models.models.map((card) => (
          <section
            key={card.id}
            aria-label={card.label}
            className="min-w-0 rounded-card border border-line bg-surface p-5 mid:p-6"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-h3 font-bold">{card.label}</h3>
              {card.algorithm ? (
                <p className="text-small text-ink-500">{card.algorithm}</p>
              ) : null}
            </div>
            <p className="mt-2 max-w-prose text-small text-ink-700">
              {card.inputs_note}
            </p>

            {card.metrics.length === 0 ? (
              <div className="mt-4">
                <EmptyState title="No scores recorded">
                  Run the training script on this machine to measure them.
                </EmptyState>
              </div>
            ) : (
              <dl className="mt-5 space-y-3">
                {card.metrics.map((metric) => (
                  <div
                    key={metric.id}
                    className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-line pb-3 last:border-0 last:pb-0"
                  >
                    <dt className="min-w-0">
                      <span className="font-semibold">{metric.label}</span>
                      {/* The scale is printed, not implied. A bare 0.54 is
                          not a score until it is said which way is better. */}
                      <span className="block text-small text-ink-500">
                        {metric.scale}
                      </span>
                    </dt>
                    <dd className="tabular text-[1.125rem] font-bold">
                      {metricValue(metric.id, metric.value)}
                    </dd>
                  </div>
                ))}
              </dl>
            )}

            <dl className="mt-5 space-y-1 text-small text-ink-500">
              <div className="flex gap-2">
                <dt className="font-semibold">File</dt>
                <dd>{card.file ?? "Not on this machine"}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="font-semibold">Fitted</dt>
                <dd>
                  {card.created_at ? formatDateTime(card.created_at) : "Not recorded"}
                </dd>
              </div>
            </dl>
          </section>
        ))}
      </div>

      <p className="max-w-prose text-small text-ink-500">
        {models.cross_validation}. Prices are in {models.currency}.
      </p>
    </div>
  );
}

/* -------------------------------------------------------- recent activity */

export function RecentActivity({ recent }: { recent: AdminRecent }) {
  return (
    <section
      aria-label="Recent activity"
      className="min-w-0 rounded-chart border border-line bg-surface p-5 mid:p-6"
    >
      <h3 className="text-h3 font-bold">Recent activity</h3>
      <p className="mt-2 max-w-prose text-small text-ink-700">
        {recent.events.length === 0
          ? "No pricing calls have been logged yet."
          : `The last ${recent.events.length} pricing calls, newest first. No account is named: the log records what was asked of a model, not who asked.`}
      </p>

      {recent.events.length === 0 ? (
        <div className="mt-4">
          <EmptyState title={NO_ACTIVITY}>
            Calls appear here as soon as the platform is used.
          </EmptyState>
        </div>
      ) : (
        <div
          className="mt-4 max-w-full overflow-x-auto"
          tabIndex={0}
          role="group"
          aria-label="Recent pricing calls"
        >
          <table className="w-full border-collapse text-[0.9375rem]">
            <caption className="px-3 py-2 text-left text-small text-ink-500">
              The latest pricing calls, with the price in {recent.currency}
            </caption>
            <thead>
              <tr>
                {[
                  "When",
                  "Path",
                  "Model",
                  "Field",
                  "Group",
                  "Price",
                  "Took",
                  "Status",
                ].map((column) => (
                  <th
                    key={column}
                    scope="col"
                    className="whitespace-nowrap border-b border-line px-3 py-2.5 text-left text-overline uppercase text-ink-500"
                  >
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {recent.events.map((event) => (
                <tr key={event.id} className="even:bg-surface-sunk">
                  <td className="whitespace-nowrap border-b border-line px-3 py-2.5">
                    {formatDateTime(event.created_at)}
                  </td>
                  <td className="whitespace-nowrap border-b border-line px-3 py-2.5">
                    {event.endpoint_label}
                  </td>
                  <td className="border-b border-line px-3 py-2.5">
                    {event.model_used ?? "None"}
                  </td>
                  <td className="border-b border-line px-3 py-2.5">
                    {event.field_label ?? "Not recorded"}
                  </td>
                  <td className="tabular border-b border-line px-3 py-2.5">
                    {event.group_size ?? "-"}
                  </td>
                  <td className="tabular whitespace-nowrap border-b border-line px-3 py-2.5">
                    {event.recommended_price === null
                      ? "None"
                      : formatMoney(event.recommended_price)}
                  </td>
                  <td className="tabular whitespace-nowrap border-b border-line px-3 py-2.5">
                    {event.response_ms} ms
                  </td>
                  <td className="tabular border-b border-line px-3 py-2.5">
                    {event.status_code}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
