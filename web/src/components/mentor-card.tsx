/**
 * One mentor, as the landing page and the directory both show them.
 *
 * Verified and not yet verified are the same card otherwise: the chip states
 * which it is in words beside its own icon, so a new mentor is listed on the
 * same terms as anybody else rather than looking like an incomplete one.
 */

import Link from "next/link";

import { CheckIcon, Chip } from "@/components/ui";
import type { MentorCard as MentorCardData } from "@/lib/api-types";
import { UNVERIFIED_LABEL, VERIFIED_LABEL } from "@/lib/copy";
import { formatMoney } from "@/lib/format";
import { initialsOf } from "@/components/site-header";

/** The four soft tints, chosen by id so a card keeps its colour. */
const TINTS = ["bg-tint-indigo", "bg-tint-blue", "bg-tint-violet", "bg-tint-cyan"];

export function groupLabel(maxMentees: number): string {
  return maxMentees <= 1 ? "One to one" : `Group of ${maxMentees}`;
}

export function MentorCardTile({ mentor }: { mentor: MentorCardData }) {
  const tint = TINTS[mentor.id % TINTS.length];
  return (
    <article className="flex min-w-0 flex-col gap-3 rounded-card border border-line bg-surface p-6">
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className={`grid h-12 w-12 flex-none place-items-center rounded-pill text-base font-bold text-accent-800 ${tint}`}
        >
          {initialsOf(mentor.display_name)}
        </span>
        <div className="min-w-0">
          <p className="font-bold leading-tight">
            <Link
              href={`/mentors/${mentor.id}`}
              className="underline-offset-[3px] hover:underline"
            >
              {mentor.display_name}
            </Link>
          </p>
          <p className="text-small text-ink-500">{mentor.service_name}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {mentor.verified ? (
          <Chip tone="verified" icon={<CheckIcon />}>
            {VERIFIED_LABEL}
          </Chip>
        ) : (
          <Chip tone="new">{UNVERIFIED_LABEL}</Chip>
        )}
        <Chip>{mentor.field_label}</Chip>
      </div>

      <div className="mt-auto flex items-end justify-between gap-2">
        <div>
          <p className="tabular font-display text-[1.75rem] font-extrabold tracking-[-0.02em]">
            {formatMoney(mentor.price)}
          </p>
          <p className="text-small text-ink-500">
            {groupLabel(mentor.max_mentees)} session
          </p>
        </div>
        <p className="text-small text-ink-500">
          {mentor.review_count > 0
            ? `${mentor.review_count} reviews`
            : "No reviews yet"}
        </p>
      </div>
    </article>
  );
}
