"use client";

/**
 * Who is signed in, as a page asks it.
 *
 * The token lives in `token.ts`; this is the mentor behind it. The record is
 * fetched once per page load and kept in a module level cache, because the
 * header, a route guard and the page itself all ask the same question and
 * three requests for one answer is three chances to disagree.
 *
 * Signing in and registering both hand the mentor straight to `setMentor`, so
 * the screen after them does not wait on a request whose answer it was
 * already given.
 */

import { useCallback, useEffect, useState } from "react";

import { api } from "./api-client";
import type { Mentor } from "./api-types";
import { SESSION_CHANGED_EVENT, clearToken, readToken } from "./token";

let cached: Mentor | null = null;
let inFlight: Promise<Mentor | null> | null = null;

function announce(): void {
  try {
    window.dispatchEvent(new Event(SESSION_CHANGED_EVENT));
  } catch {
    // No window to tell. Nothing is listening either.
  }
}

/** Remember the mentor a sign in or a registration just returned. */
export function setMentor(mentor: Mentor): void {
  cached = mentor;
  inFlight = null;
  announce();
}

/** Forget everything about the mentor, without touching the token. */
export function forgetMentor(): void {
  cached = null;
  inFlight = null;
}

/** The signed in mentor, fetched at most once while a page is open. */
export function loadMentor(): Promise<Mentor | null> {
  if (!readToken()) {
    cached = null;
    return Promise.resolve(null);
  }
  if (cached) {
    return Promise.resolve(cached);
  }
  if (!inFlight) {
    inFlight = api
      .me()
      .then((mentor) => {
        cached = mentor;
        return mentor;
      })
      .catch(() => null)
      .finally(() => {
        inFlight = null;
      });
  }
  return inFlight;
}

export interface Session {
  /** True until the first answer, so a guard does not redirect too early. */
  loading: boolean;
  mentor: Mentor | null;
  logout: () => void;
}

export function useSession(): Session {
  const [mentor, setLocalMentor] = useState<Mentor | null>(cached);
  const [loading, setLoading] = useState(cached === null);

  useEffect(() => {
    let live = true;

    const read = () => {
      if (!readToken()) {
        forgetMentor();
        if (live) {
          setLocalMentor(null);
          setLoading(false);
        }
        return;
      }
      setLoading(cached === null);
      void loadMentor().then((found) => {
        if (live) {
          setLocalMentor(found);
          setLoading(false);
        }
      });
    };

    read();
    window.addEventListener(SESSION_CHANGED_EVENT, read);
    return () => {
      live = false;
      window.removeEventListener(SESSION_CHANGED_EVENT, read);
    };
  }, []);

  const logout = useCallback(() => {
    forgetMentor();
    clearToken();
    window.location.assign("/");
  }, []);

  return { loading, mentor, logout };
}
