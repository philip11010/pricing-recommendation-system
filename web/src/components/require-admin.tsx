"use client";

/**
 * A page only an administrator may read.
 *
 * Three answers rather than two, because "not signed in" and "signed in and
 * not allowed" are different situations and sending both to the log in screen
 * would put a mentor in a loop: they would log in, arrive, and be sent back
 * to log in again.
 *
 * * Still checking the token: nothing is decided, and the page waits. A guard
 *   that redirected while the token was in flight would bounce an
 *   administrator to the log in screen on every reload.
 * * No account: the log in screen.
 * * An account without the flag: their own dashboard, which is the page they
 *   were looking for.
 *
 * **This is not the permission.** The flag it reads came from the API, and the
 * API checks the same flag on the account for every /admin request. A browser
 * that set it by hand would reach this page and then get 403 from all six
 * endpoints, which the page reports as the refusal it is. The guard is here so
 * that a mentor who follows a link is sent somewhere useful, not to keep
 * anybody out.
 */

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Column, LoadingBlock } from "@/components/ui";
import type { Mentor } from "@/lib/api-types";
import { useSession } from "@/lib/session";

export function RequireAdmin({
  children,
}: {
  children: (mentor: Mentor) => ReactNode;
}) {
  const { loading, mentor } = useSession();
  const router = useRouter();
  const allowed = Boolean(mentor?.is_admin);

  useEffect(() => {
    if (loading) {
      return;
    }
    if (!mentor) {
      router.replace("/login");
      return;
    }
    if (!allowed) {
      router.replace("/dashboard");
    }
  }, [allowed, loading, mentor, router]);

  if (loading) {
    return (
      <Column className="py-10">
        <LoadingBlock label="Checking your account" />
      </Column>
    );
  }

  // Nothing at all rather than a flash of the page followed by a redirect.
  if (!mentor || !allowed) {
    return null;
  }

  return <>{children(mentor)}</>;
}
