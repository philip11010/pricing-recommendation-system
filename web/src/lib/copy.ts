/**
 * The sentences this application says about a price.
 *
 * Kept together because they are the part of the interface that has to be got
 * right rather than merely built. Each one is a claim about what the system
 * does, and the system is advisory: it suggests, the mentor decides, and no
 * sentence here may imply otherwise.
 */

import type { RangePosition } from "./api-types";

export const BRAND = "Career Mentor";

export const ADVISORY_LINE =
  "This is a suggestion, not a decision. You can accept it, change it or decline it.";

/**
 * Shown on a price worked out from the registration form alone.
 *
 * The API marks these `low_confidence`. Saying so plainly is the point: a
 * mentor who is told a number with no caveat will read it as a measurement.
 */
export const LOW_CONFIDENCE_NOTE =
  "This is a first estimate from the details you gave us. It gets sharper as you build a record of completed sessions and ratings.";

/** Shown on a price worked out with the mentor's own track record. */
export const WITH_HISTORY_NOTE =
  "This suggestion also reflects your ratings and booking history, so it can differ from the middle of the group below.";

/** The three things a current price can be, against the suggested range. */
export const POSITION_MESSAGES: Record<RangePosition, string> = {
  within: "Your price is in line with similar mentors.",
  above:
    "Your price is above the suggested range. Check that your ratings and demand support it.",
  below: "Your price is below the suggested range. You may have room to raise it.",
};

export const POSITION_HEADINGS: Record<RangePosition, string> = {
  within: "In line with similar mentors",
  above: "Above the suggested range",
  below: "Below the suggested range",
};

/** What the three stored actions are called where a mentor can see them. */
export const DECISION_WORDS: Record<string, string> = {
  accepted: "Accepted",
  modified: "Modified",
  rejected: "Declined",
  pending: "Pending",
};

export function decisionWord(status: string | null | undefined): string {
  if (!status) {
    return DECISION_WORDS.pending ?? "Pending";
  }
  return DECISION_WORDS[status] ?? "Pending";
}

/**
 * How widely the system had to look to find comparable mentors.
 *
 * The API sends both a level and a description. The description is what is
 * shown; this is for the one extra sentence that a widened match deserves.
 */
export const WIDENED_NOTE =
  "We found fewer mentors like you than we would like, so treat these figures as a guide rather than a settled market rate.";

export const NO_COMPARABLES_NOTE =
  "We do not have enough mentors like you to compare with yet. Your suggestion still stands on its own.";

export const COMPARABLES_UNAVAILABLE_NOTE =
  "The comparison with similar mentors is not available on this server.";

export const NO_PRICE_SET =
  "You have not set a price for this service yet, so there is nothing to compare the suggestion against.";
