/**
 * Every skill the API publishes is on the form, under exactly one heading.
 *
 * The four headings and which skill belongs to which are the one part of the
 * skill list this application decides. That makes them the one part that can
 * drift: a skill added to the API with no heading here would simply not be
 * drawn, and nothing else would complain.
 *
 * PUBLISHED below is the list as /meta/options sends it. It is checked in
 * both directions, so a skill added to the API without a heading fails here,
 * and a heading naming a skill the API does not have fails here too. The end
 * to end suite checks the same thing against the running API, which is what
 * catches this fixture itself going stale.
 */

import { describe, expect, it } from "vitest";

import { GROUPED_SKILL_IDS, SKILL_GROUPS } from "@/lib/copy";

/** The thirty skill ids /meta/options publishes. */
const PUBLISHED = [
  "cv_review",
  "cover_letter_writing",
  "interview_preparation",
  "career_planning",
  "career_change",
  "salary_negotiation",
  "networking",
  "personal_branding",
  "linkedin_profile_review",
  "leadership",
  "public_speaking",
  "time_management",
  "project_management",
  "portfolio_review",
  "graduate_applications",
  "job_search_strategy",
  "workplace_communication",
  "conflict_resolution",
  "mentoring_skills",
  "presentation_skills",
  "data_analysis",
  "technical_skills_coaching",
  "entrepreneurship",
  "work_life_balance",
  "goal_setting",
  "performance_reviews",
  "promotion_planning",
  "remote_work",
  "further_studies_guidance",
  "professional_ethics",
];

describe("the four skill headings", () => {
  it("covers every skill the API publishes", () => {
    const missing = PUBLISHED.filter((id) => !GROUPED_SKILL_IDS.includes(id));

    expect(missing).toEqual([]);
  });

  it("names no skill the API does not publish", () => {
    const unknown = GROUPED_SKILL_IDS.filter((id) => !PUBLISHED.includes(id));

    expect(unknown).toEqual([]);
  });

  it("puts each skill under exactly one heading", () => {
    const seen = new Map<string, number>();
    for (const group of SKILL_GROUPS) {
      for (const id of group.skillIds) {
        seen.set(id, (seen.get(id) ?? 0) + 1);
      }
    }
    const repeated = [...seen.entries()].filter(([, count]) => count > 1);

    expect(repeated).toEqual([]);
    expect(seen.size).toBe(PUBLISHED.length);
  });

  it("shows all thirty, in the four named groups", () => {
    expect(GROUPED_SKILL_IDS).toHaveLength(30);
    expect(SKILL_GROUPS.map((group) => group.name)).toEqual([
      "Getting hired",
      "Growing your career",
      "Skills at work",
      "Business and balance",
    ]);
    expect(SKILL_GROUPS.map((group) => group.skillIds.length)).toEqual([7, 8, 10, 5]);
  });
});
