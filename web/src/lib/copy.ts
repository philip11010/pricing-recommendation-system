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

/* -------------------------------------------------------------------------
 * The About page.
 *
 * Kept here with the rest of the sentences the product says, because this
 * page is almost entirely claims: what the system does, what it was built
 * from, and how well it works. Each one has to be defensible, so they are
 * read and edited together rather than scattered through JSX.
 *
 * The figures in ABOUT_SCORE_ROWS are transcribed from the winning model for
 * each feature set in reports/model_results.json, rounded for a reader. They
 * are not estimates and they are not written from memory. Re-run the training
 * and these change with it.
 * ------------------------------------------------------------------------- */

export const ABOUT_TITLE = "About";

export const ABOUT_META_DESCRIPTION =
  "How Pathwise suggests a session price for a mentor: where the data came from, how the models were built and tested, how accurate they are, and what the suggestion does not claim.";

/** The anchor the hero's second button points at. */
export const ABOUT_HOW_IT_WORKS_ID = "how-it-works";

export const ABOUT_HERO = {
  title: "Pricing guidance you can understand, built on real market patterns.",
  lead: "We suggest a session price from what mentors like you charge, show the range around it, and say what the number rests on. You decide what to charge.",
  primary: { label: "Get your price", href: "/register" },
  secondary: { label: "See how it works", href: "#how-it-works" },
};

export const ABOUT_PROBLEM = {
  title: "Most mentors are guessing.",
  lead: "Setting a rate is one of the hardest parts of offering your time, and there is rarely anything solid to go on.",
  points: [
    {
      title: "Priced too high",
      body: "Nobody books, and you never find out that the number was the reason.",
      tint: "bg-tint-indigo",
    },
    {
      title: "Priced too low",
      body: "The sessions come in, and you undersell yourself on every one of them.",
      tint: "bg-tint-blue",
    },
    {
      title: "Nothing to lean on",
      body: "A new mentor has no record of past sessions, so the first price is a guess about a guess.",
      tint: "bg-tint-violet",
    },
  ],
};

export type AboutStepIcon = "profile" | "compare" | "decide";

export const ABOUT_HOW = {
  title: "How it works",
  lead: "Three steps, and the last one belongs to you.",
  steps: [
    {
      step: "Step 1",
      title: "Describe your profile and services",
      body: "Your field, how many people you mentor at once, and the skills you cover.",
      icon: "profile" as AboutStepIcon,
      tint: "bg-tint-indigo",
    },
    {
      step: "Step 2",
      title: "We compare you and estimate a rate",
      body: "We look at mentors whose profile and services resemble yours, and work out what a session like yours is worth.",
      icon: "compare" as AboutStepIcon,
      tint: "bg-tint-blue",
    },
    {
      step: "Step 3",
      title: "You see the price, the range and the reasons",
      body: "The number, the range around it, and what pushed it up or down. You decide, we recommend.",
      icon: "decide" as AboutStepIcon,
      tint: "bg-tint-violet",
    },
  ],
};

export const ABOUT_DATA = {
  title: "Where the data came from",
  paragraphs: [
    "Mentorship platforms do not publish what their mentors charge. There was no public set of real mentorship prices to learn from, and saying otherwise would be the easiest thing on this page to get wrong.",
    "So the system was trained on a large public dataset of service listings from Sydney, Australia, used as a structural stand-in. Each listing carries a price, a category, a group size, a session length, a track record and reviews, which is the same shape as a mentorship service.",
    "That is a claim about structure and nothing more. It is not a claim that the two markets behave alike, and no number on this page should be read as one.",
    "Training on the platform's own booking data is the intended next step, once there is enough of it. Until then, prices are shown in the currency the models were trained in, Australian dollars.",
  ],
};

export const ABOUT_BUILD = {
  title: "How it was built",
  lead: "Five things worth knowing, in the order they happened.",
  points: [
    "The models learned from thousands of listings which details go with a higher price and which go with a lower one.",
    "There are two of them. A core model reads eight profile details, so a mentor with no history can still be given a price. A fuller model adds the mentor's own track record, more than thirty details in all, for mentors who already have bookings and reviews.",
    "Both were tested on listings they had never seen. Whole hosts were held out of training, so no host appears in both the training set and the test set and one provider's pricing habits cannot leak across the line.",
    "Sensible rules sit on top of the models. A price stays inside a realistic range, and adding more skills never lowers it.",
    "Every price arrives with its reasons. The estimate is broken into factors such as field, group size, skills and track record, and shown beside a comparison with similar mentors.",
  ],
  curious:
    "For the curious: both models are gradient-boosted decision trees, built with XGBoost.",
};

export interface AboutScoreModel {
  key: "core" | "full";
  name: string;
  note: string;
}

export const ABOUT_SCORE_MODELS: AboutScoreModel[] = [
  {
    key: "core",
    name: "Core model",
    note: "Eight profile details. This is the one that prices a brand new mentor.",
  },
  {
    key: "full",
    name: "Full model",
    note: "The same details plus the mentor's own track record, for mentors who have one.",
  },
];

export interface AboutScoreRow {
  label: string;
  scale: string;
  core: string;
  full: string;
}

/**
 * Read from reports/model_results.json, winners.core and winners.full, which
 * are both the XGBoost runs. Everything below the first row is an error
 * measure, so lower is better. R-squared is the exception.
 */
export const ABOUT_SCORE_ROWS: AboutScoreRow[] = [
  {
    label: "R-squared",
    scale: "Share of the price differences explained, from 0 to 1. Higher is better.",
    core: "0.544",
    full: "0.625",
  },
  {
    label: "Log RMSE",
    scale: "Typical error on the log price scale, not in money.",
    core: "0.362",
    full: "0.323",
  },
  {
    label: "MAE",
    scale: "Average size of the error, in Australian dollars.",
    core: "$120",
    full: "$107",
  },
  {
    label: "RMSE",
    scale: "Typical error with the large misses weighted more, in Australian dollars.",
    core: "$192",
    full: "$174",
  },
  {
    label: "Cross-validation log RMSE",
    scale:
      "The same log price scale, averaged over ten folds of the training data rather than measured on the test set.",
    core: "0.331",
    full: "0.304",
  },
];

export const ABOUT_ACCURACY = {
  title: "How accurate is it",
  lead: "Both models were scored on a held-out test set of listings neither of them had seen. The first four rows are that test set. The last row is the cross-validation on the training data.",
  verdict:
    "The models explain a meaningful share of the differences in price, but not all of them. The full model is more accurate than the core model on every measure here.",
  limitTitle: "What this does not claim.",
  limit:
    "These scores say how closely the models matched prices in the data they were trained and tested on. They are not a measure of how well a price works on a mentorship platform, and they are not a promise about any single mentor's price.",
};

export const ABOUT_LIMITS = {
  title: "What it does not do",
  points: [
    {
      title: "It does not price your experience or your credentials",
      body: "The data showed no reliable link between those and what a service charges, so they stay on your public profile and are kept out of the models.",
    },
    {
      title: "It gives guidance, not guarantees",
      body: "A suggestion is a starting point for your own decision. It is not a rate anyone owes you, and it is not a forecast of what you will earn.",
    },
    {
      title: "It does not yet report how prices move with demand",
      body: "That evidence is still being measured. Until it is in, the system makes no claim about raising or lowering a price as demand moves.",
    },
  ],
};

export const ABOUT_CLOSING = {
  title: "Get a price you can explain.",
  lead: "Four short questions, and you can change the answer or ignore it.",
  primary: { label: "Get your price", href: "/register" },
  secondary: { label: "Create an account", href: "/register" },
};

/* -------------------------------------------------------------------------
 * The footer.
 *
 * The link columns are data rather than markup so that the footer, the tests
 * and this file cannot disagree about where a link goes.
 * ------------------------------------------------------------------------- */

export interface FooterLink {
  label: string;
  href: string;
}

export interface FooterColumn {
  title: string;
  links: FooterLink[];
}

export const FOOTER_COLUMNS: FooterColumn[] = [
  {
    title: "Product",
    links: [
      { label: "Get your price", href: "/register" },
      { label: "How it works", href: "/about#how-it-works" },
      { label: "About", href: "/about" },
    ],
  },
  {
    title: "Mentors",
    links: [
      { label: "Browse mentors", href: "/mentors" },
      { label: "For mentors dashboard", href: "/dashboard" },
    ],
  },
  {
    title: "Account",
    links: [
      { label: "Log in", href: "/login" },
      { label: "Register", href: "/register" },
    ],
  },
];

export const FOOTER_CTA: FooterLink = { label: "Get your price", href: "/register" };

/** The line in the thin bar at the very bottom, beside the copyright. */
export const FOOTER_PROJECT_LINE = "A final-year university project";

/** No name in it, by rule. The year is read from the clock, not written down. */
export function copyrightLine(year: number): string {
  return `\u00A9 ${year} ${BRAND}`;
}
