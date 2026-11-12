/**
 * The one place this application talks to the pricing API.
 *
 * Everything goes through `request`, so there is a single place that attaches
 * the access token, a single place that turns a refusal into an `ApiError`
 * with the API's field messages intact, a single place that notices the API
 * is not answering at all, and a single place that reacts to the API saying
 * the token is no longer good.
 */

import { ApiError, NETWORK_MESSAGE, NetworkError, UNEXPECTED_MESSAGE } from "./errors";
import { handleUnauthorized, readToken } from "./token";
import type {
  Activity,
  ApiErrorBody,
  ComparablesOrder,
  ComparablesResponse,
  ComparablesSort,
  Dashboard,
  Decision,
  DecisionPayload,
  Explanation,
  HealthResponse,
  LoginPayload,
  Mentor,
  MentorDirectory,
  OptionsResponse,
  PreviewPayload,
  PreviewResponse,
  PublicMentor,
  Recommendation,
  RegistrationPayload,
  RegistrationResponse,
  Service,
  ServiceCreatedResponse,
  ServiceHistory,
  ServiceInputPayload,
  TokenResponse,
} from "./api-types";

const DEFAULT_API_URL = "http://127.0.0.1:8000";

/** The API address, without a trailing slash so paths join cleanly. */
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL).replace(
  /\/+$/,
  "",
);

type QueryValue = string | number | boolean | undefined;

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH";
  body?: unknown;
  /** Set on every call the API wants a token for. */
  auth?: boolean;
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
  /**
   * Whether a 401 should sign this browser out.
   *
   * True everywhere except the log in attempt itself, where a refusal means
   * the password was wrong rather than that a session ended.
   */
  signOutOn401?: boolean;
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
  const {
    method = "GET",
    body,
    auth = false,
    query,
    signal,
    signOutOn401 = true,
  } = options;

  const headers: Record<string, string> = {};
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (auth) {
    const token = readToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
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
    const failure = new ApiError(response.status, await errorBodyOf(response));
    if (response.status === 401 && signOutOn401) {
      handleUnauthorized();
    }
    throw failure;
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

  /** Every option list the form renders. No token needed. */
  options(signal?: AbortSignal) {
    return request<OptionsResponse>("/meta/options", { signal });
  },

  /* ------------------------------------------------------------- public */

  directory(
    params: {
      field?: string;
      group?: string;
      limit?: number;
      offset?: number;
    } = {},
    signal?: AbortSignal,
  ) {
    return request<MentorDirectory>("/mentors", { query: { ...params }, signal });
  },

  publicMentor(mentorId: number, signal?: AbortSignal) {
    return request<PublicMentor>(`/mentors/${mentorId}/public`, { signal });
  },

  /** A price for a part filled form. Writes nothing and needs no account. */
  preview(payload: PreviewPayload, signal?: AbortSignal) {
    return request<PreviewResponse>("/preview", {
      method: "POST",
      body: payload,
      signal,
    });
  },

  /* --------------------------------------------------------------- auth */

  register(payload: RegistrationPayload, signal?: AbortSignal) {
    return request<RegistrationResponse>("/auth/register", {
      method: "POST",
      body: payload,
      signal,
    });
  },

  login(payload: LoginPayload, signal?: AbortSignal) {
    return request<TokenResponse>("/auth/login", {
      method: "POST",
      body: payload,
      signal,
      // A refusal here is a wrong password, which the form reports itself.
      signOutOn401: false,
    });
  },

  me(signal?: AbortSignal) {
    return request<Mentor>("/auth/me", { auth: true, signal });
  },

  /* ----------------------------------------------------------- services */

  service(serviceId: number, signal?: AbortSignal) {
    return request<Service>(`/services/${serviceId}`, { auth: true, signal });
  },

  addService(mentorId: number, payload: ServiceInputPayload, signal?: AbortSignal) {
    return request<ServiceCreatedResponse>(`/mentors/${mentorId}/services`, {
      method: "POST",
      body: payload,
      auth: true,
      signal,
    });
  },

  /** Ask for a fresh price for a service the mentor already offers. */
  createRecommendation(serviceId: number, signal?: AbortSignal) {
    return request<Recommendation>(`/services/${serviceId}/recommendations`, {
      method: "POST",
      auth: true,
      signal,
    });
  },

  recommendation(recommendationId: number, signal?: AbortSignal) {
    return request<Recommendation>(`/recommendations/${recommendationId}`, {
      auth: true,
      signal,
    });
  },

  /**
   * Why one price was suggested.
   *
   * A request of its own rather than part of the recommendation, so the
   * price screen is useful before it arrives and stays useful if it fails.
   */
  explanation(recommendationId: number, signal?: AbortSignal) {
    return request<Explanation>(`/recommendations/${recommendationId}/explanation`, {
      auth: true,
      signal,
    });
  },

  comparables(
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
      auth: true,
      query: { ...params },
      signal,
    });
  },

  history(serviceId: number, signal?: AbortSignal) {
    return request<ServiceHistory>(`/services/${serviceId}/history`, {
      auth: true,
      signal,
    });
  },

  decide(recommendationId: number, payload: DecisionPayload, signal?: AbortSignal) {
    return request<Decision>(`/recommendations/${recommendationId}/decision`, {
      method: "POST",
      body: payload,
      auth: true,
      signal,
    });
  },

  /* ---------------------------------------------------------- the mentor */

  dashboard(mentorId: number, signal?: AbortSignal) {
    return request<Dashboard>(`/mentors/${mentorId}/dashboard`, {
      auth: true,
      signal,
    });
  },

  activity(mentorId: number, signal?: AbortSignal) {
    return request<Activity>(`/mentors/${mentorId}/activity`, {
      auth: true,
      signal,
    });
  },
};
