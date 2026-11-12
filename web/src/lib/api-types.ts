/**
 * The shapes the pricing API sends and accepts.
 *
 * Written by hand from the API's own OpenAPI document rather than generated,
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
 * The form never asks what kind of session it is. It asks how many people can
 * join, and the name follows: one is one to one, two or more is a group.
 */
export interface SessionLabelRule {
  one_to_one: { id: string; label: string; max_mentees: number };
  group: { id: string; label: string; max_mentees_from: number };
}

export interface Bounds {
  min: number;
  max: number;
}

export interface OptionsResponse {
  currency: string;
  fields: Option[];
  skills: Option[];
  max_mentees: Bounds;
  session_label_rule: SessionLabelRule;
  min_commitment: Option<number>[];
  min_commitment_default: number;
  years_mentoring_bands: Option[];
  years_experience: Bounds;
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
  years_experience: number | null;
  years_mentoring_band: string | null;
  verified: boolean;
  is_demo: boolean;
  services: Service[];
  history: HistorySummary | null;
  created_at: string;
}

/* ------------------------------------------------------------------ auth */

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegistrationPayload {
  name: string;
  email: string;
  password: string;
  field: string;
  max_mentees: number;
  skills: string[];
  min_commitment?: number;
  years_experience?: number | null;
  education_level?: string | null;
  credentials?: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  mentor: Mentor;
}

export interface RegistrationResponse extends TokenResponse {
  service: Service;
  recommendation: Recommendation;
}

/* -------------------------------------------------------------- directory */

/** One mentor as the public directory shows them. Carries no address. */
export interface MentorCard {
  id: number;
  display_name: string;
  field_label: string;
  service_name: string;
  price: number | null;
  max_mentees: number;
  session_label: string;
  verified: boolean;
  review_count: number;
  /**
   * What mentees rate this mentor overall, out of five, to one decimal
   * place, or null when the platform holds no rating for them. Null rather
   * than zero: a mentor nobody has rated has not been rated badly, so
   * nothing at all is shown in its place. One figure, never a series.
   */
  average_rating: number | null;
}

export interface MentorDirectory {
  total: number;
  limit: number;
  offset: number;
  items: MentorCard[];
}

export interface PublicMentor extends MentorCard {
  skills: Option[];
  years_experience: number | null;
  years_mentoring_band: string | null;
  education_level: string | null;
  education_label: string | null;
  credentials: string | null;
}

/* ---------------------------------------------------------------- preview */

export interface PreviewPayload {
  field: string;
  max_mentees: number;
  skills: string[];
}

export interface PreviewResponse {
  session_price: number;
  per_person_price: number;
  range_low: number;
  range_high: number;
  currency: string;
  low_confidence: boolean;
}

/* ----------------------------------------------------------------- prices */

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
  max_mentees: number;
  session_label: string;
  model_used: string;
  low_confidence: boolean;
  model_version: string;
  status: string;
  current_price: number | null;
  difference_vs_current_percent: number | null;
  position_vs_range: RangePosition | null;
  generated_at: string;
  decision: Decision | null;
}

export interface ServiceInputPayload {
  field: string;
  max_mentees: number;
  min_commitment: number;
  skills: string[];
}

export interface ServiceCreatedResponse {
  service: Service;
  recommendation: Recommendation;
}

/* ------------------------------------------------------------ comparables */

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

/**
 * The comparable mentors a chart is drawn from, and what they stand for.
 *
 * An evenly spread sample of the whole match by price rank, keeping the
 * cheapest and the dearest. `total` is how many mentors were matched and
 * `shown` how many are here, so a sentence above a chart can say which of the
 * two it means. The summary beside it is read from exactly these mentors, so
 * the band around the middle of the group is the quartiles of the points
 * drawn next to it.
 */
export interface PriceDistribution {
  total: number;
  shown: number;
  sampled: boolean;
  items: ComparableItem[];
}

/**
 * One thing about a mentor's answers, and what it does to their price.
 *
 * `effect_pct` is relative and the effects multiply rather than add, so the
 * baseline multiplied by every row below gives back the suggested price.
 * `direction` carries the sign in words, so nothing on the page has to rely
 * on a colour or an arrow alone to say which way a row goes.
 *
 * `association` marks the rows drawn from what the platform has measured
 * about a mentor with a record. Those are patterns among mentors who charge
 * alike rather than things the mentor did, and the sentence says so.
 */
/**
 * One measured theme behind a grouped row.
 *
 * A row about a mentor's record may stand for more than one thing. These are
 * the parts of it, shown in the numbers table rather than in the row itself,
 * so that saying two things in one sentence never amounts to hiding either
 * number.
 */
export interface FactorPart {
  key: string;
  label: string;
  effect_pct: number;
}

export interface PriceFactor {
  key: string;
  label: string;
  direction: "raises" | "lowers" | "little effect";
  effect_pct: number;
  sentence: string;
  association: boolean;
  components: FactorPart[];
}

export interface PriceDifference {
  key: string;
  label: string;
  sentence: string;
}

export interface PriceComparison {
  position: "below" | "within" | "above" | "unknown";
  percentile: number | null;
  median_price: number | null;
  band_low: number | null;
  band_high: number | null;
  compared_with: number;
  matched_total: number;
  match_description: string;
  sentence: string;
  /** Present only when the suggestion is outside the middle band. */
  explains_gap: string | null;
  differences: PriceDifference[];
}

export interface Explanation {
  recommendation_id: number;
  service_id: number;
  model_used: string;
  low_confidence: boolean;
  currency: string;
  baseline_price: number;
  baseline_sentence: string;
  /** The line between the typical price and the rows that move it. */
  summary_sentence: string;
  suggested_price: number;
  factors: PriceFactor[];
  other_small_effects: PriceFactor | null;
  combination_note: string;
  limitation: string;
  profile_note: string;
  comparison: PriceComparison;
}

export interface ComparablesResponse {
  summary: ComparablesSummary;
  histogram: PriceHistogram;
  /** What to plot and tabulate: the whole match, evenly reduced. */
  distribution: PriceDistribution;
  /**
   * A page of the match in whatever order was asked for. Right for "show me
   * the dearest ten", wrong for describing a market: the first page of a sort
   * is one end of it.
   */
  items: ComparableItem[];
  limit: number;
  offset: number;
}

export type ComparablesSort = "price" | "rating";
export type ComparablesOrder = "asc" | "desc";

/* -------------------------------------------------------------- decisions */

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

/* -------------------------------------------------------------- dashboard */

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

/** The one line the mentor's own page opens with. */
export interface DashboardHeadline {
  your_price: number | null;
  similar_typical: number | null;
  position_vs_range: RangePosition | null;
  sentence: string;
  currency: string;
}

/**
 * How booked a mentor is, beside the mentors they are compared with.
 *
 * Null for a mentor the platform has not measured, which is every new one.
 * A share invented for them would be the only figure on the page nobody
 * observed, so the card goes rather than showing a zero.
 */
export interface DemandComparison {
  position: "above" | "below" | "similar";
  booked_percent: number;
  typical_booked_percent: number;
  difference_points: number;
  compared_with: number;
  sentence: string;
}

export interface Dashboard {
  mentor_id: number;
  display_name: string;
  /** The mentor's overall rating out of five, or null when there is none. */
  average_rating: number | null;
  headline: DashboardHeadline;
  currency: string;
  comparables_available: boolean;
  demand: DemandComparison | null;
  totals: DashboardTotals;
  services: DashboardService[];
}

/**
 * A mentor's own months.
 *
 * The four lists are the same length as `months`. A measurement that does not
 * exist for a month is null rather than zero, which is not the same claim.
 */
export interface Activity {
  has_history: boolean;
  months: string[];
  reviews_by_month: number[];
  booked_share_by_month: (number | null)[];
  price_by_month: (number | null)[];
  currency: string;
  note: string;
}

/* ----------------------------------------------------------------- errors */

/** One answer the API wants changed, named as the form names it. */
export interface ApiFieldError {
  field: string;
  message: string;
}

export interface ApiErrorBody {
  detail: string;
  errors: ApiFieldError[];
}
