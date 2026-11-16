/**
 * Each section of the administration page, empty and populated.
 *
 * The empty case is tested as carefully as the populated one, because it is
 * the one somebody meets first: a fresh deployment has no traffic, and a page
 * of axes with no marks on them reads as broken rather than as new. Every
 * section has to say "No activity yet" instead.
 *
 * The populated case checks the sentence above each chart, the figures in the
 * table under it and the labels on the cards. The charts themselves draw
 * nothing in this environment, which has no layout, which is exactly why the
 * sentence and the table are mandatory: they are what a reader gets when the
 * chart cannot be seen, and here they are all there is.
 *
 * Two product rules are asserted outright rather than trusted: no section
 * claims the price responds to demand, and no section prints an em dash.
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ModelsSection,
  OutputsSection,
  OverviewSection,
  RecentActivity,
  UsageSection,
  UsersSection,
} from "@/components/admin/sections";
import type {
  AdminModels,
  AdminOutputs,
  AdminRecent,
  AdminSignups,
  AdminSummary,
  AdminUsage,
} from "@/lib/api-types";

const EM_DASH = String.fromCharCode(0x2014);

/* ------------------------------------------------------------- fixtures */

function emptySummary(): AdminSummary {
  return {
    accounts: 1,
    mentors: 0,
    verified_mentors: 0,
    demo_mentors: 0,
    services: 0,
    recommendations: 0,
    decisions: {
      accepted: 0,
      modified: 0,
      rejected: 0,
      total: 0,
      acceptance_rate_percent: null,
      pending: 0,
    },
    requests_last_24h: 0,
    median_response_ms: null,
    logged_requests: 0,
  };
}

function fullSummary(): AdminSummary {
  return {
    accounts: 12,
    mentors: 11,
    verified_mentors: 9,
    demo_mentors: 10,
    services: 14,
    recommendations: 31,
    decisions: {
      accepted: 12,
      modified: 5,
      rejected: 3,
      total: 20,
      acceptance_rate_percent: 60,
      pending: 11,
    },
    requests_last_24h: 48,
    median_response_ms: 37,
    logged_requests: 220,
  };
}

/** Thirty days of nothing, which is what a fresh deployment returns. */
function emptyUsage(): AdminUsage {
  const per_day = Array.from({ length: 30 }, (_value, index) => ({
    day: `2026-10-${String(index + 1).padStart(2, "0")}`,
    core: 0,
    full: 0,
    no_model: 0,
    total: 0,
  }));
  return {
    days: 30,
    per_day,
    by_endpoint: [
      { id: "preview", label: "Registration preview", count: 0 },
      { id: "registration", label: "Registration", count: 0 },
      { id: "service_added", label: "Service added", count: 0 },
      { id: "recalculation", label: "Price recalculated", count: 0 },
    ],
    latency_per_day: [],
    model_share: {
      core: 0,
      full: 0,
      no_model: 0,
      total: 0,
      core_percent: null,
      full_percent: null,
    },
  };
}

/**
 * Four days with calls, which is the floor for a line chart.
 *
 * DESIGN.md 8.1 puts the floor at four points, so this fixture sits exactly
 * on it: the response time chart is drawn from it, and the fixture below with
 * two days is what exercises the statistic cards instead.
 */
function fullUsage(): AdminUsage {
  const usage = emptyUsage();
  usage.per_day[26] = { day: "2026-10-27", core: 2, full: 0, no_model: 0, total: 2 };
  usage.per_day[27] = { day: "2026-10-28", core: 4, full: 1, no_model: 0, total: 5 };
  usage.per_day[28] = {
    day: "2026-10-29",
    core: 9,
    full: 3,
    no_model: 1,
    total: 13,
  };
  usage.per_day[29] = {
    day: "2026-10-30",
    core: 20,
    full: 6,
    no_model: 1,
    total: 27,
  };
  usage.by_endpoint = [
    { id: "preview", label: "Registration preview", count: 26 },
    { id: "registration", label: "Registration", count: 6 },
    { id: "service_added", label: "Service added", count: 4 },
    { id: "recalculation", label: "Price recalculated", count: 4 },
  ];
  usage.latency_per_day = [
    { day: "2026-10-27", median_ms: 28, p95_ms: 52, requests: 2 },
    { day: "2026-10-28", median_ms: 30, p95_ms: 61, requests: 5 },
    { day: "2026-10-29", median_ms: 31, p95_ms: 74, requests: 13 },
    { day: "2026-10-30", median_ms: 34, p95_ms: 96, requests: 27 },
  ];
  usage.model_share = {
    core: 35,
    full: 10,
    no_model: 2,
    total: 47,
    core_percent: 74.5,
    full_percent: 21.3,
  };
  return usage;
}

/** Two days with calls, which is below the floor for a line chart. */
function shortUsage(): AdminUsage {
  const usage = fullUsage();
  usage.latency_per_day = usage.latency_per_day.slice(-2);
  return usage;
}

function emptyOutputs(): AdminOutputs {
  return {
    recommendations: 0,
    currency: "AUD",
    price_buckets: [],
    median_price: null,
    by_field: [],
    decisions: {
      accepted: 0,
      modified: 0,
      rejected: 0,
      total: 0,
      acceptance_rate_percent: null,
      pending: 0,
    },
    range_widths: { median: null, median_percent_of_price: null, buckets: [] },
  };
}

function fullOutputs(): AdminOutputs {
  return {
    recommendations: 31,
    currency: "AUD",
    price_buckets: [
      { low: 100, high: 200, count: 11 },
      { low: 200, high: 300, count: 14 },
      { low: 300, high: 400, count: 6 },
    ],
    median_price: 238,
    by_field: [
      {
        id: "technology_software",
        label: "Technology and software",
        count: 18,
        median_price: 244,
      },
      { id: "law", label: "Law", count: 13, median_price: 210 },
    ],
    decisions: {
      accepted: 12,
      modified: 5,
      rejected: 3,
      total: 20,
      acceptance_rate_percent: 60,
      pending: 11,
    },
    range_widths: {
      median: 120,
      median_percent_of_price: 50.4,
      buckets: [
        { low: 50, high: 100, count: 9 },
        { low: 100, high: 150, count: 22 },
      ],
    },
  };
}

function emptySignups(): AdminSignups {
  return {
    weeks: 12,
    per_week: Array.from({ length: 12 }, (_value, index) => ({
      week: `2026-08-${String(index + 1).padStart(2, "0")}`,
      accounts: 0,
      verified: 0,
      unverified: 0,
    })),
    accounts: 0,
    verified: 0,
    unverified: 0,
  };
}

function fullSignups(): AdminSignups {
  const signups = emptySignups();
  signups.per_week[11] = {
    week: "2026-08-12",
    accounts: 4,
    verified: 3,
    unverified: 1,
  };
  signups.accounts = 11;
  signups.verified = 9;
  signups.unverified = 2;
  return signups;
}

function models(reportAvailable: boolean): AdminModels {
  const metrics = reportAvailable
    ? [
        {
          id: "r2",
          label: "R squared",
          value: 0.5437,
          scale: "0 to 1, higher is better",
        },
        {
          id: "rmse_log",
          label: "Log RMSE",
          value: 0.361646,
          scale: "log price units, lower is better",
        },
        { id: "mae", label: "MAE", value: 119.75, scale: "AUD, lower is better" },
        { id: "rmse", label: "RMSE", value: 191.89, scale: "AUD, lower is better" },
        {
          id: "cv_rmse_log",
          label: "Cross-validated log RMSE",
          value: 0.331387,
          scale: "log price units, lower is better, mean of 10 folds",
        },
      ]
    : [];
  return {
    measured_on: "the held-out typical test rows, which no model was fitted on",
    cross_validation:
      "10-fold cross-validation on the training rows, the same folds for every model, scored on the log of the price",
    currency: "AUD",
    report_available: reportAvailable,
    models: [
      {
        id: "core",
        label: "Core model",
        algorithm: reportAvailable ? "XGBoost" : null,
        inputs_note:
          "Eight profile inputs, every one of them available the moment a mentor registers.",
        file: "core.joblib",
        created_at: "2026-11-02T13:11:19",
        metrics,
      },
      {
        id: "full",
        label: "Full model",
        algorithm: reportAvailable ? "XGBoost" : null,
        inputs_note:
          "The same eight profile inputs plus twenty-eight track record inputs.",
        file: "full.joblib",
        created_at: "2026-11-02T13:14:17",
        metrics,
      },
    ],
  };
}

function recent(count: number): AdminRecent {
  return {
    limit: 50,
    currency: "AUD",
    events: Array.from({ length: count }, (_value, index) => ({
      id: 100 - index,
      created_at: "2026-10-30T09:15:00Z",
      endpoint: "preview",
      endpoint_label: "Registration preview",
      model_used: "core",
      field: "technology_software",
      field_label: "Technology and software",
      group_size: 2,
      recommended_price: 240,
      response_ms: 31,
      status_code: 200,
    })),
  };
}

/* ------------------------------------------------------- the empty states */

describe("every section on a platform nobody has used", () => {
  it("overview says there is no activity rather than drawing zeros", () => {
    render(<OverviewSection summary={emptySummary()} usage={emptyUsage()} />);

    const chart = screen.getByRole("region", { name: "Pricing calls per day" });
    expect(within(chart).getByText("No activity yet")).toBeInTheDocument();
    // The cards still report, because a count of nothing is a measurement.
    expect(screen.getByText("Accounts")).toBeInTheDocument();
    // No decisions means no rate, and the card says so in words.
    expect(screen.getByText("Not yet")).toBeInTheDocument();
    expect(screen.getByText("Not measured yet")).toBeInTheDocument();
  });

  it("model usage says so on all three of its charts", () => {
    render(<UsageSection usage={emptyUsage()} />);

    for (const name of [
      "Calls by path",
      "Response time by day",
      "Core against full",
      "Pricing calls per day",
    ]) {
      const section = screen.getByRole("region", { name });
      expect(within(section).getByText("No activity yet")).toBeInTheDocument();
    }
  });

  it("outputs says so on all four of its charts", () => {
    render(<OutputsSection outputs={emptyOutputs()} />);

    for (const name of [
      "Advised prices",
      "Recommendations by field",
      "Decisions by type",
      "How wide the ranges are",
    ]) {
      const section = screen.getByRole("region", { name });
      expect(within(section).getByText("No activity yet")).toBeInTheDocument();
    }
  });

  it("users says no mentors have registered", () => {
    render(<UsersSection signups={emptySignups()} />);

    expect(screen.getByText("No mentors have registered yet.")).toBeInTheDocument();
    const chart = screen.getByRole("region", { name: "New accounts per week" });
    expect(within(chart).getByText("No activity yet")).toBeInTheDocument();
  });

  it("models says the scores were not measured on this machine", () => {
    render(<ModelsSection models={models(false)} />);

    expect(screen.getByText(/No scores on this machine/)).toBeInTheDocument();
    // The cards are still there, with the files and what each model reads.
    expect(screen.getByRole("region", { name: "Core model" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Full model" })).toBeInTheDocument();
    expect(screen.getAllByText("No scores recorded")).toHaveLength(2);
  });

  it("recent activity says no calls have been logged", () => {
    render(<RecentActivity recent={recent(0)} />);

    expect(
      screen.getByText("No pricing calls have been logged yet."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

/* --------------------------------------------------- the populated states */

describe("overview with figures", () => {
  it("reports each headline count", () => {
    render(<OverviewSection summary={fullSummary()} usage={fullUsage()} />);

    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("31")).toBeInTheDocument();
    expect(screen.getByText("60%")).toBeInTheDocument();
    expect(screen.getByText("48")).toBeInTheDocument();
    expect(screen.getByText("37 ms")).toBeInTheDocument();
    expect(screen.getByText("11 not answered yet")).toBeInTheDocument();
  });

  it("states the daily split in words, and the calls that reached no model", () => {
    render(<OverviewSection summary={fullSummary()} usage={fullUsage()} />);

    const chart = screen.getByRole("region", { name: "Pricing calls per day" });
    const sentence = within(chart).getByText(/47 calls over the last 30 days/);
    expect(sentence).toHaveTextContent("35 answered by the core model");
    expect(sentence).toHaveTextContent("10 by the full model");
    // The two that reached no model are said out loud, because they are in
    // the total and the three figures would otherwise fail to add up.
    expect(sentence).toHaveTextContent("2 calls reached no model");
  });

  it("puts the same figures in a table under the chart", () => {
    render(<OverviewSection summary={fullSummary()} usage={fullUsage()} />);

    const chart = screen.getByRole("region", { name: "Pricing calls per day" });
    const table = within(chart).getByRole("group", {
      name: "Pricing calls per day, by the model that answered",
    });
    expect(
      within(table).getByRole("columnheader", { name: "Core" }),
    ).toBeInTheDocument();
    expect(
      within(table).getByRole("columnheader", { name: "No model" }),
    ).toBeInTheDocument();
    expect(within(table).getByText("30 October 2026")).toBeInTheDocument();
  });
});

describe("model usage with figures", () => {
  it("names the busiest path", () => {
    render(<UsageSection usage={fullUsage()} />);

    const chart = screen.getByRole("region", { name: "Calls by path" });
    expect(
      within(chart).getByText(/The most used was Registration preview, with 26 calls/),
    ).toBeInTheDocument();
  });

  it("reports both response time series and labels the dashed one", () => {
    render(<UsageSection usage={fullUsage()} />);

    const chart = screen.getByRole("region", { name: "Response time by day" });
    expect(within(chart).getByText(/95th percentile was 96 ms/)).toBeInTheDocument();
    // The second series is identified by a legend entry as well as by its
    // dashes, so it is never carried by colour alone. Twice over: once in
    // the legend and once as the column that holds the same figures.
    expect(within(chart).getAllByText("95th percentile")).toHaveLength(2);
    expect(
      within(chart).getByRole("columnheader", { name: "Median" }),
    ).toBeInTheDocument();
  });

  it("shows statistic cards rather than a line through too few days", () => {
    render(<UsageSection usage={shortUsage()} />);

    const section = screen.getByRole("region", { name: "Response time by day" });
    // DESIGN.md 8.1 puts the floor at four points: a line through two days
    // would draw a trend out of two measurements, and the direction it
    // happened to slope would be read as one.
    expect(
      within(section).getByText(/too few to plot against time/),
    ).toBeInTheDocument();
    expect(within(section).getByText("Highest 95th percentile")).toBeInTheDocument();
    expect(within(section).getByText("96 ms")).toBeInTheDocument();
    // The same figures are still there as a table.
    expect(
      within(section).getByRole("group", {
        name: "Median and 95th percentile response time, per day, in milliseconds",
      }),
    ).toBeInTheDocument();
  });

  it("states the share each model answered", () => {
    render(<UsageSection usage={fullUsage()} />);

    const chart = screen.getByRole("region", { name: "Core against full" });
    expect(
      within(chart).getByText(/the core model answered 74.5% and the full model 21.3%/),
    ).toBeInTheDocument();
  });
});

describe("outputs with figures", () => {
  it("states the median advised price and the fullest band", () => {
    render(<OutputsSection outputs={fullOutputs()} />);

    const chart = screen.getByRole("region", { name: "Advised prices" });
    expect(within(chart).getByText(/median of \$238 AUD/)).toBeInTheDocument();
    expect(within(chart).getByText(/between \$200 and \$300/)).toBeInTheDocument();
    // The buckets are half-open, and the table says so rather than leaving a
    // reader to guess which bucket a price of exactly 200 is in.
    const table = within(chart).getByRole("group", {
      name: "Advised prices by band, in AUD",
    });
    expect(within(table).getByText("$200 to under $300 AUD")).toBeInTheDocument();
  });

  it("reports each field with its median", () => {
    render(<OutputsSection outputs={fullOutputs()} />);

    const chart = screen.getByRole("region", { name: "Recommendations by field" });
    expect(
      within(chart).getByText(/The most was Technology and software, with 18/),
    ).toBeInTheDocument();
  });

  it("states what mentors decided, and how many are still waiting", () => {
    render(<OutputsSection outputs={fullOutputs()} />);

    const chart = screen.getByRole("region", { name: "Decisions by type" });
    const sentence = within(chart).getByText(/20 prices answered/);
    expect(sentence).toHaveTextContent("12 accepted");
    expect(sentence).toHaveTextContent("5 changed");
    expect(sentence).toHaveTextContent("3 declined");
    expect(sentence).toHaveTextContent("60% were taken as advised");
    expect(sentence).toHaveTextContent("11 more are waiting on a mentor");
  });

  it("reports the range width as a figure and as a share of the price", () => {
    render(<OutputsSection outputs={fullOutputs()} />);

    const chart = screen.getByRole("region", { name: "How wide the ranges are" });
    expect(
      within(chart).getByText(/\$120 AUD wide, which is 50.4% of the price/),
    ).toBeInTheDocument();
  });
});

describe("users with figures", () => {
  it("reports the accounts and the verified split", () => {
    render(<UsersSection signups={fullSignups()} />);

    expect(screen.getByText("Mentor accounts")).toBeInTheDocument();
    const chart = screen.getByRole("region", { name: "New accounts per week" });
    const sentence = within(chart).getByText(/11 mentor accounts/);
    expect(sentence).toHaveTextContent("9 have been verified");
    expect(sentence).toHaveTextContent("2 have not");
  });

  it("says the verified split is as the accounts stand now", () => {
    render(<UsersSection signups={fullSignups()} />);

    // The platform records that a mentor was checked and not when, so a
    // week-by-week split would be invented, and the page says so.
    expect(
      screen.getByText(/The verified split is as the accounts stand now/),
    ).toBeInTheDocument();
  });
});

describe("models with scores", () => {
  it("prints every metric with the scale it is measured on", () => {
    render(<ModelsSection models={models(true)} />);

    const core = screen.getByRole("region", { name: "Core model" });
    expect(within(core).getByText("R squared")).toBeInTheDocument();
    expect(within(core).getByText("0 to 1, higher is better")).toBeInTheDocument();
    expect(within(core).getByText("0.544")).toBeInTheDocument();
    // A figure in dollars is printed whole: the extra digits would imply a
    // precision the measurement has not got.
    expect(within(core).getByText("120")).toBeInTheDocument();
    expect(within(core).getByText("192")).toBeInTheDocument();
    expect(
      within(core).getByText("log price units, lower is better, mean of 10 folds"),
    ).toBeInTheDocument();
  });

  it("says what each model is given, and names the deployed file", () => {
    render(<ModelsSection models={models(true)} />);

    const core = screen.getByRole("region", { name: "Core model" });
    expect(within(core).getByText(/Eight profile inputs/)).toBeInTheDocument();
    expect(within(core).getByText("core.joblib")).toBeInTheDocument();

    const full = screen.getByRole("region", { name: "Full model" });
    expect(
      within(full).getByText(/twenty-eight track record inputs/),
    ).toBeInTheDocument();
    expect(within(full).getByText("full.joblib")).toBeInTheDocument();
  });

  it("says which rows the scores were measured on", () => {
    render(<ModelsSection models={models(true)} />);

    expect(screen.getByText(/held-out typical test rows/)).toBeInTheDocument();
    expect(screen.queryByText(/No scores on this machine/)).not.toBeInTheDocument();
  });
});

describe("recent activity with rows", () => {
  it("lists the calls and names no account", () => {
    render(<RecentActivity recent={recent(3)} />);

    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(4);
    expect(
      within(table).getByRole("columnheader", { name: "Took" }),
    ).toBeInTheDocument();
    expect(within(table).getAllByText("Registration preview")).toHaveLength(3);
    expect(within(table).getAllByText("$240")).toHaveLength(3);
    // No column, and no cell, names a mentor.
    expect(
      screen.getByText(/No account is named: the log records what was asked/),
    ).toBeInTheDocument();
    expect(within(table).queryByText(/@/)).not.toBeInTheDocument();
  });

  it("scrolls inside its own container rather than widening the page", () => {
    render(<RecentActivity recent={recent(3)} />);

    const scroller = screen.getByRole("group", { name: "Recent pricing calls" });
    expect(scroller).toHaveAttribute("tabindex", "0");
    expect(scroller.className).toContain("overflow-x-auto");
  });
});

/* -------------------------------------------------------- product rules */

describe("what the administration pages never say", () => {
  const rendered = () => [
    render(<OverviewSection summary={fullSummary()} usage={fullUsage()} />),
    render(<UsageSection usage={fullUsage()} />),
    render(<OutputsSection outputs={fullOutputs()} />),
    render(<UsersSection signups={fullSignups()} />),
    render(<ModelsSection models={models(true)} />),
    render(<RecentActivity recent={recent(2)} />),
  ];

  it("makes no claim that the price responds to demand", () => {
    for (const view of rendered()) {
      const said = (view.container.textContent ?? "").toLowerCase();
      for (const banned of [
        "demand-responsive",
        "demand responsive",
        "responds to demand",
        "demand-informed",
      ]) {
        expect(said).not.toContain(banned);
      }
      view.unmount();
    }
  });

  it("prints no em dash", () => {
    for (const view of rendered()) {
      expect(view.container.textContent ?? "").not.toContain(EM_DASH);
      view.unmount();
    }
  });

  it("never implies the system sets a price", () => {
    const view = render(<OutputsSection outputs={fullOutputs()} />);

    // The advisory design is the product, so the page that reports what the
    // models advised says whose decision it is.
    expect(
      screen.getByText(/Every price is advice: the mentor decides/),
    ).toBeInTheDocument();
    view.unmount();
  });
});
