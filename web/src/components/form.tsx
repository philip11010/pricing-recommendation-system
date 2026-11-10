"use client";

/**
 * The form controls, built once so every field behaves the same way.
 *
 * Three things every control here does, because a mentor filling in a form is
 * the one place this application cannot afford to be clever:
 *
 * * The label is a real label element tied to the input, so tapping the words
 *   focuses the field and a screen reader reads the two together.
 * * A message about a field is tied to it with aria-describedby and marked
 *   aria-invalid, so it is read out rather than merely drawn in red.
 * * Every target is at least 44 pixels high, which is what a thumb needs.
 */

import type { KeyboardEvent, ReactNode } from "react";
import { useId } from "react";

import type { Option } from "@/lib/api-types";
import { formatMentees } from "@/lib/format";

const CONTROL =
  "min-h-[44px] w-full rounded-xl border bg-white px-3.5 py-2.5 text-base text-ink placeholder:text-ink-soft";

function controlClasses(invalid: boolean): string {
  return `${CONTROL} ${invalid ? "border-caution-700" : "border-line"}`;
}

function Describers({
  hintId,
  errorId,
  hint,
  error,
}: {
  hintId: string;
  errorId: string;
  hint?: ReactNode;
  error?: string;
}) {
  return (
    <>
      {hint ? (
        <p id={hintId} className="mt-1 text-sm text-ink-soft">
          {hint}
        </p>
      ) : null}
      {error ? (
        // role="alert" as well as aria-describedby: the description is read
        // when the field is reached, and the alert is read when the message
        // appears, which is what a mentor who pressed Continue needs.
        <p
          id={errorId}
          role="alert"
          className="mt-1.5 text-sm font-medium text-caution-700"
        >
          {error}
        </p>
      ) : null}
    </>
  );
}

function describedBy(
  hintId: string,
  errorId: string,
  hint?: ReactNode,
  error?: string,
): string | undefined {
  const ids = [hint ? hintId : null, error ? errorId : null].filter(Boolean);
  return ids.length > 0 ? ids.join(" ") : undefined;
}

export function FieldLabel({
  htmlFor,
  children,
  optional,
}: {
  htmlFor: string;
  children: ReactNode;
  optional?: boolean;
}) {
  return (
    <label htmlFor={htmlFor} className="block text-sm font-semibold text-ink">
      {children}
      {optional ? (
        <span className="ml-1 font-normal text-ink-soft">(optional)</span>
      ) : null}
    </label>
  );
}

interface TextProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  hint?: ReactNode;
  optional?: boolean;
  placeholder?: string;
  maxLength?: number;
  type?: "text" | "email";
  autoComplete?: string;
  name?: string;
}

export function TextInput({
  label,
  value,
  onChange,
  error,
  hint,
  optional,
  placeholder,
  maxLength,
  type = "text",
  autoComplete,
  name,
}: TextProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  return (
    <div>
      <FieldLabel htmlFor={id} optional={optional}>
        {label}
      </FieldLabel>
      <input
        id={id}
        name={name}
        type={type}
        className={`mt-1.5 ${controlClasses(Boolean(error))}`}
        value={value}
        placeholder={placeholder}
        maxLength={maxLength}
        autoComplete={autoComplete}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(hintId, errorId, hint, error)}
        onChange={(event) => onChange(event.target.value)}
      />
      <Describers hintId={hintId} errorId={errorId} hint={hint} error={error} />
    </div>
  );
}

export function TextArea({
  label,
  value,
  onChange,
  error,
  hint,
  optional,
  placeholder,
  maxLength,
  rows = 4,
  name,
}: Omit<TextProps, "type" | "autoComplete"> & { rows?: number }) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  return (
    <div>
      <FieldLabel htmlFor={id} optional={optional}>
        {label}
      </FieldLabel>
      <textarea
        id={id}
        name={name}
        rows={rows}
        className={`mt-1.5 ${controlClasses(Boolean(error))}`}
        value={value}
        placeholder={placeholder}
        maxLength={maxLength}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(hintId, errorId, hint, error)}
        onChange={(event) => onChange(event.target.value)}
      />
      <Describers hintId={hintId} errorId={errorId} hint={hint} error={error} />
    </div>
  );
}

/**
 * A dropdown whose value is always a string.
 *
 * The API publishes option ids as both strings and numbers, and a select
 * element has string values whatever they stand for, so the conversion
 * happens once, where the answer is read, rather than in four call sites.
 */
export function SelectInput({
  label,
  value,
  options,
  onChange,
  error,
  hint,
  optional,
  placeholder = "Choose one",
  name,
}: {
  label: string;
  value: string;
  options: readonly Option<string | number>[];
  onChange: (value: string) => void;
  error?: string;
  hint?: ReactNode;
  optional?: boolean;
  placeholder?: string;
  name?: string;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  return (
    <div>
      <FieldLabel htmlFor={id} optional={optional}>
        {label}
      </FieldLabel>
      <select
        id={id}
        name={name}
        className={`mt-1.5 ${controlClasses(Boolean(error))}`}
        value={value}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(hintId, errorId, hint, error)}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={String(option.id)} value={String(option.id)}>
            {option.label}
          </option>
        ))}
      </select>
      <Describers hintId={hintId} errorId={errorId} hint={hint} error={error} />
    </div>
  );
}

/** A set of choices small enough to show at once, as real radio buttons. */
export function RadioGroup({
  legend,
  value,
  options,
  onChange,
  error,
  hint,
}: {
  legend: string;
  value: string;
  options: readonly Option<string | number>[];
  onChange: (value: string) => void;
  error?: string;
  hint?: ReactNode;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  return (
    <fieldset aria-describedby={describedBy(hintId, errorId, hint, error)}>
      <legend className="text-sm font-semibold text-ink">{legend}</legend>
      <div className="mt-2 flex flex-wrap gap-2">
        {options.map((option) => {
          const checked = String(option.id) === String(value);
          return (
            <label
              key={String(option.id)}
              className={`flex min-h-[44px] cursor-pointer items-center gap-2 rounded-xl border px-4 py-2 text-sm font-medium ${
                checked
                  ? "border-accent-700 bg-accent-50 text-accent-800"
                  : "border-line bg-white text-ink-muted"
              }`}
            >
              <input
                type="radio"
                name={id}
                className="h-4 w-4 accent-accent-700"
                value={String(option.id)}
                checked={checked}
                onChange={(event) => onChange(event.target.value)}
              />
              {option.label}
            </label>
          );
        })}
      </div>
      <Describers hintId={hintId} errorId={errorId} hint={hint} error={error} />
    </fieldset>
  );
}

export function Toggle({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description?: ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className="flex items-start gap-3 rounded-xl border border-line bg-white p-4">
      <input
        id={id}
        type="checkbox"
        className="mt-0.5 h-5 w-5 shrink-0 accent-accent-700"
        checked={checked}
        aria-describedby={description ? hintId : undefined}
        onChange={(event) => onChange(event.target.checked)}
      />
      <div>
        <label htmlFor={id} className="block text-sm font-semibold text-ink">
          {label}
        </label>
        {description ? (
          <p id={hintId} className="mt-1 text-sm text-ink-soft">
            {description}
          </p>
        ) : null}
      </div>
    </div>
  );
}

/**
 * How many mentees can join one session.
 *
 * A stepper rather than a dropdown because the range is short and the
 * question is "how many", so the answer should feel like a quantity rather
 * than a category.
 *
 * The value carries role="spinbutton" and takes the arrow keys, Home and
 * End, which is the pattern a screen reader announces as adjustable. The two
 * buttons do the same job for a pointer, and both are disabled at the ends
 * rather than silently doing nothing.
 */
export function MenteeStepper({
  label,
  value,
  min,
  max,
  onChange,
  sessionLabel,
  error,
  hint,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
  sessionLabel: string;
  error?: string;
  hint?: ReactNode;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const labelId = `${id}-label`;

  const clamp = (next: number) => Math.min(max, Math.max(min, next));

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const moves: Record<string, number | undefined> = {
      ArrowUp: value + 1,
      ArrowRight: value + 1,
      ArrowDown: value - 1,
      ArrowLeft: value - 1,
      PageUp: value + 1,
      PageDown: value - 1,
      Home: min,
      End: max,
    };
    const next = moves[event.key];
    if (next === undefined) {
      return;
    }
    event.preventDefault();
    onChange(clamp(next));
  }

  return (
    <div>
      <p id={labelId} className="text-sm font-semibold text-ink">
        {label}
      </p>
      <div className="mt-2 flex items-center gap-3">
        <button
          type="button"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-line bg-white text-xl font-semibold text-ink-muted disabled:opacity-40"
          onClick={() => onChange(clamp(value - 1))}
          disabled={value <= min}
          aria-label="One fewer mentee"
        >
          <span aria-hidden="true">&minus;</span>
        </button>
        <div
          role="spinbutton"
          tabIndex={0}
          aria-labelledby={labelId}
          aria-valuenow={value}
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuetext={`${formatMentees(value)}, ${sessionLabel}`}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(hintId, errorId, hint, error)}
          onKeyDown={onKeyDown}
          className={`tabular flex min-h-[44px] flex-1 items-center justify-between gap-3 rounded-xl border bg-white px-4 py-2 ${
            error ? "border-caution-700" : "border-line"
          }`}
        >
          <span className="text-xl font-semibold">{value}</span>
          <span className="text-sm font-medium text-accent-800">{sessionLabel}</span>
        </div>
        <button
          type="button"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-line bg-white text-xl font-semibold text-ink-muted disabled:opacity-40"
          onClick={() => onChange(clamp(value + 1))}
          disabled={value >= max}
          aria-label="One more mentee"
        >
          <span aria-hidden="true">+</span>
        </button>
      </div>
      <Describers hintId={hintId} errorId={errorId} hint={hint} error={error} />
    </div>
  );
}

/**
 * The skills and topics a mentor offers.
 *
 * Checkboxes rather than a multiple select: thirty options is too many to
 * hold in a dropdown, and a checkbox is the one control every browser and
 * every assistive technology already agrees about.
 */
export function SkillChecklist({
  legend,
  options,
  selected,
  onToggle,
  error,
  hint,
}: {
  legend: string;
  options: Option[];
  selected: string[];
  onToggle: (id: string) => void;
  error?: string;
  hint?: ReactNode;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const chosen = new Set(selected);

  return (
    <fieldset aria-describedby={describedBy(hintId, errorId, hint, error)}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <legend className="text-sm font-semibold text-ink">{legend}</legend>
        <p aria-live="polite" className="text-sm text-ink-soft">
          {selected.length} chosen
        </p>
      </div>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        {options.map((option) => {
          const checked = chosen.has(option.id);
          return (
            <label
              key={option.id}
              className={`flex min-h-[44px] cursor-pointer items-center gap-3 rounded-xl border px-3.5 py-2 text-sm ${
                checked
                  ? "border-accent-700 bg-accent-50 text-accent-800"
                  : "border-line bg-white text-ink-muted"
              }`}
            >
              <input
                type="checkbox"
                className="h-4 w-4 shrink-0 accent-accent-700"
                checked={checked}
                onChange={() => onToggle(option.id)}
              />
              <span className="font-medium">{option.label}</span>
            </label>
          );
        })}
      </div>
      <Describers hintId={hintId} errorId={errorId} hint={hint} error={error} />
    </fieldset>
  );
}

/** Where the mentor is in a form with more than one step. */
export function ProgressSteps({
  steps,
  current,
}: {
  steps: string[];
  current: number;
}) {
  return (
    <nav aria-label="Registration progress" className="mb-6">
      <p className="text-sm font-semibold text-accent-700">
        Step {current + 1} of {steps.length}
      </p>
      <ol className="mt-2 flex flex-wrap gap-2">
        {steps.map((step, index) => {
          const done = index < current;
          const here = index === current;
          return (
            <li key={step} className="flex min-w-0 flex-1 basis-24 flex-col gap-1.5">
              <span
                aria-hidden="true"
                className={`h-1.5 rounded-full ${here || done ? "bg-accent-600" : "bg-line"}`}
              />
              <span
                className={`truncate text-xs font-medium ${
                  here ? "text-accent-800" : "text-ink-soft"
                }`}
              >
                {step}
                {here ? <span className="sr-only"> (current step)</span> : null}
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/**
 * The one place a form reports that something above needs changing.
 *
 * role="alert" so it is read as soon as it appears, and focusable so the code
 * that puts it there can move the mentor to it.
 */
export function FormErrorSummary({
  messages,
  id,
}: {
  messages: string[];
  id?: string;
}) {
  if (messages.length === 0) {
    return null;
  }
  return (
    <div
      id={id}
      role="alert"
      tabIndex={-1}
      className="rounded-xl border border-caution-200 bg-caution-50 p-4 text-sm text-caution-700"
    >
      <p className="font-semibold">Please check these answers</p>
      <ul className="mt-2 list-disc space-y-1 pl-5">
        {messages.map((message) => (
          <li key={message}>{message}</li>
        ))}
      </ul>
    </div>
  );
}
