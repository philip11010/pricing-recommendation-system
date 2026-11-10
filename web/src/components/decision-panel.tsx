"use client";

/**
 * What the mentor does about the price.
 *
 * This is the part the rest of the system is advisory for. Up to here nothing
 * has set a price: the mentor accepts the suggestion, charges something else,
 * or declines it, and whatever they settle on is what their service charges.
 *
 * Three things it is careful about:
 *
 * * The buttons are disabled while a decision is in flight. A price is
 *   answered once, and a second click would be refused by the API with a
 *   message about having already decided, which is a confusing thing to be
 *   told about your own double click.
 * * A modification equal to the suggestion is caught here with a sentence
 *   saying to accept it instead, which is the same thing the API says.
 * * Declining does not demand a number. A mentor who wants to think about it
 *   can say so, and the service keeps charging whatever it charged.
 */

import Link from "next/link";
import { useState } from "react";

import { api } from "@/lib/api-client";
import type { Decision, DecisionAction, Recommendation } from "@/lib/api-types";
import { decisionWord } from "@/lib/copy";
import { ApiError, isAlreadyDecided, messageFor } from "@/lib/errors";
import { formatMoney } from "@/lib/format";

import { TextInput } from "./form";
import { Button, Callout } from "./ui";

const PRICE_MIN = 1;
const PRICE_MAX = 5000;

type Mode = "choose" | "modify" | "decline" | "decline-price";

function validatePrice(raw: string, suggested: number, mustDiffer: boolean) {
  const trimmed = raw.trim();
  if (!trimmed) {
    return "Enter the price you want to charge.";
  }
  if (!/^\d+$/.test(trimmed)) {
    return `Enter a whole number of dollars, between ${PRICE_MIN} and ${PRICE_MAX}.`;
  }
  const value = Number.parseInt(trimmed, 10);
  if (value < PRICE_MIN || value > PRICE_MAX) {
    return `The price has to be between ${formatMoney(PRICE_MIN)} and ${formatMoney(
      PRICE_MAX,
    )}.`;
  }
  if (mustDiffer && value === suggested) {
    return "That is the suggested price. Accept it instead.";
  }
  return null;
}

export function DecisionPanel({
  mentorId,
  recommendation,
  existingDecision,
  onDecided,
}: {
  mentorId: number;
  recommendation: Recommendation;
  /** The answer already on record, if this price has been answered. */
  existingDecision?: Decision | null;
  onDecided: (decision: Decision) => void;
}) {
  const [mode, setMode] = useState<Mode>("choose");
  const [price, setPrice] = useState("");
  const [priceError, setPriceError] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState<Decision | null>(existingDecision ?? null);
  const [alreadyAnswered, setAlreadyAnswered] = useState(
    recommendation.status !== "pending" && !existingDecision,
  );

  async function send(action: DecisionAction, finalPrice?: number) {
    setSending(true);
    setFailure(null);
    try {
      const decision = await api.decide(mentorId, recommendation.id, {
        action,
        ...(finalPrice === undefined ? {} : { final_price: finalPrice }),
      });
      setDone(decision);
      onDecided(decision);
    } catch (error) {
      if (isAlreadyDecided(error)) {
        setAlreadyAnswered(true);
      } else if (error instanceof ApiError && error.fieldErrors.length > 0) {
        const named = error.fieldErrors.find((item) => item.field === "final_price");
        if (named) {
          setPriceError(named.message);
        } else {
          setFailure(error.detail);
        }
      } else {
        setFailure(messageFor(error));
      }
    } finally {
      setSending(false);
    }
  }

  function submitPrice(action: DecisionAction, mustDiffer: boolean) {
    const problem = validatePrice(price, recommendation.recommended_price, mustDiffer);
    setPriceError(problem);
    if (problem) {
      return;
    }
    void send(action, Number.parseInt(price.trim(), 10));
  }

  if (done) {
    const word = decisionWord(done.action);
    return (
      <div className="rounded-xl2 border border-accent-200 bg-accent-50 p-5 sm:p-6">
        <h3 className="text-lg font-semibold text-accent-900">
          {word}
          {done.final_price !== null
            ? `, at ${formatMoney(done.final_price)} a session`
            : ""}
        </h3>
        <p className="mt-2 text-sm leading-relaxed text-accent-900">
          {done.action === "accepted"
            ? "Your service now charges the suggested price. You can ask for a fresh suggestion whenever you like."
            : null}
          {done.action === "modified"
            ? "Your service now charges the price you set. We have kept the suggestion beside it, so you can see how the two compare over time."
            : null}
          {done.action === "rejected" && done.final_price !== null
            ? "Your service now charges the price you set. We have recorded that you declined the suggestion."
            : null}
          {done.action === "rejected" && done.final_price === null
            ? "We have recorded that you declined this suggestion, and your service charges what it charged before. Ask for a fresh suggestion when you are ready."
            : null}
        </p>
        <div className="mt-4">
          <Link
            href="/dashboard"
            className="inline-flex min-h-[44px] items-center rounded-xl bg-accent-700 px-5 font-semibold text-white hover:bg-accent-800"
          >
            Go to my page
          </Link>
        </div>
      </div>
    );
  }

  if (alreadyAnswered) {
    return (
      <Callout
        tone="notice"
        title={`Already answered: ${decisionWord(recommendation.status)}`}
      >
        You have already answered this suggestion. Ask for a fresh suggestion from your
        own page if you want to decide again.
        <div className="mt-3">
          <Link href="/dashboard" className="font-semibold underline">
            Go to my page
          </Link>
        </div>
      </Callout>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold">What would you like to do?</h3>
        <p className="mt-1 text-sm text-ink-muted">
          This suggestion is advice. Nothing is set until you answer it.
        </p>
      </div>

      {failure ? <Callout tone="caution">{failure}</Callout> : null}

      {mode === "choose" ? (
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => void send("accepted")} disabled={sending}>
            {sending
              ? "Saving"
              : `Accept ${formatMoney(recommendation.recommended_price)}`}
          </Button>
          <Button
            tone="secondary"
            onClick={() => {
              setPrice(String(recommendation.recommended_price));
              setPriceError(null);
              setMode("modify");
            }}
            disabled={sending}
          >
            Modify the price
          </Button>
          <Button tone="quiet" onClick={() => setMode("decline")} disabled={sending}>
            Decline
          </Button>
        </div>
      ) : null}

      {mode === "modify" ? (
        <div className="space-y-4 rounded-xl border border-line bg-shell p-4">
          <TextInput
            label="The price you want to charge, per session"
            value={price}
            onChange={(value) => {
              setPriceError(null);
              setPrice(value);
            }}
            error={priceError ?? undefined}
            hint={`A whole number of dollars, from ${formatMoney(PRICE_MIN)} to ${formatMoney(
              PRICE_MAX,
            )}. It has to differ from the suggested ${formatMoney(
              recommendation.recommended_price,
            )}.`}
          />
          <div className="flex flex-wrap gap-3">
            <Button onClick={() => submitPrice("modified", true)} disabled={sending}>
              {sending ? "Saving" : "Save my price"}
            </Button>
            <Button
              tone="quiet"
              onClick={() => {
                setPriceError(null);
                setMode("choose");
              }}
              disabled={sending}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : null}

      {mode === "decline" ? (
        <div className="space-y-4 rounded-xl border border-line bg-shell p-4">
          <p className="text-sm text-ink-muted">
            That is fine. Would you like to set your own price instead, or leave it for
            now?
          </p>
          <div className="flex flex-wrap gap-3">
            <Button
              tone="secondary"
              onClick={() => {
                setPrice("");
                setPriceError(null);
                setMode("decline-price");
              }}
              disabled={sending}
            >
              Set my own price
            </Button>
            <Button
              onClick={() => void send("rejected")}
              disabled={sending}
              tone="quiet"
            >
              {sending ? "Saving" : "Decide later"}
            </Button>
            <Button tone="quiet" onClick={() => setMode("choose")} disabled={sending}>
              Back
            </Button>
          </div>
        </div>
      ) : null}

      {mode === "decline-price" ? (
        <div className="space-y-4 rounded-xl border border-line bg-shell p-4">
          <TextInput
            label="The price you want to charge, per session"
            value={price}
            onChange={(value) => {
              setPriceError(null);
              setPrice(value);
            }}
            error={priceError ?? undefined}
            hint={`A whole number of dollars, from ${formatMoney(PRICE_MIN)} to ${formatMoney(
              PRICE_MAX,
            )}.`}
          />
          <div className="flex flex-wrap gap-3">
            <Button onClick={() => submitPrice("rejected", false)} disabled={sending}>
              {sending ? "Saving" : "Save my price"}
            </Button>
            <Button
              tone="quiet"
              onClick={() => {
                setPriceError(null);
                setMode("decline");
              }}
              disabled={sending}
            >
              Back
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
