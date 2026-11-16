/**
 * Adding a service starts from the last one the mentor described.
 *
 * The form prefilled the field and the skills and left the group size at one,
 * so a mentor who runs groups of six had to set the size again every time
 * while the two answers either side of it were already filled in. All three
 * come from the same service now, and this holds them to that.
 *
 * The live preview beside the form is mocked out. It asks the API for a
 * price on a timer, which is a different thing from what this file is about.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Mentor, OptionsResponse, Service } from "@/lib/api-types";
import { mostRecentService, startingGroupSize } from "@/lib/prefill";

function service(id: number, maxMentees: number, field: string): Service {
  return {
    id,
    mentor_id: 7,
    session_label: maxMentees > 1 ? "group" : "one_to_one",
    field,
    max_mentees: maxMentees,
    min_commitment: 1,
    skills: ["cv_review"],
    profile_verified: true,
    current_price: 300,
    created_at: "2025-01-01T00:00:00Z",
  };
}

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
  // Oldest first, as the API sends them.
  services: [
    service(1, 1, "technology_software"),
    service(2, 6, "business_entrepreneurship"),
  ],
  history: null,
  created_at: "2025-01-01T00:00:00Z",
};

const OPTIONS: OptionsResponse = {
  currency: "AUD",
  fields: [
    { id: "technology_software", label: "Technology and software" },
    { id: "business_entrepreneurship", label: "Business and entrepreneurship" },
  ],
  skills: [
    { id: "cv_review", label: "CV review" },
    { id: "interview_preparation", label: "Interview preparation" },
  ],
  max_mentees: { min: 1, max: 8 },
  session_label_rule: {
    one_to_one: { id: "one_to_one", label: "One to one", max_mentees: 1 },
    group: { id: "group", label: "Group", max_mentees_from: 2 },
  },
  min_commitment: [{ id: 1, label: "One session" }],
  min_commitment_default: 1,
  years_mentoring_bands: [],
  years_experience: { min: 0, max: 40 },
  education_levels: [],
};

let mentor: Mentor = MENTOR;

vi.mock("@/components/require-auth", () => ({
  RequireAuth: ({ children }: { children: (mentor: Mentor) => ReactNode }) => (
    <>{children(mentor)}</>
  ),
}));

vi.mock("@/components/price-preview", () => ({
  PricePreview: () => <div data-testid="price-preview" />,
}));

vi.mock("@/lib/api-client", () => ({
  api: {
    options: () => Promise.resolve(OPTIONS),
    addService: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

const { default: AddServicePage } = await import("@/app/dashboard/add-service/page");

beforeEach(() => {
  mentor = MENTOR;
});

describe("which service the form starts from", () => {
  it("is the most recent one, not the one they registered with", () => {
    expect(mostRecentService(MENTOR.services)?.id).toBe(2);
  });

  it("is nothing at all when the mentor has no service", () => {
    expect(mostRecentService([])).toBeNull();
  });
});

describe("the group size the picker opens on", () => {
  it("is the most recent service's size", () => {
    expect(startingGroupSize(service(2, 6, "law"), { min: 1, max: 8 })).toBe(6);
  });

  it("is the smallest allowed when there is no service to read", () => {
    expect(startingGroupSize(null, { min: 1, max: 8 })).toBe(1);
  });

  it("is held inside what the API says it accepts", () => {
    expect(startingGroupSize(service(2, 40, "law"), { min: 1, max: 8 })).toBe(8);
    expect(startingGroupSize(service(2, 0, "law"), { min: 1, max: 8 })).toBe(1);
  });
});

describe("the form itself", () => {
  it("opens with the group size of the most recent service, and stays editable", async () => {
    const user = userEvent.setup();
    render(<AddServicePage />);

    const size = await screen.findByText("6 people");
    expect(size).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "More people" }));
    expect(screen.getByText("7 people")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Fewer people" }));
    await user.click(screen.getByRole("button", { name: "Fewer people" }));
    expect(screen.getByText("5 people")).toBeInTheDocument();
  });

  it("prefills the field and the skills from that same service", async () => {
    render(<AddServicePage />);

    const field = await screen.findByLabelText(/Field/);
    expect(field).toHaveValue("business_entrepreneurship");
    expect(screen.getByRole("checkbox", { name: "CV review" })).toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: "Interview preparation" }),
    ).not.toBeChecked();
  });

  it("opens at one person for a mentor with no service to read", async () => {
    mentor = { ...MENTOR, services: [] };
    render(<AddServicePage />);

    expect(await screen.findByText("1 person")).toBeInTheDocument();
  });
});
