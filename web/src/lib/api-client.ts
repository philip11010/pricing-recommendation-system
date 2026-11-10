/**
 * The one place this application talks to the pricing API.
 *
 * Everything goes through `request`, so there is a single place that adds the
 * identity header, a single place that turns a refusal into an `ApiError` with
 * the API's field messages intact, and a single place that notices the API is
 * not answering at all.
 *
 * There is no authentication yet. A mentor-scoped call states which mentor it
 * is for in the `X-Mentor-Id` header, and the API answers 404 rather than 403
 * for another mentor's record, so nothing can be learned by asking.
 */

import { ApiError, NETWORK_MESSAGE, NetworkError, UNEXPECTED_MESSAGE } from "./errors";
import type {
  ApiErrorBody,
  ComparablesOrder,
  ComparablesResponse,
  ComparablesSort,
  Dashboard,
  Decision,
  DecisionPayload,
  DemoMentor,
  HealthResponse,
  Mentor,
  OptionsResponse,
  Recommendation,
  RegistrationPayload,
  RegistrationResponse,
  ServiceCreatedResponse,
  ServiceHistory,
  ServiceInputPayload,
} from "./api-types";

export const MENTOR_ID_HEADER = "X-Mentor-Id";

const DEFAULT_API_URL = "http://127.0.0.1:8000";

/** The API address, without a trailing slash so paths join cleanly. */
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL).replace(
  /\/+$/,
  "",
);

type QueryValue = string | number | boolean | undefined;

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  /** Set on every mentor-scoped call. Omitted only where the API allows it. */
  mentorId?: number;
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined) {
      search.set(key, String(value));
    }
  }
  const suffix = search.toString();
  return `${API_URL}${path}${suffix ? `?${suffix}` : ""}`;
}

async function errorBodyOf(response: Response): Promise<ApiErrorBody> {
  try {
    const parsed: unknown = await response.json();
    if (parsed && typeof parsed === "object" && "detail" in parsed) {
      const body = parsed as Partial<ApiErrorBody>;
      return {
        detail: typeof body.detail === "string" ? body.detail : UNEXPECTED_MESSAGE,
        errors: Array.isArray(body.errors) ? body.errors : [],
      };
    }
  } catch {
    // The API documents one error body and sends it everywhere. A response
    // that is not it means something in front of the API answered instead, so
    // there is nothing to read and a generic sentence is the honest one.
  }
  return { detail: UNEXPECTED_MESSAGE, errors: [] };
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, mentorId, query, signal } = options;

  const headers: Record<string, string> = {};
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (mentorId !== undefined) {
    headers[MENTOR_ID_HEADER] = String(mentorId);
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
      cache: "no-store",
    });
  } catch (error) {
    // An aborted request is this application changing its mind, not a
    // failure, so it is rethrown for the caller to ignore.
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new NetworkError(NETWORK_MESSAGE);
  }

  if (!response.ok) {
    throw new ApiError(response.status, await errorBodyOf(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new NetworkError(UNEXPECTED_MESSAGE);
  }
}

export const api = {
  health(signal?: AbortSignal) {
    return request<HealthResponse>("/health", { signal });
  },

  /** Every option list the form renders. No identity needed. */
  options(signal?: AbortSignal) {
    return request<OptionsResponse>("/meta/options", { signal });
  },

  register(payload: RegistrationPayload, signal?: AbortSignal) {
    return request<RegistrationResponse>("/mentors", {
      method: "POST",
      body: payload,
      signal,
    });
  },

  /**
   * The mentors seeded for the demonstration.
   *
   * The one mentor-related call with no identity header: it is the list an
   * identity is picked from, so requiring one would be circular.
   */
  demoMentors(signal?: AbortSignal) {
    return request<DemoMentor[]>("/mentors/demo", { signal });
  },

  mentor(mentorId: number, signal?: AbortSignal) {
    return request<Mentor>(`/mentors/${mentorId}`, { mentorId, signal });
  },

  dashboard(mentorId: number, signal?: AbortSignal) {
    return request<Dashboard>(`/mentors/${mentorId}/dashboard`, { mentorId, signal });
  },

  addService(mentorId: number, payload: ServiceInputPayload, signal?: AbortSignal) {
    return request<ServiceCreatedResponse>(`/mentors/${mentorId}/services`, {
      method: "POST",
      body: payload,
      mentorId,
      signal,
    });
  },

  /** Ask for a fresh price for a service the mentor already offers. */
  createRecommendation(mentorId: number, serviceId: number, signal?: AbortSignal) {
    return request<Recommendation>(`/services/${serviceId}/recommendations`, {
      method: "POST",
      mentorId,
      signal,
    });
  },

  recommendation(mentorId: number, recommendationId: number, signal?: AbortSignal) {
    return request<Recommendation>(`/recommendations/${recommendationId}`, {
      mentorId,
      signal,
    });
  },

  comparables(
    mentorId: number,
    serviceId: number,
    params: {
      sort?: ComparablesSort;
      order?: ComparablesOrder;
      limit?: number;
      offset?: number;
    } = {},
    signal?: AbortSignal,
  ) {
    return request<ComparablesResponse>(`/services/${serviceId}/comparables`, {
      mentorId,
      query: { ...params },
      signal,
    });
  },

  history(mentorId: number, serviceId: number, signal?: AbortSignal) {
    return request<ServiceHistory>(`/services/${serviceId}/history`, {
      mentorId,
      signal,
    });
  },

  decide(
    mentorId: number,
    recommendationId: number,
    payload: DecisionPayload,
    signal?: AbortSignal,
  ) {
    return request<Decision>(`/recommendations/${recommendationId}/decision`, {
      method: "POST",
      body: payload,
      mentorId,
      signal,
    });
  },
};
