import type { Metadata } from "next";

import { ButtonLink, Card } from "@/components/ui";
import { BRAND } from "@/lib/copy";

export const metadata: Metadata = {
  title: "Pricing help for mentors",
  description:
    "Tell us about the session you offer and we suggest a price, with the prices similar mentors charge beside it. You decide what to charge.",
};

/**
 * The landing page.
 *
 * Every claim on it is something the system actually does. There are no
 * testimonials, no counts of mentors and no accuracy figures, because none of
 * those exist to quote: this is a prototype, and a number put here to fill a
 * space would be invented.
 */

const STEPS = [
  {
    title: "You tell us about your service",
    body: "Your field, how many mentees can join one session, the smallest booking you accept, and the skills and topics you cover. That is the whole of it.",
  },
  {
    title: "We suggest a price, and show you the market",
    body: "You get a suggested price with a range around it, and beside it what mentors in your field at about your group size charge, as a spread rather than a single number.",
  },
  {
    title: "You accept, change or decline",
    body: "The suggestion is advice. Take it, set your own figure instead, or leave it. Whatever you settle on is what your service charges, and we keep the record of what was suggested against what you chose.",
  },
];

const FACTS = [
  {
    title: "New mentors get a first estimate",
    body: "With no sessions behind you there is no record to read, so your first suggestion comes from what you entered and is labelled as the estimate it is. It sharpens as you build a record.",
  },
  {
    title: "Established mentors are priced on their record",
    body: "Once you have ratings and booking history, the suggestion takes those into account as well, which is why it can sit away from the middle of the market.",
  },
  {
    title: "A price, never a wage",
    body: "We suggest what one session could be worth next to comparable mentors. We do not report earnings or income, because the number of sessions you will sell is not something we know.",
  },
];

export default function LandingPage() {
  return (
    <div className="space-y-12">
      <section className="pt-2">
        <p className="text-sm font-semibold uppercase tracking-wide text-accent-700">
          {BRAND}
        </p>
        <h1 className="mt-3 max-w-prose text-display font-bold">
          Know what to charge for a mentoring session.
        </h1>
        <p className="mt-5 max-w-prose text-lg leading-relaxed text-ink-muted">
          {BRAND} is for people who mentor others through their career and are paid for
          it. Describe the session you offer and we suggest a price for it, in
          Australian dollars, with the prices comparable mentors charge beside it. The
          suggestion is advice. You decide what to charge.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <ButtonLink href="/register">Become a mentor</ButtonLink>
          <ButtonLink href="/mentors" tone="secondary">
            I am already a mentor
          </ButtonLink>
        </div>
      </section>

      <section aria-labelledby="how-it-works">
        <h2 id="how-it-works" className="text-2xl font-bold tracking-tight">
          How the pricing suggestion works
        </h2>
        <ol className="mt-5 grid gap-4 sm:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step.title}>
              <Card className="h-full">
                <span
                  aria-hidden="true"
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-accent-50 text-base font-bold text-accent-800"
                >
                  {index + 1}
                </span>
                <h3 className="mt-4 text-lg font-semibold">{step.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-muted">
                  {step.body}
                </p>
              </Card>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="what-to-expect">
        <h2 id="what-to-expect" className="text-2xl font-bold tracking-tight">
          What to expect from the suggestion
        </h2>
        <dl className="mt-5 grid gap-4 sm:grid-cols-3">
          {FACTS.map((fact) => (
            <div
              key={fact.title}
              className="rounded-xl2 border border-line bg-white p-5"
            >
              <dt className="font-semibold">{fact.title}</dt>
              <dd className="mt-2 text-sm leading-relaxed text-ink-muted">
                {fact.body}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <section
        aria-labelledby="get-started"
        className="rounded-xl2 border border-accent-200 bg-accent-50 p-6 sm:p-8"
      >
        <h2
          id="get-started"
          className="text-2xl font-bold tracking-tight text-accent-900"
        >
          Ready to see a price?
        </h2>
        <p className="mt-3 max-w-prose leading-relaxed text-accent-900">
          Registering takes three short steps and ends with a suggested price for your
          first service. There is no payment and nothing to cancel.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <ButtonLink href="/register">Become a mentor</ButtonLink>
          <ButtonLink href="/mentors" tone="quiet">
            Open an existing mentor
          </ButtonLink>
        </div>
      </section>
    </div>
  );
}
