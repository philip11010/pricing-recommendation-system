/**
 * The live preview waits before it asks.
 *
 * Without this, moving the group size from one to eight would be seven
 * requests for a figure nobody read, and the answers could land out of order
 * so the panel ended on the wrong one. What is tested is the waiting itself:
 * that nothing changes before the delay, that a change during the wait
 * restarts it rather than queueing a second one, and that the last value is
 * the one that settles.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PREVIEW_DEBOUNCE_MS, useDebouncedValue } from "@/lib/use-debounced";

describe("useDebouncedValue", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("waits four hundred milliseconds by default", () => {
    expect(PREVIEW_DEBOUNCE_MS).toBe(400);
  });

  it("gives the first value straight away", () => {
    const { result } = renderHook(() => useDebouncedValue("technology_software|1|"));

    expect(result.current).toBe("technology_software|1|");
  });

  it("holds the old value until the wait is over", () => {
    const { result, rerender } = renderHook(({ value }) => useDebouncedValue(value), {
      initialProps: { value: "a" },
    });

    rerender({ value: "b" });
    expect(result.current).toBe("a");

    act(() => {
      vi.advanceTimersByTime(PREVIEW_DEBOUNCE_MS - 1);
    });
    expect(result.current).toBe("a");

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current).toBe("b");
  });

  it("settles once on the last value when the answers keep changing", () => {
    const { result, rerender } = renderHook(({ value }) => useDebouncedValue(value), {
      initialProps: { value: "1" },
    });

    for (const value of ["2", "3", "4", "5"]) {
      act(() => {
        vi.advanceTimersByTime(100);
      });
      rerender({ value });
    }

    // Four presses in four hundred milliseconds, and nothing has settled yet.
    expect(result.current).toBe("1");

    act(() => {
      vi.advanceTimersByTime(PREVIEW_DEBOUNCE_MS);
    });
    expect(result.current).toBe("5");
  });

  it("takes the delay it is given", () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebouncedValue(value, 50),
      { initialProps: { value: "a" } },
    );

    rerender({ value: "b" });
    act(() => {
      vi.advanceTimersByTime(50);
    });

    expect(result.current).toBe("b");
  });
});
