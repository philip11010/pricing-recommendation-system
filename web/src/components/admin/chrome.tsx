"use client";

/**
 * The furniture of the administration pages: the sidebar and the stat cards.
 *
 * **Why a sidebar at all**, on a product whose every other screen is one
 * column. The five sections here are five different questions about the same
 * service, read in no particular order and returned to: which model is being
 * used, what has been advised, who has registered, how the models scored.
 * That is what a sidebar is for. The mentor-facing screens each answer one
 * question, which is why none of them has one.
 *
 * **It is navigation, not tabs.** The buttons move between sections of one
 * page, so they are a `nav` with `aria-current="page"` on the chosen one,
 * marked by weight and a fill as well as by colour. A tablist would promise
 * arrow-key behaviour that this does not implement.
 *
 * At 900px and below the sidebar becomes a row of the same buttons above the
 * content, which scrolls sideways inside itself rather than widening the
 * page.
 */

import type { ReactNode } from "react";

export interface AdminSection {
  id: string;
  label: string;
}

/** The five sections, in the order the sidebar lists them. */
export const ADMIN_SECTIONS: AdminSection[] = [
  { id: "overview", label: "Overview" },
  { id: "usage", label: "Model usage" },
  { id: "outputs", label: "Outputs" },
  { id: "users", label: "Users" },
  { id: "models", label: "Models" },
];

export function AdminNav({
  current,
  onSelect,
}: {
  current: string;
  onSelect: (id: string) => void;
}) {
  return (
    <nav aria-label="Administration sections" className="wide:w-56 wide:flex-none">
      {/* One list, two layouts. A row that scrolls inside itself on a phone,
          and a column beside the content from 900px up. */}
      <ul className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1 wide:mx-0 wide:flex-col wide:gap-1 wide:overflow-visible wide:px-0 wide:pb-0">
        {ADMIN_SECTIONS.map((section) => {
          const chosen = section.id === current;
          return (
            <li key={section.id} className="flex-none wide:w-full">
              <button
                type="button"
                onClick={() => onSelect(section.id)}
                aria-current={chosen ? "page" : undefined}
                className={`inline-flex min-h-[44px] w-full items-center whitespace-nowrap rounded-field px-3.5 py-2.5 text-left transition-colors duration-[180ms] ease-entrance ${
                  chosen
                    ? "bg-accent-100 font-bold text-accent-800"
                    : "font-medium text-ink-700 hover:bg-surface-sunk"
                }`}
              >
                {section.label}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/**
 * One figure with its label above it and an optional note under it.
 *
 * The same anatomy as the mentor-facing statistic card, kept here rather than
 * reused because this one takes a string value and sits in a denser grid: six
 * of these across a row at full width, two on a phone.
 */
export function StatCard({
  label,
  value,
  note,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
}) {
  return (
    <div className="min-w-0 rounded-card border border-line bg-surface p-4 mid:p-5">
      <p className="text-overline uppercase text-ink-500">{label}</p>
      <p className="tabular mt-1 text-[1.5rem] font-bold leading-tight">{value}</p>
      {note ? <p className="mt-1 text-small text-ink-500">{note}</p> : null}
    </div>
  );
}

/** The row the summary figures sit in. */
export function StatRow({ children }: { children: ReactNode }) {
  return (
    <div className="grid gap-4 grid-cols-2 wide:grid-cols-3 xl:grid-cols-6">
      {children}
    </div>
  );
}

/** The grid the charts sit in: one column on a tablet, two on a wide screen. */
export function ChartGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-5 xl:grid-cols-2">{children}</div>;
}

/** A heading above a group of charts, so a section reads as sections. */
export function SectionHeading({ title, lead }: { title: string; lead?: ReactNode }) {
  return (
    <div>
      <h2 className="text-h2 font-display">{title}</h2>
      {lead ? <p className="mt-2 max-w-prose text-ink-700">{lead}</p> : null}
    </div>
  );
}
