/**
 * The page for an address that is not one of ours.
 *
 * Calm, with the same banner as every other calm screen, and two ways out
 * rather than an apology with nowhere to go.
 */

import { Banner, ButtonLink, Column } from "@/components/ui";

export default function NotFound() {
  return (
    <>
      <Banner
        title="We could not find that page"
        lead="The address you followed does not point at anything here."
      />
      <Column className="py-10">
        <p className="max-w-prose text-ink-700">
          It may have been a mistyped address, or a link to something that has since
          been removed. Both of these will get you back.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <ButtonLink href="/">Go to the start</ButtonLink>
          <ButtonLink href="/mentors" variant="outline">
            Browse mentors
          </ButtonLink>
        </div>
      </Column>
    </>
  );
}
