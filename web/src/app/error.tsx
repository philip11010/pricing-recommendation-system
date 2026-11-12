"use client";

/**
 * The page for something this application got wrong.
 *
 * It says what can be done rather than what went wrong internally: the reason
 * is in the console for whoever is building this, and a stack trace is not
 * something a mentor can act on.
 */

import { useEffect } from "react";

import { Banner, Button, ButtonLink, Column } from "@/components/ui";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <>
      <Banner
        title="Something went wrong"
        lead="This page did not load the way it should have."
      />
      <Column className="py-10">
        <p className="max-w-prose text-ink-700">
          Nothing you had entered has been sent anywhere. Try the page again, and if it
          keeps happening, go back to the start and come at it from there.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Button onClick={reset}>Try this page again</Button>
          <ButtonLink href="/" variant="outline">
            Go to the start
          </ButtonLink>
        </div>
      </Column>
    </>
  );
}
