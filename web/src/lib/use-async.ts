"use client";

/**
 * One request, and the three things a page has to show about it.
 *
 * Every page here loads from the API in the browser, and every one of them
 * needs the same three states: loading, loaded, and failed with something to
 * read. Writing that out per page produced three subtly different versions of
 * it, so it lives here once.
 *
 * The request is aborted when the page moves on, which matters on the
 * comparable mentors list, where changing the sort while a page is in flight
 * would otherwise let the old answer land on top of the new one.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type AsyncStatus = "loading" | "ready" | "error";

export interface AsyncState<T> {
  status: AsyncStatus;
  data: T | null;
  error: unknown;
}

export interface AsyncResult<T> extends AsyncState<T> {
  /** Run the request again, for a retry button or after a change. */
  reload: () => void;
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

/**
 * Run `loader` now, and again whenever `key` changes.
 *
 * `key` rather than a dependency array: every caller's dependencies are a
 * handful of ids and query values, and a string of them is both easier to
 * read at the call site and immune to the array changing length.
 */
export function useAsync<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  key: string,
): AsyncResult<T> {
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const [state, setState] = useState<AsyncState<T>>({
    status: "loading",
    data: null,
    error: null,
  });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let live = true;
    setState({ status: "loading", data: null, error: null });

    loaderRef
      .current(controller.signal)
      .then((data) => {
        if (live) {
          setState({ status: "ready", data, error: null });
        }
      })
      .catch((error: unknown) => {
        if (!live || isAbort(error)) {
          return;
        }
        setState({ status: "error", data: null, error });
      });

    return () => {
      live = false;
      controller.abort();
    };
  }, [key, attempt]);

  const reload = useCallback(() => setAttempt((count) => count + 1), []);

  return { ...state, reload };
}
