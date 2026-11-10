/**
 * Which mentor this browser is acting as.
 *
 * There is no authentication yet, so there is no session to speak of: the
 * mentor's id is kept in this browser and sent on every mentor-scoped
 * request. That is a placeholder, and it is confined to this module so that
 * replacing it with a real sign-in touches one file.
 *
 * Every read and write is wrapped. Storage throws rather than returning
 * nothing in a private window and when a browser has site data blocked, and a
 * page that cannot read an id should send the visitor to the start, not break.
 */

const STORAGE_KEY = "careerMentor.mentorId";

// The mentor's name, kept beside the id so the header can greet them without
// a request of its own. A convenience, never the source of anything: the name
// shown on a page comes from the record that page loaded.
const NAME_KEY = "careerMentor.mentorName";

/** Fired after the stored id changes, so a header can follow along. */
export const MENTOR_CHANGED_EVENT = "careermentor:mentorchanged";

function storage(): Storage | null {
  try {
    if (typeof window === "undefined") {
      return null;
    }
    return window.localStorage;
  } catch {
    return null;
  }
}

function announce(): void {
  try {
    window.dispatchEvent(new Event(MENTOR_CHANGED_EVENT));
  } catch {
    // Nothing to tell. The page that made the change already knows.
  }
}

/** The mentor this browser is acting as, or null if none has been chosen. */
export function readMentorId(): number | null {
  try {
    const raw = storage()?.getItem(STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = Number.parseInt(raw, 10);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
  } catch {
    return null;
  }
}

export function writeMentorId(mentorId: number, name?: string | null): void {
  try {
    storage()?.setItem(STORAGE_KEY, String(mentorId));
    if (name) {
      storage()?.setItem(NAME_KEY, name);
    } else {
      storage()?.removeItem(NAME_KEY);
    }
  } catch {
    // The id is lost when the page is left, which shows up as being sent
    // back to the start. Better than refusing to continue now.
  }
  announce();
}

/** The name to greet this mentor by, if one was stored with their id. */
export function readMentorName(): string | null {
  try {
    const raw = storage()?.getItem(NAME_KEY);
    return raw && raw.trim() ? raw : null;
  } catch {
    return null;
  }
}

export function clearMentorId(): void {
  try {
    storage()?.removeItem(STORAGE_KEY);
    storage()?.removeItem(NAME_KEY);
  } catch {
    // Nothing stored, nothing to clear.
  }
  announce();
}
