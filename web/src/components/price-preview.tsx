"use client";

/**
 * The price so far, while the form is still being filled in.
 *
 * It asks the API the same three questions registration asks, so the figure a
 * mentor watches while they type is the figure they are given when they
 * submit. Nothing is stored: there is no mentor yet to store it against.
 *
 * The panel is a white card on the gradient, which is the one place besides
 * the price hero where the two meet. It sticks beside the form on a wide
 * screen and sits below it on a phone, where a sticky panel would cover the
 * field being answered.
 */

import { useEffect, useState } from "react";

import { Overline } from "@/components/ui";
import { api } from "@/lib/api-client";
import type { PreviewResponse } from "@/lib/api-types";
import { PREVIEW_NOTE } from "@/lib/copy";
import { messageFor } from "@/lib/errors";
import { formatMoney } from "@/lib/format";
import { useDebouncedValue } from "@/lib/use-debounced";

type State =
  | { kind: "waiting" }
  | { kind: "loading" }
  | { kind: "ready"; price: PreviewResponse }
  | { kind: "error"; message: string };

export function PricePreview({
  field,
  maxMentees,
  skills,
  heading = "Your price so far",
}: {
  field: string;
  maxMentees: number;
  skills: string[];
  heading?: string;
}) {
  /**
   * The three answers as one string.
   *
   * A string rather than an object, because the debounced value is what the
   * request effect depends on, and a fresh object every render would restart
   * the wait on every render and never settle.
   */
  const key = [field, maxMentees, [...skills].sort().join(" ")].join("|");
  const settled = useDebouncedValue(key);
  const [state, setState] = useState<State>({ kind: "waiting" });

  // The group size the figure on screen was worked out for, which is not the
  // one in the form until the wait has settled.
  const pricedFor = Number.parseInt(settled.split("|")[1] ?? "1", 10) || 1;

  useEffect(() => {
    const [settledField, settledMentees, settledSkills] = settled.split("|");
    if (!settledField) {
      setState({ kind: "waiting" });
      return;
    }
    const controller = new AbortController();
    let live = true;
    setState({ kind: "loading" });

    api
      .preview(
        {
          field: settledField,
          max_mentees: Number.parseInt(settledMentees ?? "1", 10) || 1,
          skills: settledSkills ? settledSkills.split(" ") : [],
        },
        controller.signal,
      )
      .then((price) => {
        if (live) {
          setState({ kind: "ready", price });
        }
      })
      .catch((error: unknown) => {
        if (!live || (error instanceof DOMException && error.name === "AbortError")) {
          return;
        }
        setState({ kind: "error", message: messageFor(error) });
      });

    return () => {
      live = false;
      controller.abort();
    };
  }, [settled]);

  return (
    <div className="on-gradient rounded-card bg-hero p-5">
      <div className="on-surface rounded-card bg-surface p-6 text-ink-900">
        <Overline>{heading}</Overline>

        {/* A fixed minimum height, so the panel does not jump between the
            three states while a mentor is answering beside it. */}
        <div className="min-h-[132px]" aria-live="polite">
          {state.kind === "waiting" ? (
            <p className="mt-3 text-ink-700">
              Choose your field to see an early price here.
            </p>
          ) : null}

          {state.kind === "loading" ? (
            <p className="mt-3 flex items-center gap-2 text-ink-700">
              <span
                aria-hidden="true"
                className="h-4 w-4 animate-spin rounded-pill border-2 border-accent-100 border-t-accent-700"
              />
              Working out your price
            </p>
          ) : null}

          {state.kind === "error" ? (
            <p className="mt-3 text-ink-700">
              We could not work out a price just now. Your answers are safe, and the
              full suggestion comes on the next screen.
            </p>
          ) : null}

          {state.kind === "ready" ? (
            <>
              <p className="tabular mt-2.5 font-display text-figure">
                {formatMoney(state.price.per_person_price)}
                <span className="ml-2 text-base font-semibold tracking-normal text-ink-500">
                  per person
                </span>
              </p>
              <p className="tabular mt-1.5 font-medium text-ink-700">
                {pricedFor === 1
                  ? `One to one session: ${formatMoney(state.price.session_price)}`
                  : `Full session of ${pricedFor}: ${formatMoney(state.price.session_price)}`}
              </p>
              <p className="tabular mt-1 text-small text-ink-500">
                Usually between {formatMoney(state.price.range_low)} and{" "}
                {formatMoney(state.price.range_high)}
              </p>
            </>
          ) : null}
        </div>

        <p className="mt-3 text-small text-ink-500">{PREVIEW_NOTE}</p>
      </div>
    </div>
  );
}
