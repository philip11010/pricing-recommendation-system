"use client";

/**
 * The bar at the top of every page.
 *
 * On the landing page it is the brand and nothing else, because nobody has
 * said who they are yet. Everywhere after it, it carries the three things a
 * mentor needs wherever they are: who they are signed in as, the way back to
 * their own page, and the way out.
 *
 * "Switch mentor" rather than "Sign out", because there is no authentication
 * to sign out of. Saying "sign out" would claim a security property this
 * prototype does not have.
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { BRAND } from "@/lib/copy";
import {
  MENTOR_CHANGED_EVENT,
  clearMentorId,
  readMentorId,
  readMentorName,
} from "@/lib/mentor-session";

export function SiteHeader() {
  const pathname = usePathname();
  const router = useRouter();
  const [mentorId, setMentorId] = useState<number | null>(null);
  const [mentorName, setMentorName] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setMentorId(readMentorId());
    setMentorName(readMentorName());
  }, []);

  useEffect(() => {
    refresh();
    window.addEventListener(MENTOR_CHANGED_EVENT, refresh);
    // Another tab switching mentor should not leave this one claiming the
    // old name.
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(MENTOR_CHANGED_EVENT, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, [refresh, pathname]);

  const onLanding = pathname === "/";
  const signedIn = !onLanding && mentorId !== null;

  function switchMentor() {
    clearMentorId();
    router.push("/mentors");
  }

  return (
    <header className="border-b border-line bg-white">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3 sm:px-6">
        <Link
          href={signedIn ? "/dashboard" : "/"}
          className="flex items-center gap-2 text-base font-bold tracking-tight"
        >
          <span
            aria-hidden="true"
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent-700 text-sm font-bold text-white"
          >
            CM
          </span>
          {BRAND}
        </Link>

        {signedIn ? (
          <nav aria-label="Mentor" className="flex items-center gap-1 sm:gap-3">
            <span className="hidden max-w-[12rem] truncate text-sm text-ink-muted sm:inline">
              Signed in as{" "}
              <span className="font-semibold text-ink">
                {mentorName ?? `mentor ${mentorId}`}
              </span>
            </span>
            <Link
              href="/dashboard"
              className="flex min-h-[44px] items-center rounded-xl px-3 text-sm font-semibold text-accent-800 hover:bg-accent-50"
            >
              My page
            </Link>
            <button
              type="button"
              onClick={switchMentor}
              className="flex min-h-[44px] items-center rounded-xl px-3 text-sm font-semibold text-ink-muted hover:bg-shell"
            >
              Switch mentor
            </button>
          </nav>
        ) : null}
      </div>
    </header>
  );
}
