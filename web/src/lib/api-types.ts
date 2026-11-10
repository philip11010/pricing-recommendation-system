/**
 * The shapes the pricing API sends and accepts.
 *
 * Written by hand from the API's own OpenAPI schema rather than generated,
 * for one reason: the generated types carry the API's internal names for
 * things, and this file is the last place those names appear. Everything a
 * mentor reads is built from the labels the API sends alongside them.
 *
 * Every money figure is a whole number of AUD. The API rounds before it
 * sends, so nothing here divides a price again.
 */

/** One choice in a list the API publishes for the form to render. */
export interface Option<Id extends string | number = string> {
  id: Id;
  label: string;
}

/**
 * How a session is named, published as a rule rather than as a list.
 *
 * The form never asks what kind of session it is. It asks how many mentees
 * can join, and the name follows: one is one to one, two or more is a group.
 */
export interface SessionLabelRule {
  one_to_one: { id: string; label: string; max_mentees: number };
  group: { id: string; label: string; max_mentees_from: number };
}

export interface OptionsResponse {
  currency: string;
  fields: Option[];
  skills: Option[];
  max_mentees: { min: number; max: number };
  session_label_rule: SessionLabelRule;
  min_commitment: Option<number>[];
  years_mentoring_bands: Option[];
  services_planned: Option<number>[];
  education_levels: Option[];
}

export interface HealthResponse {
  status: string;
  models_loaded: boolean;
  comparables_loaded: boolean;
  model_version: string | null;
  trained_at: string | null;
  currency: string;
  detail: string | null;
}

export interface Service {
  id: number;
  mentor_id: number;
  session_label: string;
  field: string;
  max_mentees: number;
  min_commitment: number;
  skills: string[];
  profile_verified: boolean;
  current_price: number | null;
  created_at: string;
}

/** A mentor's track record, as much of it as a mentor would want to read. */
export interface HistorySummary {
  complete: boolean;
  top_rated_mentor: boolean | null;
  reviews_total: number | null;
  reviews_last_12_months: number | null;
  reviews_per_month: number | null;
  rating_overall: number | null;
  booked_share_90d: number | null;
  booked_share_365d: number | null;
  open_slots_next_year: number | null;
  days_since_last_review: number | null;
  years_since_first_review: number | null;
  tenure_years: number | null;
  updated_at: string;
}

export interface Mentor {
  id: number;
  full_name: string;
  email: string;
  headline: string | null;
  bio: string | null;
  education_level: string | null;
  experience_summary: string | null;
  credentials: string | null;
  years_mentoring_band: string;
  services_planned: number;
  is_demo: boolean;
  services: Service[];
  history: HistorySummary | null;
  created_at: string;
}

export interface DemoMentor {
  id: number;
  display_name: string;
  headline: string | null;
  field_label: string;
  session_label: string;
  has_history: boolean;
}

/** Where a mentor's current price sits against the advised range. */
export type RangePosition = "below" | "within" | "above";

export interface Recommendation {
  id: number;
  service_id: number;
  recommended_price: number;
  price_low: number;
  price_high: number;
  price_per_mentee: number;
  price_per_mentee_low: number;
  price_per_mentee_high: number;
  currency: string;
  model_used: string;
  low_confidence: boolean;
  model_version: string;
  status: string;
  current_price: number | null;
  difference_vs_current_percent: number | null;
  position_vs_range: RangePosition | null;
  generated_at: string;
}

export interface ServiceInputPayload {
  field: string;
  max_mentees: number;
  min_commitment: number;
  skills: string[];
  profile_verified: boolean;
}

export interface RegistrationPayload {
  full_name: string;
  email: string;
  years_mentoring_band: string;
  services_planned: number;
  headline: string | null;
  bio: string | null;
  education_level: string | null;
  experience_summary: string | null;
  credentials: string | null;
  service: ServiceInputPayload;
}

export interface RegistrationResponse {
  mentor: Mentor;
  service: Service;
  recommendation: Recommendation;
}

export interface ServiceCreatedResponse {
  service: Service;
  recommendation: Recommendation;
}

export interface ComparablesSummary {
  count: number;
  median_price: number | null;
  p25_price: number | null;
  p75_price: number | null;
  median_price_per_mentee: number | null;
  currency: string;
  match_level: number;
  widened: boolean;
  match_description: string;
}

export interface PriceHistogram {
  bin_edges: number[];
  counts: number[];
}

/** One mentor a price is compared against. Carries no name and no id. */
export interface ComparableItem {
  field_label: string;
  session_label: string;
  max_mentees: number;
  price: number;
  price_per_mentee: number;
  rating_overall: number;
  booked_share_percent: number;
  reviews_total: number;
}

export interface ComparablesResponse {
  summary: ComparablesSummary;
  histogram: PriceHistogram;
  items: ComparableItem[];
  limit: number;
  offset: number;
}

export type ComparablesSort = "price" | "rating";
export type ComparablesOrder = "asc" | "desc";

export type DecisionAction = "accepted" | "modified" | "rejected";

export interface DecisionPayload {
  action: DecisionAction;
  final_price?: number | null;
}

export interface Decision {
  id: number;
  recommendation_id: number;
  action: string;
  final_price: number | null;
  currency: string;
  decided_at: string;
}

export interface RecommendationHistoryItem {
  recommendation: Recommendation;
  decision: Decision | null;
}

export interface ServiceHistory {
  service_id: number;
  count: number;
  items: RecommendationHistoryItem[];
}

export interface DecisionCounts {
  accepted: number;
  modified: number;
  rejected: number;
  pending: number;
}

export interface TimelinePoint {
  generated_at: string;
  recommended_price: number;
  final_price: number | null;
  action: string | null;
}

export interface DashboardService {
  service_id: number;
  field_label: string;
  session_label: string;
  max_mentees: number;
  current_price: number | null;
  currency: string;
  latest_recommendation: Recommendation | null;
  position_vs_range: RangePosition | null;
  price_percentile: number | null;
  decision_counts: DecisionCounts;
  average_difference_percent: number | null;
  timeline: TimelinePoint[];
  comparables: ComparablesSummary | null;
}

export interface DashboardTotals {
  services: number;
  services_with_a_price: number;
  recommendations: number;
  decision_counts: DecisionCounts;
  average_difference_percent: number | null;
}

export interface Dashboard {
  mentor_id: number;
  display_name: string;
  currency: string;
  comparables_available: boolean;
  totals: DashboardTotals;
  services: DashboardService[];
}

/** One answer the API wants changed, named as the form names it. */
export interface ApiFieldError {
  field: string;
  message: string;
}

export interface ApiErrorBody {
  detail: string;
  errors: ApiFieldError[];
}
