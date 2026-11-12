/**
 * The sentences this application says, and the one place the product is named.
 *
 * Kept together because they are the part of the interface that has to be got
 * right rather than merely built. Each one is a claim about what the system
 * does, and the system is advisory: it suggests, the mentor decides, and no
 * sentence here may imply otherwise.
 */

/** The product name. Written once, so renaming is one edit. */
export const BRAND = "Pathwise";

export const TAGLINE =
  "Suggested session prices for mentors, based on what mentors like you charge. The suggestion is advice: you decide what to charge.";

export const FOOTER_LINE =
  "Prices are suggestions in Australian dollars. The final price is always yours.";

export const ADVISORY_LINE =
  "This is advice, not a rule. Mentors like you usually charge close to this, and you decide the final price.";

/**
 * Shown on a price worked out from the registration form alone.
 *
 * The API marks these `low_confidence`. Saying so plainly is the point: a
 * mentor who is told a number with no caveat will read it as a measurement.
 */
export const LOW_CONFIDENCE_TITLE = "Early estimate.";

export const LOW_CONFIDENCE_NOTE =
  "You have no session history yet, so this range is wider. It sharpens as you build a record of completed sessions and reviews.";

/** Shown on a price worked out with the mentor's own track record. */
export const WITH_HISTORY_NOTE =
  "This suggestion also reflects your reviews and how busy you have been, so it can differ from the middle of the group below.";

export const PREVIEW_NOTE =
  "Early numbers. They update as you change your answers. The full suggestion comes on the next screen.";

export const UNVERIFIED_AFTER_SUBMIT =
  "New profiles start as not verified. A check mark appears once your details are confirmed.";

export const VERIFIED_LABEL = "Verified";
export const UNVERIFIED_LABEL = "New, not verified yet";

export const SESSION_EXPIRED = "Please log in again";

export const LOGIN_FAILED = "That email address and password do not match an account.";

/** What the three stored actions are called where a mentor can see them. */
export const DECISION_WORDS: Record<string, string> = {
  accepted: "Accepted",
  modified: "Modified",
  rejected: "Declined",
  pending: "Pending",
};

export function decisionWord(status: string | null | undefined): string {
  if (!status) {
    return DECISION_WORDS.pending;
  }
  return DECISION_WORDS[status] ?? DECISION_WORDS.pending;
}

export const WIDENED_NOTE =
  "We found fewer mentors like you than we would like, so treat these figures as a guide rather than a settled market rate.";

export const NO_COMPARABLES_NOTE =
  "We do not have enough mentors like you to compare with yet. Your suggestion still stands on its own.";

export const COMPARABLES_UNAVAILABLE_NOTE =
  "The comparison with similar mentors is not available on this server.";

export const NO_PRICE_SET =
  "You have not set a price for this service yet, so there is nothing to compare the suggestion against.";

/**
 * The four headings the thirty skills are read under.
 *
 * The group names and which skill belongs to which are the only part of the
 * skill list this application decides. The skills themselves come from
 * /meta/options, and a test checks that every id the API publishes appears
 * here exactly once, so a skill added to the API cannot go missing from the
 * form.
 */
export interface SkillGroup {
  name: string;
  skillIds: string[];
}

export const SKILL_GROUPS: SkillGroup[] = [
  {
    name: "Getting hired",
    skillIds: [
      "cv_review",
      "cover_letter_writing",
      "interview_preparation",
      "linkedin_profile_review",
      "portfolio_review",
      "graduate_applications",
      "job_search_strategy",
    ],
  },
  {
    name: "Growing your career",
    skillIds: [
      "career_planning",
      "career_change",
      "salary_negotiation",
      "promotion_planning",
      "performance_reviews",
      "personal_branding",
      "further_studies_guidance",
      "networking",
    ],
  },
  {
    name: "Skills at work",
    skillIds: [
      "leadership",
      "public_speaking",
      "time_management",
      "project_management",
      "workplace_communication",
      "conflict_resolution",
      "mentoring_skills",
      "presentation_skills",
      "data_analysis",
      "technical_skills_coaching",
    ],
  },
  {
    name: "Business and balance",
    skillIds: [
      "entrepreneurship",
      "work_life_balance",
      "goal_setting",
      "remote_work",
      "professional_ethics",
    ],
  },
];

/** Every skill id this application has a group for, as a flat set. */
export const GROUPED_SKILL_IDS: string[] = SKILL_GROUPS.flatMap(
  (group) => group.skillIds,
);
