"""Tests for configuration and feature set definitions."""

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
