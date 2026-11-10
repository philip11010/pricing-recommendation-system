/**
 * The small pieces every page is built from.
 *
 * Tailwind classes gathered into named components rather than repeated, so
 * that "a button" and "a card" mean one thing across the application and a
 * change to either happens once.
 */

import Link from "next/link";
import type { ReactNode } from "react";

type ButtonTone = "primary" | "secondary" | "quiet" | "danger";

const BUTTON_BASE =
  "inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-base font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60";

const BUTTON_TONES: Record<ButtonTone, string> = {
  primary: "bg-accent-700 text-white hover:bg-accent-800",
  secondary: "border border-accent-700 bg-white text-accent-800 hover:bg-accent-50",
  quiet: "border border-line bg-white text-ink-muted hover:bg-shell",
  danger:
    "border border-caution-200 bg-caution-50 text-caution-700 hover:bg-caution-50",
};

export function Button({
  tone = "primary",
  type = "button",
  className = "",
  children,
  ...rest
}: {
  tone?: ButtonTone;
  children: ReactNode;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type={type}
      className={`${BUTTON_BASE} ${BUTTON_TONES[tone]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

export function ButtonLink({
  href,
  tone = "primary",
  className = "",
  children,
}: {
  href: string;
  tone?: ButtonTone;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link href={href} className={`${BUTTON_BASE} ${BUTTON_TONES[tone]} ${className}`}>
      {children}
    </Link>
  );
}

export function Card({
  className = "",
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={`rounded-xl2 border border-line bg-white p-5 shadow-card sm:p-7 ${className}`}
    >
      {children}
    </section>
  );
}

export function PageHeading({
  eyebrow,
  title,
  lead,
}: {
  eyebrow?: string;
  title: string;
  lead?: ReactNode;
}) {
  return (
    <header className="mb-6">
      {eyebrow ? (
        <p className="mb-2 text-sm font-semibold uppercase tracking-wide text-accent-700">
          {eyebrow}
        </p>
      ) : null}
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{title}</h1>
      {lead ? <p className="mt-3 max-w-prose text-lg text-ink-muted">{lead}</p> : null}
    </header>
  );
}

export function SectionHeading({
  title,
  description,
  action,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
        {description ? (
          <p className="mt-1 max-w-prose text-sm text-ink-muted">{description}</p>
        ) : null}
      </div>
      {action}
    </div>
  );
}

type CalloutTone = "notice" | "caution" | "accent" | "quiet";

const CALLOUT_TONES: Record<CalloutTone, string> = {
  notice: "border-notice-200 bg-notice-50 text-notice-700",
  caution: "border-caution-200 bg-caution-50 text-caution-700",
  accent: "border-accent-200 bg-accent-50 text-accent-800",
  quiet: "border-line bg-shell text-ink-muted",
};

export function Callout({
  tone = "notice",
  title,
  children,
}: {
  tone?: CalloutTone;
  title?: string;
  children: ReactNode;
}) {
  return (
    <div className={`rounded-xl border p-4 text-sm ${CALLOUT_TONES[tone]}`}>
      {title ? <p className="mb-1 font-semibold">{title}</p> : null}
      <div className="leading-relaxed">{children}</div>
    </div>
  );
}

export function Badge({
  children,
  tone = "quiet",
}: {
  children: ReactNode;
  tone?: CalloutTone;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold ${CALLOUT_TONES[tone]}`}
    >
      {children}
    </span>
  );
}

/**
 * What a page shows while it is waiting.
 *
 * Announced politely rather than silently, so that someone using a screen
 * reader is told the page is working instead of being left on an empty one.
 */
export function LoadingBlock({ label = "Loading" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-3 rounded-xl2 border border-line bg-white p-6 text-ink-muted shadow-card"
    >
      <span
        aria-hidden="true"
        className="h-5 w-5 animate-spin rounded-full border-2 border-accent-200 border-t-accent-700"
      />
      <span>{label}</span>
    </div>
  );
}

/**
 * What a page shows when a request failed.
 *
 * `role="alert"` rather than a polite region: the page has nothing else on it
 * and the reason is the only thing to read.
 */
export function ErrorNotice({
  message,
  onRetry,
  retryLabel = "Try again",
}: {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <div
      role="alert"
      className="rounded-xl2 border border-caution-200 bg-caution-50 p-6 shadow-card"
    >
      <p className="font-semibold text-caution-700">We could not load this</p>
      <p className="mt-2 text-sm leading-relaxed text-caution-700">{message}</p>
      {onRetry ? (
        <div className="mt-4">
          <Button tone="secondary" onClick={onRetry}>
            {retryLabel}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-shell p-6 text-center">
      <p className="font-semibold">{title}</p>
      {children ? (
        <p className="mx-auto mt-2 max-w-prose text-sm text-ink-muted">{children}</p>
      ) : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

/** A label and a figure, which is most of what the dashboard is. */
export function Statistic({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-line bg-white p-4">
      <dt className="text-sm text-ink-soft">{label}</dt>
      <dd className="tabular mt-1 text-xl font-semibold">{value}</dd>
      {hint ? <p className="mt-1 text-xs text-ink-soft">{hint}</p> : null}
    </div>
  );
}
