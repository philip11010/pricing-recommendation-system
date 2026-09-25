"""
Central configuration for the pricing recommendation system.

All paths, constants, and experiment parameters live here rather than being
scattered through the codebase. This supports the reproducibility requirement
stated in Section 4.2.3 of the proposal.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
MODEL_STORE_DIR = PROJECT_ROOT / "models_store"

for _directory in (RAW_DATA_DIR, PROCESSED_DATA_DIR, MODEL_STORE_DIR):
    _directory.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
RANDOM_SEED = 42

# ---------------------------------------------------------------------------
# Experiment parameters (Section 3.2.2 / 3.2.3)
# ---------------------------------------------------------------------------
TEST_SIZE = 0.20  # 80/20 train/test split
CV_FOLDS = 10  # 10-fold cross-validation (Raschka, 2016)

# ---------------------------------------------------------------------------
# Feature categories (Section 2.2.3 / conceptual framework)
#
# Kept here so that the baseline vs. full feature-set comparison described in
# the hypothesis can be driven from a single definition rather than hard-coded
# in multiple places.
#
# Column names are from the Inside Airbnb proxy dataset. Each column belongs to
# exactly one category. Excluded after EDA:
#   - fully empty in the snapshot: host_since, host_verifications,
#     host_response_rate, host_acceptance_rate, host_response_time
#   - target leakage: see TARGET_LEAKAGE_COLUMNS below
#   - redundant: estimated_occupancy_l365d (derived from review counts,
#     duplicates number_of_reviews_ltm), availability_60
#   - property_type: it nests room_type ("Shared room in home" etc.), so after
#     one-hot encoding the room_type columns are exact sums of property_type
#     columns. LinearRegression then fits huge offsetting coefficients, and
#     any unseen property type at prediction time (common: 66 levels, many
#     with one listing) breaks the offset and the prediction overflows.
#     room_type keeps the coarse signal with only 4 stable levels.
# ---------------------------------------------------------------------------
MENTOR_PROFILE_FEATURES: list[str] = [
    # Experience is split into whole years plus remaining months (0-11), so
    # both parts are needed: total months = years * 12 + months.
    "hosts_time_as_host_years",
    "hosts_time_as_host_months",
    "host_identity_verified",  # certification analogue
    "host_has_profile_pic",
    "host_listings_count",
    "room_type",  # specialisation analogue
    "accommodates",
    "bedrooms",
    "bathrooms",
    "beds",
]
MENTOR_PERFORMANCE_FEATURES: list[str] = [
    "review_scores_rating",
    "review_scores_accuracy",
    "review_scores_communication",
    "review_scores_value",
    "number_of_reviews",
    "host_is_superhost",  # awarded on rating and reliability metrics
]
DEMAND_INDICATOR_FEATURES: list[str] = [
    "availability_30",
    "availability_90",
    "availability_365",
    "number_of_reviews_ltm",  # booking-request proxy
    "number_of_reviews_l30d",
    "reviews_per_month",  # booking velocity, so demand rather than performance
]
MARKET_FEATURES: list[str] = [
    # Location stands in for "similar mentors". Neighbourhood average price
    # must be derived inside each CV fold to avoid leaking the target.
    "neighbourhood_cleansed",
    "latitude",
    "longitude",
]

TARGET_VARIABLE = "price"

# Columns computed from the listed price. Using any of them as a feature lets
# the model read the answer: estimated_revenue_l365d equals
# estimated_occupancy_l365d x price for every listing with occupancy, and
# price_quote_price_per_night equals price for every priced listing. The rest
# of the price_quote_* family comes from the same quote.
TARGET_LEAKAGE_COLUMNS: list[str] = [
    "estimated_revenue_l365d",
    "price_quote_price_per_night",
    "price_quote_total_price",
    "price_quote_raw",
    "price_quote_checkin_date",
    "price_quote_checkout_date",
]

# ---------------------------------------------------------------------------
# Preprocessing
#
# Every feature not listed as categorical is treated as continuous.
#
# IQR capping is opt-in. It is applied only to heavily right-skewed counts,
# where a handful of extreme values would otherwise compress everyone else
# into a sliver of the Min-Max range. Deliberately left uncapped:
#   - rating columns: low scores are rare but real, and capping at ~4.3 would
#     make a 1-star host indistinguishable from a 4.3-star one
#   - size (accommodates, bedrooms, beds): large properties are the expensive
#     ones, so capping would remove the strongest price signal
#   - coordinates: an outlying latitude is a real location, not an error
#   - bounded variables (experience, availability): Tukey fences fall outside
#     their range, so capping would be a no-op
#
# The target is capped separately, on the log scale, in
# src/preprocessing/target.py.
# ---------------------------------------------------------------------------
CATEGORICAL_FEATURES: list[str] = [
    "host_identity_verified",
    "host_has_profile_pic",
    "host_is_superhost",
    "room_type",
    "neighbourhood_cleansed",
]
CAPPED_FEATURES: list[str] = [
    "host_listings_count",
    "bathrooms",
    "number_of_reviews",
    "number_of_reviews_ltm",
    "number_of_reviews_l30d",
    "reviews_per_month",
]
IQR_MULTIPLIER = 1.5


def full_feature_set() -> list[str]:
    """All four input categories, used for the full model."""
    return (
        MENTOR_PROFILE_FEATURES
        + MENTOR_PERFORMANCE_FEATURES
        + DEMAND_INDICATOR_FEATURES
        + MARKET_FEATURES
    )


def baseline_feature_set() -> list[str]:
    """
    Profile and performance features only, excluding demand indicators and
    market variables. Used as the baseline arm of the ablation study that
    tests whether demand-responsive features improve predictive accuracy.
    """
    return MENTOR_PROFILE_FEATURES + MENTOR_PERFORMANCE_FEATURES
