/**
 * The access token, and what happens when the API stops accepting it.
 *
 * One module reads and writes it, so signing in, signing out and being signed
 * out by the server are three things that happen in one place. Every read and
 * write is wrapped: storage throws rather than returning nothing in a private
 * window and when a browser has site data blocked, and a page that cannot
 * read a token should send the visitor to the log in screen, not break.
 *
 * There is no cookie. The token is sent in a header this application sets, so
 * a request a mentor did not start carries no credentials of its own.
 */

const STORAGE_KEY = "careerMentor.token";

/** Fired after the stored token changes, so a header can follow along. */
export const SESSION_CHANGED_EVENT = "pathwise:sessionchanged";

/** The query the log in page reads to decide whether to say anything. */
export const EXPIRED_QUERY = "expired";

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
    window.dispatchEvent(new Event(SESSION_CHANGED_EVENT));
  } catch {
    // Nothing to tell. The page that made the change already knows.
  }
}

/** The token this browser is signed in with, or null. */
export function readToken(): string | null {
  try {
    const raw = storage()?.getItem(STORAGE_KEY);
    return raw && raw.trim() ? raw : null;
  } catch {
    return null;
  }
}

export function writeToken(token: string): void {
  try {
    storage()?.setItem(STORAGE_KEY, token);
  } catch {
    // The token is lost when the page is left, which shows up as being asked
    // to log in again. Better than refusing to continue now.
  }
  announce();
}

export function clearToken(): void {
  try {
    storage()?.removeItem(STORAGE_KEY);
  } catch {
    // Nothing stored, nothing to clear.
  }
  announce();
}

/** True when this browser holds a token. Says nothing about it being valid. */
export function hasToken(): boolean {
  return readToken() !== null;
}

/**
 * The API refused the token, whatever page asked.
 *
 * The token is discarded first, so nothing retries with it, and the mentor is
 * sent to the log in screen with one short sentence rather than to a page
 * full of failed requests. Already being on that screen means the refusal was
 * the log in attempt itself, which the form reports for itself.
 */
export function handleUnauthorized(): void {
  clearToken();
  if (typeof window === "undefined") {
    return;
  }
  const path = window.location.pathname;
  if (path === "/login") {
    return;
  }
  window.location.assign(`/login?${EXPIRED_QUERY}=1`);
}
