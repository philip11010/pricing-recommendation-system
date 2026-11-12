/**
 * The brand mark: a rounded square with a path turning upwards into a point.
 *
 * Inline rather than a file, so it takes its colour from the surface it is
 * on. On a dark header the square is white with an indigo path; on a white
 * one the square is ink with a white path. The product name beside it comes
 * from the BRAND constant, never from here.
 */

export function LogoMark({
  onDark = false,
  className = "h-7 w-7",
}: {
  onDark?: boolean;
  className?: string;
}) {
  const square = onDark ? "text-surface" : "text-ink-900";
  const ink = onDark ? "var(--gradient-dark)" : "var(--surface)";
  return (
    <svg
      viewBox="0 0 28 28"
      className={`${className} ${square} flex-none`}
      aria-hidden="true"
      focusable="false"
    >
      <rect width="28" height="28" rx="9" fill="currentColor" />
      <path
        d="M8 20 L8 12 Q8 8 12 8 L20 8"
        fill="none"
        stroke={ink}
        strokeWidth="3"
        strokeLinecap="round"
      />
      <circle cx="20" cy="20" r="3" fill={ink} />
    </svg>
  );
}
