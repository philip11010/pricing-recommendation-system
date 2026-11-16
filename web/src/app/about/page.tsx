/**
 * About: bold hero, then calm all the way down.
 *
 * This is the page a reader opens when they want to decide whether to believe
 * the number the rest of the product shows them, so it is written to be
 * checkable rather than persuasive. Every claim on it is either something the
 * application does, or a figure read out of the training report. There are no
 * testimonials, no counts of users, no logos and no partners, because none of
 * those exist, and a page that invented them would undo the trust it was
 * built to earn.
 *
 * A server component: it holds no state, so it carries its own metadata.
 *
 * The sentences live in lib/copy.ts with the rest of what the product says.
 */

import type { Metadata } from "next";
import type { ReactNode } from "react";

import { ButtonLink, Card, Column, Note } from "@/components/ui";
import {
  ABOUT_ACCURACY,
  ABOUT_BUILD,
  ABOUT_CLOSING,
  ABOUT_DATA,
  ABOUT_HERO,
  ABOUT_HOW,
  ABOUT_HOW_IT_WORKS_ID,
  ABOUT_LIMITS,
  ABOUT_META_DESCRIPTION,
  ABOUT_PROBLEM,
  ABOUT_SCORE_MODELS,
  ABOUT_SCORE_ROWS,
  ABOUT_TITLE,
  type AboutStepIcon,
} from "@/lib/copy";

export const metadata: Metadata = {
  title: ABOUT_TITLE,
  description: ABOUT_META_DESCRIPTION,
};

/**
 * The three step icons.
 *
 * One family, one stroke weight, drawn in currentColor so each takes the ink
 * of the card it sits on. Decorative beside a visible label, so hidden from
 * the accessibility tree.
 */
function StepIcon({ name }: { name: AboutStepIcon }) {
  const shared = {
    viewBox: "0 0 24 24",
    className: "h-6 w-6 flex-none",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    focusable: "false" as const,
  };

  if (name === "profile") {
    return (
      <svg {...shared}>
        <circle cx="12" cy="8" r="3.5" />
        <path d="M4.5 20c0-3.6 3.4-5.5 7.5-5.5s7.5 1.9 7.5 5.5" />
      </svg>
    );
  }

  if (name === "compare") {
    return (
      <svg {...shared}>
        <path d="M4 19V9.5M10 19V5M16 19v-6.5M22 19H2" />
      </svg>
    );
  }

  return (
    <svg {...shared}>
      <path d="M20.5 7 10 17.5 4.5 12" />
      <path d="M3.5 5.5h9" />
    </svg>
  );
}

/** One calm section: a display heading, an optional lead, then its content. */
function Section({
  id,
  title,
  lead,
  className = "",
  children,
}: {
  id?: string;
  title: string;
  lead?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className={className}>
      <Column wide className="relative py-12">
        <h2 className="max-w-headline text-balance font-display text-display">
          {title}
        </h2>
        {lead ? (
          <p className="mt-4 max-w-prose text-body-lg text-ink-700">{lead}</p>
        ) : null}
        <div className="mt-8">{children}</div>
      </Column>
    </section>
  );
}

export default function AboutPage() {
  return (
    <>
      {/* a. Hero, bold: the landing page gradient and its three glows. */}
      <section className="on-gradient bg-hero text-surface">
        <div className="mx-auto w-full max-w-site px-4 pb-16 pt-12 sm:px-6 wide:pb-20 wide:pt-16">
          {/* Written out rather than using Overline, which carries ink-500:
              two text colour utilities on one element are decided by the
              order Tailwind emits them, not by the order written here. */}
          <p className="text-overline uppercase text-surface">{ABOUT_TITLE}</p>
          <h1 className="mt-3 max-w-headline text-balance font-display text-display">
            {ABOUT_HERO.title}
          </h1>
          <p className="mt-6 max-w-lead text-body-lg text-on-gradient-lead">
            {ABOUT_HERO.lead}
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <ButtonLink href={ABOUT_HERO.primary.href} variant="white">
              {ABOUT_HERO.primary.label}
            </ButtonLink>
            <ButtonLink href={ABOUT_HERO.secondary.href} variant="outlineDark">
              {ABOUT_HERO.secondary.label}
            </ButtonLink>
          </div>
        </div>
      </section>

      {/* b. The problem. */}
      <Section title={ABOUT_PROBLEM.title} lead={ABOUT_PROBLEM.lead}>
        <div className="grid gap-6 mid:grid-cols-2 lg:grid-cols-3">
          {ABOUT_PROBLEM.points.map((point) => (
            <div key={point.title} className={`min-w-0 rounded-card p-6 ${point.tint}`}>
              <h3 className="text-h3 font-semibold">{point.title}</h3>
              <p className="mt-2 max-w-[34ch] text-ink-700">{point.body}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* c. How it works. The anchor the hero's second button points at. */}
      <Section
        id={ABOUT_HOW_IT_WORKS_ID}
        title={ABOUT_HOW.title}
        lead={ABOUT_HOW.lead}
        className="glow-field"
      >
        <ol className="grid list-none gap-6 p-0 mid:grid-cols-2 lg:grid-cols-3">
          {ABOUT_HOW.steps.map((step) => (
            <li key={step.step} className={`min-w-0 rounded-card p-6 ${step.tint}`}>
              <span className="inline-grid h-11 w-11 place-items-center rounded-pill bg-surface text-accent-800">
                <StepIcon name={step.icon} />
              </span>
              <p className="mt-4 text-overline uppercase text-ink-500">{step.step}</p>
              <h3 className="my-2 text-h3 font-semibold">{step.title}</h3>
              <p className="max-w-[34ch] text-ink-700">{step.body}</p>
            </li>
          ))}
        </ol>
      </Section>

      {/* d. Where the data came from. */}
      <Section title={ABOUT_DATA.title}>
        <div className="max-w-prose space-y-4 text-body-lg text-ink-700">
          {ABOUT_DATA.paragraphs.map((paragraph) => (
            <p key={paragraph.slice(0, 40)}>{paragraph}</p>
          ))}
        </div>
      </Section>

      {/* e. How it was built. */}
      <Section title={ABOUT_BUILD.title} lead={ABOUT_BUILD.lead}>
        <ol className="grid max-w-prose list-none gap-5 p-0">
          {ABOUT_BUILD.points.map((point, index) => (
            <li key={point.slice(0, 40)} className="flex gap-4">
              <span
                aria-hidden="true"
                className="tabular inline-grid h-9 w-9 flex-none place-items-center rounded-pill bg-accent-100 text-label font-bold text-accent-800"
              >
                {index + 1}
              </span>
              <p className="text-ink-700">{point}</p>
            </li>
          ))}
        </ol>
        <p className="mt-8 max-w-prose text-small text-ink-500">
          {ABOUT_BUILD.curious}
        </p>
      </Section>

      {/* f. How accurate is it. Every figure read from the training report. */}
      <Section title={ABOUT_ACCURACY.title} lead={ABOUT_ACCURACY.lead}>
        <div className="grid gap-6 mid:grid-cols-2">
          {ABOUT_SCORE_MODELS.map((model) => (
            <Card key={model.key}>
              <h3 className="text-h3 font-semibold">{model.name}</h3>
              <p className="mt-1.5 text-small text-ink-500">{model.note}</p>
              <dl className="mt-5 grid gap-4">
                {ABOUT_SCORE_ROWS.map((row) => (
                  <div
                    key={row.label}
                    className="border-t border-line pt-4 first:border-t-0 first:pt-0"
                  >
                    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                      <dt className="font-semibold">{row.label}</dt>
                      <dd className="tabular text-[1.375rem] font-bold leading-tight">
                        {model.key === "core" ? row.core : row.full}
                      </dd>
                    </div>
                    <p className="mt-1 text-small text-ink-500">{row.scale}</p>
                  </div>
                ))}
              </dl>
            </Card>
          ))}
        </div>
        <p className="mt-8 max-w-prose text-body-lg text-ink-700">
          {ABOUT_ACCURACY.verdict}
        </p>
        <Note
          tone="caution"
          title={ABOUT_ACCURACY.limitTitle}
          className="mt-5 max-w-prose"
        >
          {ABOUT_ACCURACY.limit}
        </Note>
      </Section>

      {/* g. What it does not do. */}
      <Section title={ABOUT_LIMITS.title}>
        <div className="grid gap-6 mid:grid-cols-2 lg:grid-cols-3">
          {ABOUT_LIMITS.points.map((point) => (
            <Card key={point.title}>
              <h3 className="text-h3 font-semibold">{point.title}</h3>
              <p className="mt-2 text-ink-700">{point.body}</p>
            </Card>
          ))}
        </div>
      </Section>

      {/* h. Closing. */}
      <Column wide className="pb-14">
        <div className="on-gradient rounded-band bg-closing px-6 py-10 text-surface mid:px-8 mid:py-14">
          <h2 className="max-w-headline text-balance font-display text-display">
            {ABOUT_CLOSING.title}
          </h2>
          <p className="mt-4 max-w-lead text-on-gradient-lead">{ABOUT_CLOSING.lead}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <ButtonLink href={ABOUT_CLOSING.primary.href} variant="white">
              {ABOUT_CLOSING.primary.label}
            </ButtonLink>
            <ButtonLink href={ABOUT_CLOSING.secondary.href} variant="outlineDark">
              {ABOUT_CLOSING.secondary.label}
            </ButtonLink>
          </div>
        </div>
      </Column>
    </>
  );
}
