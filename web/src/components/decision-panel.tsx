"use client";

/**
 * The three answers a mentor can give one suggestion.
 *
 * Accept takes the advised price. Change takes a price the mentor names
 * instead, which has to be a different number, or accepting is what they
 * meant. Decline takes no price, or the price they charge anyway, which is
 * the most useful thing they could say while turning the advice down.
 *
 * Declining is reversible, so it is a quiet pill and not a red one, and the
 * solid primary is the one action that is neither destructive nor final.
 *
 * The same rules are enforced by the API. They are repeated here so a mentor
 * is told before a request rather than after one, and the API's own message
 * is shown whenever it refuses anyway.
 */

import { useRef, useState } from "react";

import { TextInput } from "@/components/form";
import { Button } from "@/components/ui";
import { api } from "@/lib/api-client";
import type { DecisionAction, Recommendation } from "@/lib/api-types";
import { ApiError, messageFor } from "@/lib/errors";
import { formatMoney } from "@/lib/format";

export function DecisionPanel({
  recommendation,
  onDecided,
}: {
  recommendation: Recommendation;
  onDecided: () => void;
}) {
  const [ownPrice, setOwnPrice] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [sending, setSending] = useState<DecisionAction | null>(null);
  const priceRef = useRef<HTMLInputElement>(null);

  const advised = recommendation.recommended_price;

  function namedPrice(): number | null {
    const trimmed = ownPrice.trim();
    if (!trimmed) {
      return null;
    }
    const parsed = Number(trimmed);
    return Number.isFinite(parsed) ? Math.round(parsed) : Number.NaN;
  }

  async function answer(action: DecisionAction) {
    setProblem(null);
    setFailure(null);
    const price = namedPrice();

    if (price !== null && Number.isNaN(price)) {
      setProblem("Give your own price as a whole number of dollars.");
      priceRef.current?.focus();
      return;
    }

    if (action === "modified") {
      if (price === null) {
        setProblem("Say what you will charge instead of the advised price.");
        priceRef.current?.focus();
        return;
      }
      if (price === advised) {
        setProblem(
          `That is the advised price. Accept the advice instead of changing it to the same ${formatMoney(advised)}.`,
        );
        priceRef.current?.focus();
        return;
      }
    }

    setSending(action);
    try {
      await api.decide(recommendation.id, {
        action,
        // Accepting means taking the advised price, so a number typed in the
        // field below is not sent with it.
        final_price: action === "accepted" ? null : price,
      });
      onDecided();
    } catch (error) {
      if (error instanceof ApiError && error.fieldErrors.length > 0) {
        setProblem(error.fieldErrors[0].message);
      } else {
        setFailure(messageFor(error));
      }
      setSending(null);
    }
  }

  return (
    <div>
      <div className="mt-6 flex flex-wrap gap-2">
        <Button
          className="grow mid:grow-0"
          disabled={sending !== null}
          aria-busy={sending === "accepted"}
          onClick={() => answer("accepted")}
        >
          {sending === "accepted" ? "Saving" : `Accept ${formatMoney(advised)}`}
        </Button>
        <Button
          variant="quiet"
          className="grow mid:grow-0"
          disabled={sending !== null}
          aria-busy={sending === "modified"}
          onClick={() => answer("modified")}
        >
          {sending === "modified" ? "Saving" : "Change"}
        </Button>
        <Button
          variant="quiet"
          className="grow mid:grow-0"
          disabled={sending !== null}
          aria-busy={sending === "rejected"}
          onClick={() => answer("rejected")}
        >
          {sending === "rejected" ? "Saving" : "Decline"}
        </Button>
      </div>

      <TextInput
        ref={priceRef}
        id="own-price"
        label="Or set your own price (AUD)"
        helper="Fill this in, then choose Change. You can also decline and leave it blank."
        inputMode="numeric"
        placeholder="e.g. 230"
        value={ownPrice}
        onChange={(event) => setOwnPrice(event.target.value)}
        error={problem}
      />

      {failure ? (
        <p
          role="alert"
          className="rounded-field bg-danger-fill px-3.5 py-3 text-small text-danger-700"
        >
          {failure}
        </p>
      ) : null}
    </div>
  );
}
