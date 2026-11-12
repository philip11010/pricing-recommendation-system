"use client";

/**
 * The landing page: bold register.
 *
 * A full bleed hero gradient, one display headline with a single italic word,
 * an example of what a mentor is about to be shown, three steps on soft
 * tinted cards, three real mentors from the public directory, and a closing
 * band. The example price card is example content and says so: live figures
 * belong to a mentor who has answered the form.
 */

import { MentorCardTile } from "@/components/mentor-card";
import { PriceLadder } from "@/components/price-ladder";
import {
  ButtonLink,
  Column,
  EmptyState,
  ErrorNotice,
  LoadingBlock,
  Note,
  Overline,
  RaisedCard,
  TextLink,
} from "@/components/ui";
import { api } from "@/lib/api-client";
import { ADVISORY_LINE, LOW_CONFIDENCE_NOTE, LOW_CONFIDENCE_TITLE } from "@/lib/copy";
import { messageFor } from "@/lib/errors";
import { useAsync } from "@/lib/use-async";

/**
 * The figures on the example card.
 *
 * Fixed, and labelled as an example on the card itself. A number pulled from
 * the API here would be one mentor's price presented as everybody's.
 */
const EXAMPLE = {
  price: 185,
  low: 126,
  high: 276,
  scale: { min: 90, max: 420 },
};

const STEPS = [
  {
    step: "Step 1",
    title: "Tell us what you offer",
    body: "Your field, how many people you mentor at once, and the skills you cover.",
    tint: "bg-tint-indigo",
  },
  {
    step: "Step 2",
    title: "See your suggested price",
    body: "One number, the range around it, and how it compares with mentors like you.",
    tint: "bg-tint-blue",
  },
  {
    step: "Step 3",
    title: "Accept, change or decline",
    body: "It is your call. Come back any time to see how your price sits over the months.",
    tint: "bg-tint-violet",
  },
];

function MentorsAlreadyHere() {
  const { status, data, error, reload } = useAsync(
    (signal) => api.directory({ limit: 3 }, signal),
    "landing-mentors",
  );

  if (status === "loading") {
    return <LoadingBlock label="Loading mentors" />;
  }

  if (status === "error") {
    return (
      <ErrorNotice
        title="We could not load the mentors"
        message={messageFor(error)}
        onRetry={reload}
      />
    );
  }

  const mentors = data?.items ?? [];
  if (mentors.length === 0) {
    return (
      <EmptyState title="No mentors are listed yet">
        Be the first. Register, and your profile appears here straight away.
      </EmptyState>
    );
  }

  return (
    <div className="grid gap-6 mid:grid-cols-2 lg:grid-cols-3">
      {mentors.map((mentor) => (
        <MentorCardTile key={mentor.id} mentor={mentor} />
      ))}
    </div>
  );
}

export default function LandingPage() {
  return (
    <>
      <section className="on-gradient bg-hero text-surface">
        <div className="mx-auto grid w-full max-w-site items-center gap-8 px-4 pb-14 pt-8 sm:px-6 wide:grid-cols-[1.1fr_0.9fr] wide:gap-12 wide:pb-20 wide:pt-12">
          <div>
            <h1 className="max-w-[12ch] text-balance font-display text-display mid:text-display-xl">
              Know what your time is <em className="accent-word">worth</em>.
            </h1>
            <p className="mt-6 max-w-lead text-body-lg text-on-gradient-lead">
              Tell us about your sessions. Get a suggested price, and see what mentors
              like you charge.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <ButtonLink href="/register" variant="white">
                Get my price
              </ButtonLink>
              <TextLink href="/login" onGradient>
                I am an existing mentor
              </TextLink>
            </div>
            <p className="mt-5 text-small text-on-gradient-fine">
              Free to try. You set the final price.
            </p>
          </div>

          <RaisedCard
            role="group"
            aria-label="Example price suggestion"
            className="mx-auto w-full max-w-[440px]"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Overline>Suggested session price</Overline>
              <span className="rounded-pill bg-accent-100 px-3 py-1 text-label font-semibold text-accent-800">
                Example
              </span>
            </div>
            <p className="tabular mt-2.5 font-display text-figure">
              ${EXAMPLE.price}
              <span className="ml-2 text-base font-semibold tracking-normal text-ink-500">
                AUD
              </span>
            </p>
            <p className="mt-1.5 font-medium text-ink-700">
              Similar mentors charge ${EXAMPLE.low} to ${EXAMPLE.high}
            </p>
            <div className="mt-4">
              <PriceLadder
                scale={EXAMPLE.scale}
                bandLow={EXAMPLE.low}
                bandHigh={EXAMPLE.high}
                suggested={EXAMPLE.price}
                sentence={`In this example the suggested $${EXAMPLE.price} sits in the middle of what similar mentors charge, $${EXAMPLE.low} to $${EXAMPLE.high}.`}
                tableCaption="The figures in this example"
              />
            </div>
            <p className="mt-4 text-ink-700">{ADVISORY_LINE}</p>
            <Note className="mt-4" title={LOW_CONFIDENCE_TITLE}>
              {LOW_CONFIDENCE_NOTE}
            </Note>
            <p className="mt-4 text-small text-ink-500">
              This is an example, not a price for anybody. Yours arrives after four
              short questions.
            </p>
          </RaisedCard>
        </div>
      </section>

      <section className="glow-field">
        <Column wide className="relative py-14">
          <h2 className="mb-10 max-w-[16ch] text-balance font-display text-display">
            Three steps to a price you can defend.
          </h2>
          <div className="grid gap-6 mid:grid-cols-2 lg:grid-cols-3">
            {STEPS.map((step) => (
              <div key={step.step} className={`min-w-0 rounded-card p-6 ${step.tint}`}>
                <p className="text-overline uppercase text-ink-500">{step.step}</p>
                <h3 className="my-2 text-h3 font-semibold">{step.title}</h3>
                <p className="max-w-[34ch] text-ink-700">{step.body}</p>
              </div>
            ))}
          </div>
        </Column>
      </section>

      <Column wide className="py-10">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <h2 className="max-w-[14ch] text-balance font-display text-display">
            Mentors already here.
          </h2>
          <TextLink href="/mentors">Browse all mentors</TextLink>
        </div>
        <MentorsAlreadyHere />
      </Column>

      <Column wide className="pb-14">
        <div className="on-gradient rounded-band bg-closing px-6 py-10 text-surface mid:px-8 mid:py-14">
          <h2 className="max-w-[18ch] text-balance font-display text-display">
            Start with your first price.
          </h2>
          <div className="mt-8 flex flex-wrap gap-3">
            <ButtonLink href="/register" variant="white">
              Register
            </ButtonLink>
            <ButtonLink href="/login" variant="outlineDark">
              Existing mentor
            </ButtonLink>
          </div>
        </div>
      </Column>
    </>
  );
}
