/**
 * Where a mentor came from, carried in the address and checked on arrival.
 *
 * The similar mentors page is reached from two places and has to offer a way
 * back to the one the mentor actually used. Back to a fresh price would not
 * do: asking for a price again creates a new recommendation, so a mentor who
 * had gone off to look at the comparison would return to a different number
 * with the three answers still unanswered.
 *
 * So the link carries the origin. It is a query parameter rather than
 * anything stored, because that makes the back link part of the address: it
 * survives a reload, it can be shared, and it costs nothing when it is
 * absent.
 *
 * Nothing read out of the address is trusted. `from` has to be one of two
 * known words and the recommendation id has to be a positive whole number, or
 * the origin is discarded and the fallback is the mentor's own dashboard,
 * which every signed in mentor has. A link that said `from=recommendation`
 * with no id, or with somebody else's, would otherwise turn into a link to a
 * price screen that answers 404.
 */

export const FROM_QUERY = "from";
export const RECOMMENDATION_QUERY = "rec";

export const FROM_RECOMMENDATION = "recommendation";
export const FROM_DASHBOARD = "dashboard";

export const DASHBOARD_BACK_LABEL = "Back to your dashboard";
export const RECOMMENDATION_BACK_LABEL = "Back to your price";

export type OriginName = typeof FROM_RECOMMENDATION | typeof FROM_DASHBOARD;

export interface BackLink {
  href: string;
  label: string;
}

export interface OriginChoice {
  from: OriginName;
  /** Required when `from` is the price screen, ignored otherwise. */
  recommendationId?: number | null;
}

/** A positive whole number, or null for anything else at all. */
function wholeNumber(raw: string | null | undefined): number | null {
  if (!raw || !/^\d+$/.test(raw)) {
    return null;
  }
  const value = Number.parseInt(raw, 10);
  return Number.isSafeInteger(value) && value > 0 ? value : null;
}

/** The address of the similar mentors page, carrying where it was opened from. */
export function similarHref(serviceId: number, origin?: OriginChoice | null): string {
  const base = `/similar/${serviceId}`;
  if (!origin) {
    return base;
  }
  if (origin.from === FROM_RECOMMENDATION) {
    const id = origin.recommendationId;
    if (typeof id !== "number" || !Number.isSafeInteger(id) || id <= 0) {
      return base;
    }
    return `${base}?${FROM_QUERY}=${FROM_RECOMMENDATION}&${RECOMMENDATION_QUERY}=${id}`;
  }
  return `${base}?${FROM_QUERY}=${FROM_DASHBOARD}`;
}

/**
 * The way back, from whatever the address claims.
 *
 * Always a link, never nothing: a page with no way out is the fault this
 * exists to prevent, so an origin that cannot be read falls back to the
 * dashboard rather than to an absent link.
 */
export function backFromOrigin(
  from: string | null | undefined,
  recommendationId: string | null | undefined,
): BackLink {
  if (from === FROM_RECOMMENDATION) {
    const id = wholeNumber(recommendationId);
    if (id !== null) {
      return { href: `/recommendation/${id}`, label: RECOMMENDATION_BACK_LABEL };
    }
  }
  return { href: "/dashboard", label: DASHBOARD_BACK_LABEL };
}

/* ------------------------------------------------------------- directory */

export const FIELD_QUERY = "field";

/**
 * The directory, with a filter kept in the address.
 *
 * Same reasoning as the origin above, for the same kind of problem: a mentee
 * who filtered the directory to one field, opened a profile and came back
 * would otherwise be handed the unfiltered list and have to filter it again.
 * Putting the filter in the address also means the browser's own back button
 * returns to the filtered list, which is what a reader expects of it.
 */
export function directoryHref(field?: string | null): string {
  return field ? `/mentors?${FIELD_QUERY}=${encodeURIComponent(field)}` : "/mentors";
}

/** One mentor's public profile, keeping whatever filter the list was under. */
export function mentorHref(mentorId: number, field?: string | null): string {
  return field
    ? `/mentors/${mentorId}?${FIELD_QUERY}=${encodeURIComponent(field)}`
    : `/mentors/${mentorId}`;
}
