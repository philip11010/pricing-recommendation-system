"use client";

/**
 * Every field in the product, built the same way.
 *
 * Top to bottom, always in this order: a visible label bound to the input,
 * helper text above the input so it is read before the field is answered, the
 * input itself, and a message under it tied to the input with
 * aria-describedby. A placeholder is never the label.
 *
 * A fixed height slot is reserved for the message, so showing one does not
 * push the rest of the form down.
 */

import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from "react";

import { WarningIcon } from "@/components/ui";
import type { Option } from "@/lib/api-types";

const INPUT_CLASS =
  "w-full min-h-[44px] rounded-field border border-line bg-surface px-3.5 py-2.5 text-base text-ink-900 hover:border-line-strong disabled:bg-surface-sunk";

export function FieldShell({
  id,
  label,
  helper,
  error,
  children,
  labelFor = true,
}: {
  id: string;
  label: ReactNode;
  helper?: ReactNode;
  error?: string | null;
  children: ReactNode;
  /** False where the control is a group rather than one input. */
  labelFor?: boolean;
}) {
  const helperId = `${id}-helper`;
  const errorId = `${id}-error`;
  return (
    <div className="mt-5">
      {labelFor ? (
        <label htmlFor={id} className="block text-label font-semibold">
          {label}
        </label>
      ) : (
        <span className="block text-label font-semibold">{label}</span>
      )}
      {helper ? (
        <span id={helperId} className="mb-2 mt-0.5 block text-small text-ink-500">
          {helper}
        </span>
      ) : null}
      {children}
      <div className="min-h-[1.5rem] pt-1">
        {error ? (
          <p
            id={errorId}
            role="alert"
            className="flex items-start gap-1.5 text-small text-danger-700"
          >
            <WarningIcon className="mt-0.5 h-4 w-4 flex-none" />
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function describedBy(id: string, helper: unknown, error: unknown): string | undefined {
  const parts = [helper ? `${id}-helper` : null, error ? `${id}-error` : null].filter(
    Boolean,
  );
  return parts.length > 0 ? parts.join(" ") : undefined;
}

export interface TextInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: ReactNode;
  helper?: ReactNode;
  error?: string | null;
  id?: string;
}

export const TextInput = forwardRef<HTMLInputElement, TextInputProps>(
  function TextInput({ label, helper, error, id, className = "", ...rest }, ref) {
    const generated = useId();
    const fieldId = id ?? generated;
    return (
      <FieldShell id={fieldId} label={label} helper={helper} error={error}>
        <input
          ref={ref}
          id={fieldId}
          className={`${INPUT_CLASS} ${className}`}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(fieldId, helper, error)}
          {...rest}
        />
      </FieldShell>
    );
  },
);

export interface SelectInputProps
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> {
  label: ReactNode;
  helper?: ReactNode;
  error?: string | null;
  options: Option<string | number>[];
  placeholder?: string;
  id?: string;
}

export const SelectInput = forwardRef<HTMLSelectElement, SelectInputProps>(
  function SelectInput(
    { label, helper, error, options, placeholder, id, className = "", ...rest },
    ref,
  ) {
    const generated = useId();
    const fieldId = id ?? generated;
    return (
      <FieldShell id={fieldId} label={label} helper={helper} error={error}>
        <select
          ref={ref}
          id={fieldId}
          className={`${INPUT_CLASS} ${className}`}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(fieldId, helper, error)}
          {...rest}
        >
          {placeholder ? <option value="">{placeholder}</option> : null}
          {options.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </select>
      </FieldShell>
    );
  },
);

/**
 * A small bounded number, such as how many people are in a session.
 *
 * A pill shaped group with a minus, an output announced politely and a plus.
 * The buttons clamp at the ends of the range rather than disappearing, so the
 * control does not change shape as it is used.
 */
export function Stepper({
  label,
  helper,
  value,
  min,
  max,
  onChange,
  describe,
  error,
  id: givenId,
  decreaseLabel = "Fewer people",
  increaseLabel = "More people",
}: {
  label: ReactNode;
  helper?: ReactNode;
  value: number;
  min: number;
  max: number;
  onChange: (next: number) => void;
  /** How the current value is read out, for example "4 people". */
  describe: (value: number) => string;
  error?: string | null;
  id?: string;
  decreaseLabel?: string;
  increaseLabel?: string;
}) {
  const generated = useId();
  const id = givenId ?? generated;
  return (
    <FieldShell id={id} label={label} helper={helper} error={error} labelFor={false}>
      <div className="inline-flex items-center gap-3 rounded-pill border border-line p-1">
        <button
          type="button"
          aria-label={decreaseLabel}
          disabled={value <= min}
          onClick={() => onChange(Math.max(min, value - 1))}
          className="h-11 w-11 cursor-pointer rounded-pill bg-accent-100 text-xl font-bold text-accent-800 transition-colors duration-[180ms] ease-entrance hover:bg-tint-indigo disabled:cursor-not-allowed disabled:opacity-60 mid:h-10 mid:w-10"
        >
          &minus;
        </button>
        <output
          id={id}
          aria-live="polite"
          className="min-w-[72px] text-center font-bold"
        >
          {describe(value)}
        </output>
        <button
          type="button"
          aria-label={increaseLabel}
          disabled={value >= max}
          onClick={() => onChange(Math.min(max, value + 1))}
          className="h-11 w-11 cursor-pointer rounded-pill bg-accent-100 text-xl font-bold text-accent-800 transition-colors duration-[180ms] ease-entrance hover:bg-tint-indigo disabled:cursor-not-allowed disabled:opacity-60 mid:h-10 mid:w-10"
        >
          +
        </button>
      </div>
    </FieldShell>
  );
}

/**
 * One of a set of choices.
 *
 * A real checkbox that is visually hidden but still focusable, with the pill
 * as its label. A chosen pill changes fill, border and weight together, so
 * the selection is not carried by colour alone.
 */
export function PillCheckbox({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <label className="relative inline-flex cursor-pointer">
      <input
        type="checkbox"
        className="absolute h-px w-px opacity-0"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span
        className={`inline-flex min-h-[44px] items-center rounded-pill border px-4 py-2 text-[0.9375rem] transition-colors duration-[180ms] ease-entrance mid:min-h-[40px] ${
          checked
            ? "border-accent-700 bg-accent-100 font-semibold text-accent-800"
            : "border-line font-medium text-ink-700 hover:border-line-strong hover:bg-surface-sunk"
        }`}
      >
        {label}
      </span>
    </label>
  );
}

export interface SummaryProblem {
  /** The id of the field to jump to. */
  id: string;
  message: string;
}

/**
 * Everything wrong with the form, at the top of it.
 *
 * It complements the inline messages and never replaces them. Focus is moved
 * here on a failed submit, and each line is a link to the field it is about.
 */
export const ErrorSummary = forwardRef<HTMLDivElement, { problems: SummaryProblem[] }>(
  function ErrorSummary({ problems }, ref) {
    if (problems.length === 0) {
      return null;
    }
    return (
      <div
        ref={ref}
        role="alert"
        tabIndex={-1}
        className="mb-6 rounded-card border border-line bg-danger-fill p-6 text-danger-700"
      >
        <h2 className="text-h3 font-semibold">
          {problems.length === 1
            ? "One answer needs changing"
            : `${problems.length} answers need changing`}
        </h2>
        <ul className="mt-3 list-disc space-y-1 pl-5">
          {problems.map((problem) => (
            <li key={`${problem.id}-${problem.message}`}>
              <a
                href={`#${problem.id}`}
                className="font-semibold underline underline-offset-[3px]"
              >
                {problem.message}
              </a>
            </li>
          ))}
        </ul>
      </div>
    );
  },
);
