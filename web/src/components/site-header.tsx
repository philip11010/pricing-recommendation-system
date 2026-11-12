"use client";

/**
 * The same header on every page, in two colours.
 *
 * Dark on the bold screens, so it belongs to the gradient underneath it, and
 * white with a bottom border on the calm ones. Which screens are bold is
 * decided here, in one list, rather than by each page passing a flag it could
 * forget.
 *
 * A visitor and a signed in mentor see different navigation, and the current
 * page is marked with aria-current as well as with colour and weight, so the
 * mark is not carried by colour alone.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

import { LogoMark } from "@/components/logo";
import { Button, ButtonLink } from "@/components/ui";
import { BRAND } from "@/lib/copy";
import { useSession } from "@/lib/session";

/** The screens that carry the full bleed gradient, per DESIGN.md section 12. */
function isBoldScreen(path: string): boolean {
  return path === "/" || path === "/login" || path.startsWith("/recommendation/");
}

export function initialsOf(name: string): string {
  return (name ?? "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function SiteHeader() {
  const path = usePathname() ?? "/";
  const dark = isBoldScreen(path);
  const { mentor, logout } = useSession();

  const shell = dark
    ? "on-gradient bg-on-gradient-dark text-surface"
    : "border-b border-line bg-surface";
  const linkTone = dark ? "text-surface" : "text-ink-700";

  const navLink = (href: string, label: string) => {
    const current = path === href || path.startsWith(`${href}/`);
    return (
      <Link
        href={href}
        aria-current={current ? "page" : undefined}
        className={`inline-flex min-h-[44px] items-center rounded-pill px-3 py-2.5 mid:min-h-[40px] transition-colors duration-[180ms] ease-entrance ${
          current
            ? dark
              ? "font-bold text-surface"
              : "font-bold text-accent-700"
            : `font-medium ${linkTone}`
        }`}
      >
        {label}
      </Link>
    );
  };

  return (
    <header className={`relative z-10 ${shell}`}>
      <div className="mx-auto flex w-full max-w-site flex-wrap items-center justify-between gap-4 px-4 py-[18px] sm:px-6">
        <Link
          href="/"
          aria-label={`${BRAND} home`}
          className="flex items-center gap-2.5 font-display text-2xl font-extrabold tracking-[-0.03em]"
        >
          <LogoMark onDark={dark} />
          {BRAND}
        </Link>

        <nav
          aria-label="Main"
          className="flex flex-wrap items-center justify-end gap-1.5"
        >
          {mentor ? (
            <>
              {navLink("/mentors", "Mentors")}
              {navLink("/dashboard", "Dashboard")}
              {/* The outlined pill has a hover state built for the surface it
                  is on. A quiet pill recoloured for the gradient would keep
                  the light hover fill underneath its white label. */}
              <Button variant={dark ? "outlineDark" : "quiet"} small onClick={logout}>
                Log out
              </Button>
              <span
                aria-hidden="true"
                className="ml-1 inline-grid h-9 w-9 flex-none place-items-center rounded-pill bg-tint-violet text-label font-bold text-accent-800"
              >
                {initialsOf(mentor.full_name)}
              </span>
            </>
          ) : (
            <>
              <span className="hidden mid:inline">
                {navLink("/mentors", "Browse mentors")}
              </span>
              <ButtonLink
                href="/login"
                small
                variant={dark ? "outlineDark" : "outline"}
              >
                Existing mentor
              </ButtonLink>
              <ButtonLink href="/register" small variant={dark ? "white" : "solid"}>
                Register
              </ButtonLink>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
