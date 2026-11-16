/**
 * The mentor's own page, with the API's answers handed to it.
 *
 * One thing is being pinned down here above all others: the figure the page
 * opens with belongs to the service the API named, and not to whichever
 * service happens to be first in the list. Reading the first of the list is
 * what left a mentor who had just added a service and answered its price
 * looking at the price of the one they registered with, and a test that
 * renders the page from a two-service answer is the only place that can be
 * caught before a mentor catches it.
 *
 * The charts themselves draw nothing in this environment, which has no
 * layout, so what is asserted is everything around them: the sentences, the
 * labels and the tables that carry the same figures.
 */

import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  Activity,
  Dashboard,
  DashboardService,
  Mentor,
  Recommendation,
} from "@/lib/api-types";

const MENTOR: Mentor = {
  id: 7,
  full_name: "Test Mentor",
  email: "mentor@example.com",
  headline: null,
  bio: null,
  education_level: null,
  experience_summary: null,
  credentials: null,
  years_experience: null,
  years_mentoring_band: null,
  verified: true,
  is_demo: false,
  is_admin: false,
  services: [],
  history: null,
  created_at: "2025-01-01T00:00:00Z",
};

vi.mock("@/components/require-auth", () => ({
  RequireAuth: ({ children }: { children: (mentor: Mentor) => ReactNode }) => (
    <>{children(MENTOR)}</>
  ),
}));

const dashboardCall = vi.fn<() => Promise<Dashboard>>();
const activityCall = vi.fn<() => Promise<Activity>>();

vi.mock("@/lib/api-client", () => ({
  api: {
    dashboard: () => dashboardCall(),
    activity: () => activityCall(),
  },
}));

const { default: DashboardPage } = await import("@/app/dashboard/page");

function recommendation(price: number, serviceId: number): Recommendation {
  return {
    id: serviceId * 10,
    service_id: serviceId,
    recommended_price: price,
    price_low: price - 50,
    price_high: price + 50,
    price_per_mentee: price,
    price_per_mentee_low: price - 50,
    price_per_mentee_high: price + 50,
    currency: "AUD",
    max_mentees: 1,
    session_label: "one_to_one",
    model_used: "core",
    low_confidence: false,
    model_version: "test",
    status: "accepted",
    current_price: price,
    difference_vs_current_percent: 0,
    position_vs_range: "within",
    generated_at: "2025-02-01T00:00:00Z",
    decision: null,
  };
}

function service(
  serviceId: number,
  fieldLabel: string,
  price: number,
  maxMentees = 1,
): DashboardService {
  return {
    service_id: serviceId,
    field_label: fieldLabel,
    session_label: maxMentees > 1 ? "Group" : "One to one",
    max_mentees: maxMentees,
    current_price: price,
    currency: "AUD",
    latest_recommendation: recommendation(price, serviceId),
    position_vs_range: "within",
    price_percentile: 50,
    decision_counts: { accepted: 1, modified: 0, rejected: 0, pending: 0 },
    average_difference_percent: 0,
    timeline: [],
    comparables: {
      count: 40,
      median_price: price,
      p25_price: price - 60,
      p75_price: price + 60,
      median_price_per_mentee: price,
      currency: "AUD",
      match_level: 2,
      widened: false,
      match_description: `${fieldLabel} mentors`,
    },
  };
}

const FIRST = service(1, "Technology and software", 300);
const SECOND = service(2, "Law", 520, 4);

function dashboardWith(services: DashboardService[], aboutId: number): Dashboard {
  const main = services.find((entry) => entry.service_id === aboutId) ?? services[0];
  return {
    mentor_id: MENTOR.id,
    display_name: MENTOR.full_name,
    average_rating: 4.89,
    headline: {
      service_id: main.service_id,
      service_label: main.field_label,
      session_label: main.session_label,
      max_mentees: main.max_mentees,
      your_price: main.current_price,
      similar_typical: 420,
      position_vs_range: "within",
      sentence: "You charge about the same as other mentors in your field.",
      currency: "AUD",
    },
    currency: "AUD",
    comparables_available: true,
    demand: null,
    totals: {
      services: services.length,
      services_with_a_price: services.length,
      recommendations: services.length,
      decision_counts: {
        accepted: services.length,
        modified: 0,
        rejected: 0,
        pending: 0,
      },
      average_difference_percent: 0,
    },
    services,
  };
}

const MONTHS = [
  "2025-03-01",
  "2025-04-01",
  "2025-05-01",
  "2025-06-01",
  "2025-07-01",
  "2025-08-01",
  "2025-09-01",
];

const ACTIVITY: Activity = {
  has_history: true,
  months: MONTHS,
  reviews_by_month: [2, 5, 3, 6, 4, 9, 7],
  booked_share_by_month: MONTHS.map(() => null),
  price_by_month: MONTHS.map(() => null),
  currency: "AUD",
  note: "Your reviews month by month.",
};

const EMPTY_ACTIVITY: Activity = {
  has_history: false,
  months: [],
  reviews_by_month: [],
  booked_share_by_month: [],
  price_by_month: [],
  currency: "AUD",
  note: "Nothing recorded yet.",
};

async function show(dashboard: Dashboard, activity: Activity = ACTIVITY) {
  dashboardCall.mockResolvedValue(dashboard);
  activityCall.mockResolvedValue(activity);
  render(<DashboardPage />);
  await screen.findAllByText("Your price now");
}

/**
 * The statistic card with that heading, whatever its figure is.
 *
 * Found by the card around the label rather than by the label alone: the
 * same words appear again inside the tables under the charts, and a plain
 * text query finds those as well.
 */
function statistic(label: string): HTMLElement {
  for (const found of screen.getAllByText(label)) {
    const card = found.parentElement;
    if (found.tagName === "P" && card?.className.includes("rounded-card")) {
      return card;
    }
  }
  throw new Error(`no statistic card labelled "${label}"`);
}

beforeEach(() => {
  dashboardCall.mockReset();
  activityCall.mockReset();
});

describe("the price the dashboard opens with", () => {
  it("is the one the API named, not the first service in the list", async () => {
    await show(dashboardWith([FIRST, SECOND], SECOND.service_id));

    // $520 is the service the mentor settled on last. $300 is the one they
    // registered with, and the bug was that it showed instead.
    expect(within(statistic("Your price now")).getByText("$520")).toBeInTheDocument();
    expect(within(statistic("Your price now")).queryByText("$300")).toBeNull();
  });

  it("names the service when the mentor has more than one", async () => {
    await show(dashboardWith([FIRST, SECOND], SECOND.service_id));

    expect(
      within(statistic("Your price now")).getByText("Law, per session of 4"),
    ).toBeInTheDocument();
  });

  it("names no service when the mentor has only one", async () => {
    await show(dashboardWith([FIRST], FIRST.service_id));

    const card = statistic("Your price now");
    expect(within(card).getByText("per one to one session")).toBeInTheDocument();
    expect(within(card).queryByText(/Technology and software/)).toBeNull();
  });

  it("falls back to the first service when the API named none", async () => {
    const answer = dashboardWith([FIRST, SECOND], FIRST.service_id);
    answer.headline.service_id = null;
    await show(answer);

    expect(within(statistic("Your price now")).getByText("$300")).toBeInTheDocument();
  });
});

describe("the comparison beside it", () => {
  it("compares the same service the headline is about", async () => {
    await show(dashboardWith([FIRST, SECOND], SECOND.service_id));

    const compare = screen.getByRole("region", { name: "How you compare" });
    const said = compare.textContent ?? "";

    // The second service's quartiles, $460 to $580, rather than the first
    // service's $240 to $360.
    expect(said).toContain("$460");
    expect(said).toContain("$580");
    expect(said).not.toContain("$240");
    expect(said).not.toContain("$360");
  });
});

describe("the rating card", () => {
  it("writes the average as a fraction of five", async () => {
    await show(dashboardWith([FIRST], FIRST.service_id));

    expect(screen.getByText("4.9/5")).toBeInTheDocument();
    expect(screen.queryByText(/out of 5/)).toBeNull();
  });
});

describe("the demand card", () => {
  it("describes the recent months and never the price", async () => {
    await show(dashboardWith([FIRST], FIRST.service_id));

    const demand = screen.getByRole("region", { name: "Demand for your time" });
    expect(
      within(demand).getByText("How your activity has come in over the last months."),
    ).toBeInTheDocument();
    // Six months of the seven, summed, with the busiest named.
    expect(
      within(demand).getByText(
        "34 reviews from April 2025 to September 2025, with the most in August 2025.",
      ),
    ).toBeInTheDocument();

    const said = demand.textContent ?? "";
    for (const banned of [
      "higher price",
      "lower price",
      "raise",
      "lower your",
      "booked",
      "%",
    ]) {
      expect(said.toLowerCase()).not.toContain(banned.toLowerCase());
    }
  });

  it("opens the same months as a table", async () => {
    await show(dashboardWith([FIRST], FIRST.service_id));

    const demand = screen.getByRole("region", { name: "Demand for your time" });
    const table = within(demand).getByRole("group", {
      name: "Reviews recorded in each of the last months",
    });

    expect(within(table).getByText("September 2025")).toBeInTheDocument();
    // April onwards: the earliest month of the seven is outside the window.
    expect(within(table).queryByText("March 2025")).toBeNull();
  });

  it("is absent for a mentor with no months recorded", async () => {
    await show(dashboardWith([FIRST], FIRST.service_id), EMPTY_ACTIVITY);

    expect(screen.queryByRole("region", { name: "Demand for your time" })).toBeNull();
  });
});
