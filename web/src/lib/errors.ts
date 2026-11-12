/**
 * What went wrong, in words a mentor can act on.
 *
 * The API answers every failure with the same body: a sentence in `detail`
 * and a list of `{field, message}` pairs in `errors`. Two kinds of failure
 * never arrive that way, and both are handled here so that no page has to:
 * the network not reaching the API at all, and the API answering something
 * that is not the documented body.
 */

import type { ApiErrorBody, ApiFieldError } from "./api-types";

/** The API answered, and said no. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly fieldErrors: ApiFieldError[];

  constructor(status: number, body: ApiErrorBody) {
    super(body.detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = body.detail;
    this.fieldErrors = body.errors ?? [];
  }
}

/**
 * The request never got an answer.
 *
 * Almost always the API not running, which is worth saying outright: the
 * browser's own message for a failed fetch is "Failed to fetch", and nobody
 * has ever acted on that.
 */
export class NetworkError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NetworkError";
  }
}

export const NETWORK_MESSAGE =
  "We could not reach the pricing service. Check that it is running, then try again.";

export const UNEXPECTED_MESSAGE =
  "Something went wrong at our end. Please try again in a moment.";

/** Every answer the form sends, named as the API names it. */
export const KNOWN_FIELDS = [
  "name",
  "email",
  "password",
  "field",
  "max_mentees",
  "min_commitment",
  "skills",
  "years_experience",
  "education_level",
  "credentials",
  "headline",
  "bio",
  "experience_summary",
  "action",
  "final_price",
] as const;

export type KnownField = (typeof KNOWN_FIELDS)[number];

const KNOWN = new Set<string>(KNOWN_FIELDS);

export interface FieldErrorMap {
  /** One message per field, keyed by the name the form uses. */
  fields: Record<string, string>;
  /** Messages with no field to attach them to, shown above the form. */
  general: string[];
}

/**
 * Turn the API's list into something a form can render.
 *
 * Three rules, each for a case that actually happens:
 *
 * * A message about a field the form does not render has nowhere to go, so it
 *   is shown above the form rather than dropped. A mentor who cannot see why
 *   their submission was refused will try the same thing again.
 * * The first message for a field wins. A single input showing two
 *   contradictory sentences is worse than showing the first one.
 * * An error list that is empty, or missing, falls back to the sentence the
 *   API sent with it, so there is always something to read.
 */
export function toFieldErrors(
  errors: ApiFieldError[] | undefined,
  detail?: string,
): FieldErrorMap {
  const fields: Record<string, string> = {};
  const general: string[] = [];

  for (const error of errors ?? []) {
    const name = (error?.field ?? "").trim();
    const message = (error?.message ?? "").trim();
    if (!message) {
      continue;
    }
    if (name && KNOWN.has(name)) {
      if (!(name in fields)) {
        fields[name] = message;
      }
      continue;
    }
    const labelled = name ? `${name}: ${message}` : message;
    if (!general.includes(labelled)) {
      general.push(labelled);
    }
  }

  if (Object.keys(fields).length === 0 && general.length === 0 && detail) {
    general.push(detail);
  }

  return { fields, general };
}

/** The sentence to show for any failure, whatever kind it turned out to be. */
export function messageFor(error: unknown): string {
  if (error instanceof NetworkError) {
    return error.message;
  }
  if (error instanceof ApiError) {
    return error.detail || UNEXPECTED_MESSAGE;
  }
  return UNEXPECTED_MESSAGE;
}

/** True when the API said this record does not exist, or is not ours. */
export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

/** True when the API said this price has already been answered. */
export function isAlreadyDecided(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409;
}

/** True when the API said who we are, or are not. */
export function isUnauthenticated(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

/** True when the API has not been given the models or the comparison table. */
export function isUnprepared(error: unknown): boolean {
  return error instanceof ApiError && error.status === 503;
}
