"use client";

/**
 * A value that settles before anything acts on it.
 *
 * The live price preview asks the API for a number whenever an answer
 * changes. Without this, dragging the stepper from one to eight would be
 * seven requests for a figure nobody read, and the answers could arrive out
 * of order. Four hundred milliseconds is long enough to cover a run of
 * presses and short enough that the panel does not feel stuck.
 */

import { useEffect, useState } from "react";

export const PREVIEW_DEBOUNCE_MS = 400;

export function useDebouncedValue<T>(value: T, delay: number = PREVIEW_DEBOUNCE_MS): T {
  const [settled, setSettled] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return settled;
}
