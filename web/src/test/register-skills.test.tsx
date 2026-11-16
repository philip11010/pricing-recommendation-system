/**
 * The registration form's skills at work follow the field, and nothing else does.
 *
 * Three things are checked here, and the third is the one that matters.
 *
 * The labels swap: picking a field redraws the ten pills under "skills at
 * work" with that field's own names, and leaves the other twenty alone.
 *
 * The ticks reset: those ten labels no longer mean what they meant, so the
 * ticks against them go, the other twenty stay, and the mentor is told.
 *
 * The payload does not move: the pills send skill ids, and the ids are the
 * same ten positions in every field. So two mentors who tick the same
 * positions in different fields send the same `skills` list to /preview, and
 * the price they are shown is worked out from the same count. The API is
 * mocked here only to read what was sent to it.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { OptionsResponse, PreviewPayload } from "@/lib/api-types";
import { WORK_SKILLS_RESET_NOTE } from "@/lib/copy";
import { FIELD_WORK_SKILLS } from "@/lib/work-skills";

/** The thirty labels /meta/options sends, in the order it sends them. */
const API_SKILLS: [string, string][] = [
  ["cv_review", "CV review"],
  ["cover_letter_writing", "Cover letter writing"],
  ["interview_preparation", "Interview preparation"],
  ["career_planning", "Career planning"],
  ["career_change", "Career change"],
  ["salary_negotiation", "Salary negotiation"],
  ["networking", "Networking"],
  ["personal_branding", "Personal branding"],
  ["linkedin_profile_review", "LinkedIn profile review"],
  ["leadership", "Leadership"],
  ["public_speaking", "Public speaking"],
  ["time_management", "Time management"],
  ["project_management", "Project management"],
  ["portfolio_review", "Portfolio review"],
  ["graduate_applications", "Graduate applications"],
  ["job_search_strategy", "Job search strategy"],
  ["workplace_communication", "Workplace communication"],
  ["conflict_resolution", "Conflict resolution"],
  ["mentoring_skills", "Mentoring skills"],
  ["presentation_skills", "Presentation skills"],
  ["data_analysis", "Data analysis"],
  ["technical_skills_coaching", "Technical skills coaching"],
  ["entrepreneurship", "Entrepreneurship"],
  ["work_life_balance", "Work-life balance"],
  ["goal_setting", "Goal setting"],
  ["performance_reviews", "Performance reviews"],
  ["promotion_planning", "Promotion planning"],
  ["remote_work", "Remote work"],
  ["further_studies_guidance", "Further studies guidance"],
  ["professional_ethics", "Professional ethics"],
];

const OPTIONS: OptionsResponse = {
  currency: "AUD",
  fields: [
    { id: "law", label: "Law" },
    { id: "engineering", label: "Engineering" },
    { id: "medicine_health", label: "Medicine and health" },
  ],
  skills: API_SKILLS.map(([id, label]) => ({ id, label })),
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

const previewed: PreviewPayload[] = [];

const preview = vi.fn((payload: PreviewPayload) => {
  previewed.push(payload);
  return Promise.resolve({
    session_price: 300,
    per_person_price: 300,
    range_low: 250,
    range_high: 360,
    currency: "AUD",
    low_confidence: true,
  });
});

vi.mock("@/lib/api-client", () => ({
  api: {
    options: () => Promise.resolve(OPTIONS),
    preview: (payload: PreviewPayload) => preview(payload),
    register: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

const { default: RegisterPage } = await import("@/app/register/page");

/** The debounce the preview panel waits out before it asks for a price. */
const DEBOUNCE_MS = 400;

/**
 * Wait out the debounce and let the answer land.
 *
 * Inside act, because the answer arrives in a promise and sets state on the
 * preview panel: advancing the clock without it leaves React warning that
 * something updated outside a render it was told about.
 */
async function settlePreview() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(DEBOUNCE_MS * 2);
  });
}

/*
 * A pill by the words on it. The accessible name is matched in full, so
 * "Leadership" never answers for "Leadership and strategy".
 */
function pill(name: string) {
  return screen.getByRole("checkbox", { name });
}

function noPill(name: string) {
  return screen.queryByRole("checkbox", { name });
}

beforeEach(() => {
  previewed.length = 0;
  preview.mockClear();
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

async function openForm() {
  const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  render(<RegisterPage />);
  await screen.findByRole("heading", { name: "Skills you cover" });
  return user;
}

describe("the skills at work follow the field", () => {
  it("shows the labels the API sent before a field is picked", async () => {
    await openForm();

    expect(pill("Leadership")).toBeInTheDocument();
    expect(pill("Technical skills coaching")).toBeInTheDocument();
    expect(noPill("Legal research")).toBeNull();
  });

  it("swaps all ten when a field is picked", async () => {
    const user = await openForm();

    await user.selectOptions(screen.getByLabelText("Your field"), "law");

    for (const label of Object.values(FIELD_WORK_SKILLS.law)) {
      expect(pill(label)).toBeInTheDocument();
    }
    expect(noPill("Leadership")).toBeNull();
    expect(noPill("Technical skills coaching")).toBeNull();
  });

  it("swaps them again when the field changes", async () => {
    const user = await openForm();
    const field = screen.getByLabelText("Your field");

    await user.selectOptions(field, "law");
    expect(pill("Courtroom advocacy")).toBeInTheDocument();

    await user.selectOptions(field, "engineering");
    expect(noPill("Courtroom advocacy")).toBeNull();
    for (const label of Object.values(FIELD_WORK_SKILLS.engineering)) {
      expect(pill(label)).toBeInTheDocument();
    }
  });

  it("leaves the other three headings alone, in every field", async () => {
    const user = await openForm();
    const field = screen.getByLabelText("Your field");
    const constant = [
      "CV review",
      "Job search strategy",
      "Career planning",
      "Further studies guidance",
      "Entrepreneurship",
      "Professional ethics",
    ];

    for (const chosen of ["law", "engineering", "medicine_health"]) {
      await user.selectOptions(field, chosen);
      for (const label of constant) {
        expect(pill(label), `${label} in ${chosen}`).toBeInTheDocument();
      }
      expect(screen.getAllByRole("checkbox")).toHaveLength(30);
    }
  });

  it("still draws all thirty, in the same four headings", async () => {
    const user = await openForm();

    await user.selectOptions(screen.getByLabelText("Your field"), "medicine_health");

    expect(screen.getAllByRole("checkbox")).toHaveLength(30);
    for (const name of [
      "Getting hired",
      "Growing your career",
      "Skills at work",
      "Business and balance",
    ]) {
      expect(screen.getByRole("group", { name })).toBeInTheDocument();
    }
  });
});

describe("what a field change does to the ticks", () => {
  it("clears the skills at work, keeps the rest, and says so", async () => {
    const user = await openForm();
    const field = screen.getByLabelText("Your field");

    await user.selectOptions(field, "law");
    await user.click(pill("CV review"));
    await user.click(pill("Goal setting"));
    await user.click(pill("Legal research"));
    await user.click(pill("Case analysis"));

    expect(pill("Legal research")).toBeChecked();

    await user.selectOptions(field, "engineering");

    // Read by role as well as by its words: the note is announced rather
    // than only drawn, so a mentor who cannot see the pills clear is told.
    const note = screen.getByText(WORK_SKILLS_RESET_NOTE);
    expect(note).toHaveAttribute("role", "status");
    expect(pill("CV review")).toBeChecked();
    expect(pill("Goal setting")).toBeChecked();
    for (const label of Object.values(FIELD_WORK_SKILLS.engineering)) {
      expect(pill(label), label).not.toBeChecked();
    }
  });

  it("says nothing when there was no skill at work to clear", async () => {
    const user = await openForm();
    const field = screen.getByLabelText("Your field");

    await user.selectOptions(field, "law");
    await user.click(pill("CV review"));
    await user.selectOptions(field, "engineering");

    expect(screen.queryByText(WORK_SKILLS_RESET_NOTE)).toBeNull();
    expect(pill("CV review")).toBeChecked();
  });

  it("takes the note away again once the mentor ticks something", async () => {
    const user = await openForm();
    const field = screen.getByLabelText("Your field");

    await user.selectOptions(field, "law");
    await user.click(pill("Legal research"));
    await user.selectOptions(field, "engineering");
    expect(screen.getByText(WORK_SKILLS_RESET_NOTE)).toBeInTheDocument();

    await user.click(pill("Site supervision"));

    expect(screen.queryByText(WORK_SKILLS_RESET_NOTE)).toBeNull();
  });
});

describe("what the label swap does to the request", () => {
  /** Tick some pills in one field and read what /preview was asked. */
  async function askedFor(field: string, labels: string[]) {
    previewed.length = 0;
    const user = await openForm();

    await user.selectOptions(screen.getByLabelText("Your field"), field);
    for (const label of labels) {
      await user.click(pill(label));
    }

    await settlePreview();
    await waitFor(() => expect(previewed.length).toBeGreaterThan(0));
    return previewed[previewed.length - 1];
  }

  it("sends the same skill ids whatever the labels say", async () => {
    // Slots work_1, work_7 and work_10, read under two different fields.
    const fromLaw = await askedFor("law", [
      "Legal research",
      "Case analysis",
      "Compliance review",
    ]);
    const fromEngineering = await askedFor("engineering", [
      "Site supervision",
      "Quality assurance",
      "Commissioning and testing",
    ]);

    const expected = ["leadership", "mentoring_skills", "technical_skills_coaching"];
    expect([...fromLaw.skills].sort()).toEqual([...expected].sort());
    expect([...fromEngineering.skills].sort()).toEqual([...expected].sort());
    expect(fromLaw.skills).toEqual(fromEngineering.skills);
    expect(fromLaw.max_mentees).toBe(fromEngineering.max_mentees);
  });

  it("counts the same number of skills in both fields", async () => {
    const fromLaw = await askedFor("law", ["Legal research", "Matter management"]);
    const fromMedicine = await askedFor("medicine_health", [
      "Clinical reasoning",
      "Ward handover",
    ]);

    expect(fromLaw.skills).toHaveLength(2);
    expect(fromMedicine.skills).toHaveLength(2);
    expect(fromLaw.skills).toEqual(fromMedicine.skills);
  });

  it("asks again after a field change, with the cleared skills", async () => {
    const user = await openForm();
    const field = screen.getByLabelText("Your field");

    await user.selectOptions(field, "law");
    await user.click(pill("CV review"));
    await user.click(pill("Legal research"));
    await settlePreview();
    await waitFor(() => expect(previewed.length).toBeGreaterThan(0));
    expect(previewed[previewed.length - 1].skills).toContain("leadership");

    await user.selectOptions(field, "engineering");
    await settlePreview();
    await waitFor(() =>
      expect(previewed[previewed.length - 1].field).toBe("engineering"),
    );

    const last = previewed[previewed.length - 1];
    expect(last.skills).toEqual(["cv_review"]);
    // And the panel still shows a figure, so the preview did not stall.
    expect(screen.getByText(/One to one session: \$/)).toBeInTheDocument();
  });
});
