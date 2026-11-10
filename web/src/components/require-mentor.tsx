"use client";

/**
 * A page that needs to know which mentor it is for.
 *
 * Reading browser storage is a client-side act, so a page cannot know on the
 * server whether anyone is signed in. This waits one render, reads the id,
 * and sends the visitor to the landing page if there is none, rather than
 * calling the API without an identity header and showing them a 401.
 */

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { readMentorId } from "@/lib/mentor-session";
import { LoadingBlock } from "@/components/ui";

type State = { checked: false } | { checked: true; mentorId: number | null };

export function RequireMentor({
  children,
}: {
  children: (mentorId: number) => ReactNode;
}) {
  const router = useRouter();
  const [state, setState] = useState<State>({ checked: false });

  useEffect(() => {
    const mentorId = readMentorId();
    setState({ checked: true, mentorId });
    if (mentorId === null) {
      router.replace("/");
    }
  }, [router]);

  if (!state.checked) {
    return <LoadingBlock label="Checking who you are" />;
  }

  if (state.mentorId === null) {
    return (
      <LoadingBlock label="Taking you back to the start, because we do not know which mentor this is for" />
    );
  }

  return <>{children(state.mentorId)}</>;
}
