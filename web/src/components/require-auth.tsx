"use client";

/**
 * A page only a signed in mentor may read.
 *
 * It waits for the first answer before deciding: redirecting while the token
 * is still being checked would bounce a signed in mentor to the log in screen
 * on every reload. Once the answer is no, the mentor is sent to log in and
 * the page under this renders nothing at all, rather than flashing and then
 * disappearing.
 *
 * The mentor is handed to the page, so the page does not ask again for a
 * record this already holds.
 */

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Column, LoadingBlock } from "@/components/ui";
import type { Mentor } from "@/lib/api-types";
import { useSession } from "@/lib/session";

export function RequireAuth({ children }: { children: (mentor: Mentor) => ReactNode }) {
  const { loading, mentor } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !mentor) {
      router.replace("/login");
    }
  }, [loading, mentor, router]);

  if (loading) {
    return (
      <Column className="py-10">
        <LoadingBlock label="Checking your account" />
      </Column>
    );
  }

  if (!mentor) {
    return null;
  }

  return <>{children(mentor)}</>;
}
