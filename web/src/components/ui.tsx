/**
 * The small pieces every page is built from.
 *
 * Token classes gathered into named components rather than repeated, so that
 * "a white pill on the gradient" and "a quiet pill on a card" mean one thing
 * across the application and a change to either happens once. No component in
 * this file writes a colour of its own: every one of them is a theme entry
 * that points at a custom property.
 */

import Link from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";

export type ButtonVariant = "solid" | "white" | "outline" | "outlineDark" | "quiet";

const BUTTON_BASE =
  "inline-flex min-h-[44px] cursor-pointer items-center justify-center gap-2 rounded-pill px-6 py-[11px] text-base font-semibold leading-none transition-colors duration-[180ms] ease-entrance disabled:cursor-not-allowed disabled:opacity-60";

const BUTTON_SMALL =
  "inline-flex min-h-[44px] mid:min-h-[40px] cursor-pointer items-center justify-center gap-2 rounded-pill px-[18px] py-2 text-[0.9375rem] font-semibold leading-none transition-colors duration-[180ms] ease-entrance disabled:cursor-not-allowed disabled:opacity-60";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  solid:
    "border-2 border-accent-700 bg-accent-700 text-surface hover:bg-accent-800 hover:border-accent-800",
  white:
    "border-2 border-surface bg-surface text-accent-800 hover:bg-tint-indigo hover:border-tint-indigo",
  outline:
    "border-2 border-ink-900 bg-transparent text-ink-900 hover:bg-ink-900 hover:text-surface",
  outlineDark:
    "border-2 border-surface bg-transparent text-surface hover:bg-surface hover:text-accent-800",
  quiet:
    "border border-line bg-transparent text-ink-700 hover:bg-surface-sunk hover:border-line-strong",
};

function buttonClass(variant: ButtonVariant, small: boolean, extra: string): string {
  return `${small ? BUTTON_SMALL : BUTTON_BASE} ${BUTTON_VARIANTS[variant]} ${extra}`;
}

export function Button({
  variant = "solid",
  small = false,
  type = "button",
  className = "",
  children,
  ...rest
}: {
  variant?: ButtonVariant;
  small?: boolean;
  children: ReactNode;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button type={type} className={buttonClass(variant, small, className)} {...rest}>
      {children}
    </button>
  );
}

export function ButtonLink({
  href,
  variant = "solid",
  small = false,
  className = "",
  children,
  ...rest
}: {
  href: string;
  variant?: ButtonVariant;
  small?: boolean;
  children: ReactNode;
} & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href">) {
  return (
    <Link href={href} className={buttonClass(variant, small, className)} {...rest}>
      {children}
    </Link>
  );
}

/**
 * An inline link in prose.
 *
 * The one place a second hue appears. Underlined as well as coloured, because
 * a colour change on its own is not a cue. On the gradient it is white.
 */
export function TextLink({
  href,
  onGradient = false,
  className = "",
  children,
}: {
  href: string;
  onGradient?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const tone = onGradient
    ? "text-surface hover:text-tint-indigo"
    : "text-link-700 hover:text-link-800";
  return (
    <Link
      href={href}
      className={`font-semibold underline underline-offset-[3px] ${tone} ${className}`}
    >
      {children}
    </Link>
  );
}

/** White, a hairline border, no shadow. The card for a calm page. */
export function Card({
  className = "",
  children,
  ...rest
}: {
  className?: string;
  children: ReactNode;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`min-w-0 rounded-card border border-line bg-surface p-6 ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}

/** White at full opacity with a shadow. The card that sits on the gradient. */
export function RaisedCard({
  className = "",
  children,
  ...rest
}: {
  className?: string;
  children: ReactNode;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`on-surface min-w-0 rounded-card bg-surface p-6 text-ink-900 shadow-card mid:p-8 ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}

export function Overline({
  className = "",
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <p className={`text-overline uppercase text-ink-500 ${className}`}>{children}</p>
  );
}

export type ChipTone = "neutral" | "verified" | "new" | "accepted" | "declined";

const CHIP_TONES: Record<ChipTone, string> = {
  neutral: "bg-surface-sunk text-ink-700",
  verified: "bg-success-fill text-success-700",
  new: "bg-caution-fill text-caution-700",
  accepted: "bg-success-fill text-success-700",
  declined: "bg-danger-fill text-danger-700",
};

export function Chip({
  tone = "neutral",
  icon,
  children,
}: {
  tone?: ChipTone;
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-pill px-3 py-1 text-label font-semibold ${CHIP_TONES[tone]}`}
    >
      {icon}
      {children}
    </span>
  );
}

/** A check mark, used only beside the word it belongs to. */
export function CheckIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" className={className} aria-hidden="true" focusable="false">
      <circle cx="10" cy="10" r="9" fill="currentColor" />
      <path
        d="M6 10.5l2.8 2.8L14 7.8"
        fill="none"
        stroke="var(--surface)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** A warning triangle, used beside the words of an error. */
export function WarningIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 20 20" className={className} aria-hidden="true" focusable="false">
      <path
        d="M10 2.5 18.5 17.5H1.5z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path
        d="M10 7.5v4.2"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <circle cx="10" cy="14.6" r="1" fill="currentColor" />
    </svg>
  );
}

export type NoteTone = "caution" | "info" | "danger" | "success";

const NOTE_TONES: Record<NoteTone, string> = {
  caution: "bg-caution-fill text-caution-700",
  info: "bg-accent-100 text-accent-800",
  danger: "bg-danger-fill text-danger-700",
  success: "bg-success-fill text-success-700",
};

/**
 * A short passage set apart on a tinted fill.
 *
 * Used for the low confidence note, which is first class content and never
 * fine print: it keeps body size and sits in the reading order.
 */
export function Note({
  tone = "caution",
  title,
  className = "",
  children,
  ...rest
}: {
  tone?: NoteTone;
  title?: string;
  className?: string;
  children: ReactNode;
} & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-field px-3.5 py-3 text-small ${NOTE_TONES[tone]} ${className}`}
      {...rest}
    >
      {title ? <strong className="font-bold">{title} </strong> : null}
      {children}
    </div>
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
      className="flex items-center gap-3 rounded-card border border-line bg-surface p-6 text-ink-700"
    >
      <span
        aria-hidden="true"
        className="h-5 w-5 animate-spin rounded-pill border-2 border-accent-100 border-t-accent-700"
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
  title = "We could not load this",
  message,
  onRetry,
  retryLabel = "Try again",
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <div
      role="alert"
      className="rounded-card border border-line bg-danger-fill p-6 text-danger-700"
    >
      <p className="font-bold">{title}</p>
      <p className="mt-2 max-w-prose text-small">{message}</p>
      {onRetry ? (
        <div className="mt-4">
          <Button variant="quiet" onClick={onRetry}>
            {retryLabel}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/** A sentence and a next action, wherever a list can come back empty. */
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
    <div className="rounded-card border border-dashed border-line-strong bg-surface-sunk p-6">
      <p className="font-bold">{title}</p>
      {children ? <p className="mt-2 max-w-prose text-ink-700">{children}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

/** A label above a figure. Used where there are too few points for a chart. */
export function Statistic({
  label,
  value,
  note,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
}) {
  return (
    <div className="min-w-0 rounded-card border border-line bg-surface p-6">
      <p className="text-overline uppercase text-ink-500">{label}</p>
      <p className="tabular mt-1 text-[1.75rem] font-bold leading-tight">{value}</p>
      {note ? <p className="mt-1 text-small text-ink-500">{note}</p> : null}
    </div>
  );
}

/** The slim band of colour a calm screen opens with. */
export function Banner({
  title,
  lead,
  action,
}: {
  title: ReactNode;
  lead?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="on-gradient bg-banner text-surface">
      <div className="mx-auto flex w-full max-w-site flex-wrap items-end justify-between gap-4 px-4 pb-10 pt-9 sm:px-6">
        <div className="min-w-0">
          <h1 className="max-w-headline text-display-sm font-display text-balance">
            {title}
          </h1>
          {lead ? (
            <p className="mt-2 max-w-[56ch] text-on-gradient-lead">{lead}</p>
          ) : null}
        </div>
        {action}
      </div>
    </div>
  );
}

/** The column every page lays its content out in. */
export function Column({
  wide = false,
  className = "",
  children,
}: {
  wide?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={`mx-auto w-full px-4 sm:px-6 ${wide ? "max-w-site" : "max-w-app"} ${className}`}
    >
      {children}
    </div>
  );
}
