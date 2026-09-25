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
# Populated once the dataset schema is confirmed. Kept here so that the
# baseline vs. full feature-set comparison described in the hypothesis can be
# driven from a single definition rather than hard-coded in multiple places.
# ---------------------------------------------------------------------------
MENTOR_PROFILE_FEATURES: list[str] = []
MENTOR_PERFORMANCE_FEATURES: list[str] = []
DEMAND_INDICATOR_FEATURES: list[str] = []
MARKET_FEATURES: list[str] = []

TARGET_VARIABLE = "price"


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
