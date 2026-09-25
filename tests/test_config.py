"""Tests for configuration and feature set definitions."""

import pytest

from src import config


def test_random_seed_is_fixed():
    """Reproducibility requires a fixed seed (Section 4.2.3)."""
    assert config.RANDOM_SEED == 42


def test_cv_folds_is_ten():
    """10-fold cross-validation is specified in Section 3.2.3."""
    assert config.CV_FOLDS == 10


def test_test_size_is_twenty_percent():
    """80/20 train/test split is specified in Section 3.2.2."""
    assert config.TEST_SIZE == 0.20


def test_baseline_is_subset_of_full_feature_set():
    """
    The baseline arm of the ablation study must be a strict subset of the
    full feature set, otherwise the comparison is not valid.
    """
    baseline = set(config.baseline_feature_set())
    full = set(config.full_feature_set())
    assert baseline.issubset(full)


def test_baseline_excludes_demand_features():
    """
    The hypothesis tests whether demand features improve accuracy, so the
    baseline must not contain them.
    """
    baseline = set(config.baseline_feature_set())
    demand = set(config.DEMAND_INDICATOR_FEATURES)
    assert baseline.isdisjoint(demand)


def test_feature_categories_do_not_overlap():
    """
    Each column must belong to one category only, otherwise a feature could
    appear in both ablation arms or be counted twice in the full set.
    """
    full = config.full_feature_set()
    assert len(full) == len(set(full))


def test_preprocessing_lists_only_name_known_features():
    """A typo here would silently route a column to the wrong branch."""
    full = set(config.full_feature_set())
    assert set(config.CATEGORICAL_FEATURES).issubset(full)
    assert set(config.CAPPED_FEATURES).issubset(full)


def test_capped_features_are_continuous():
    assert set(config.CAPPED_FEATURES).isdisjoint(config.CATEGORICAL_FEATURES)


@pytest.mark.parametrize(
    "feature_set", [config.baseline_feature_set, config.full_feature_set]
)
def test_feature_sets_exclude_target_leakage(feature_set):
    """
    Columns derived from price would let the model read the answer, so they
    must be absent from both ablation arms.
    """
    features = set(feature_set())
    assert features.isdisjoint(config.TARGET_LEAKAGE_COLUMNS)
    assert config.TARGET_VARIABLE not in features


def test_nested_categoricals_are_not_both_used():
    """
    property_type nests room_type, which makes their one-hot columns exactly
    collinear. Only one of them may be a feature.
    """
    full = set(config.full_feature_set())
    assert not {"property_type", "room_type"}.issubset(full)


def test_known_leaking_columns_are_listed():
    assert "estimated_revenue_l365d" in config.TARGET_LEAKAGE_COLUMNS
    assert "price_quote_price_per_night" in config.TARGET_LEAKAGE_COLUMNS
