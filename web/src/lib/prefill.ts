/**
 * What the add-a-service form opens with.
 *
 * A mentor adding a second service has already described one, and almost
 * every answer they are about to give is the answer they gave last time. So
 * the form starts from their most recent service and they change what
 * differs, rather than filling the same three answers again.
 *
 * Here rather than in the page, so the two rules can be tested as rules:
 * which service is read, and what happens when the value in it is outside
 * what the API will accept.
 */

import type { Service } from "./api-types";

/**
 * The service this form starts from: the last one the mentor described.
 *
 * Services arrive oldest first, so the newest is the end of the list. The
 * newest rather than the first: a mentor who has moved from one to one
 * sessions to groups of six would otherwise be handed the one to one they
 * set up when they joined, every time they add a service.
 *
 * Nothing at all for a mentor with no service, which is only possible if
 * they deleted the one registration made for them.
 */
export function mostRecentService(services: Service[]): Service | null {
  return services.length > 0 ? services[services.length - 1] : null;
}

/**
 * The group size the picker opens on.
 *
 * Held inside what the API says it will accept, because the prefill comes
 * from a stored row and the bounds come from the options list. A stepper
 * opening outside its own range would start on a value it then refuses to
 * return to.
 */
export function startingGroupSize(
  existing: Service | null,
  bounds: { min: number; max: number },
): number {
  const found = existing?.max_mentees;
  if (typeof found !== "number" || !Number.isFinite(found)) {
    return bounds.min;
  }
  return Math.min(Math.max(Math.round(found), bounds.min), bounds.max);
}
