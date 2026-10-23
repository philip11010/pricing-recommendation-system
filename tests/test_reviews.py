"""
Tests for structural no-review handling.

The property under test throughout: an unreviewed listing must never be
represented as an averagely-rated listing, and must stay distinguishable from
a genuinely low-rated one.
"""

import numpy as np
import pandas as pd
import pytest
from sklearn.pipeline import Pipeline

from src import config
from src.preprocessing import (
    NO_REVIEW_RATE_FILL,
    NO_REVIEW_SCORE_FILL,
    NO_REVIEWS_FLAG,
    NoReviewsIndicator,
    add_no_reviews_features,
    build_preprocessor,
    flag_no_reviews,
)

REVIEW_FEATURES = [
    "number_of_reviews",
    "review_scores_rating",
    "review_scores_value",
    "reviews_per_month",
    NO_REVIEWS_FLAG,
]


@pytest.fixture
def listings():
    """
    Rows 0-2 are reviewed, rows 3-4 are unreviewed, row 5 is reviewed but
    has one genuinely missing score (random missingness, not structural).
    """
    return pd.DataFrame(
        {
            "number_of_reviews": [10.0, 50.0, 3.0, 0.0, 0.0, 20.0],
            "review_scores_rating": [4.9, 4.8, 1.2, np.nan, np.nan, np.nan],
            "review_scores_value": [4.8, 4.7, 1.5, np.nan, np.nan, 4.6],
            "reviews_per_month": [1.2, 3.4, 0.2, np.nan, np.nan, 2.0],
        }
    )


# ---------------------------------------------------------------------------
# flag_no_reviews
# ---------------------------------------------------------------------------
def test_flag_marks_zero_review_listings(listings):
    flag = flag_no_reviews(listings)

    np.testing.assert_array_equal(flag.to_numpy(), [0.0, 0.0, 0.0, 1.0, 1.0, 0.0])


def test_flag_is_named_for_the_configured_column(listings):
    assert flag_no_reviews(listings).name == NO_REVIEWS_FLAG
    assert NO_REVIEWS_FLAG == "has_no_reviews"


def test_flag_treats_missing_review_count_as_no_reviews():
    df = pd.DataFrame({"number_of_reviews": [np.nan, 5.0]})

    np.testing.assert_array_equal(flag_no_reviews(df).to_numpy(), [1.0, 0.0])


def test_flag_falls_back_to_missing_rating_without_a_count_column():
    df = pd.DataFrame({"review_scores_rating": [np.nan, 4.5]})

    np.testing.assert_array_equal(flag_no_reviews(df).to_numpy(), [1.0, 0.0])


def test_flag_is_all_zero_when_no_review_columns_exist():
    df = pd.DataFrame({"accommodates": [1, 2]})

    np.testing.assert_array_equal(flag_no_reviews(df).to_numpy(), [0.0, 0.0])


# ---------------------------------------------------------------------------
# add_no_reviews_features
# ---------------------------------------------------------------------------
def test_adds_the_flag_column(listings):
    result = add_no_reviews_features(listings)

    assert NO_REVIEWS_FLAG in result.columns


def test_fills_review_scores_for_unreviewed_rows_with_the_sentinel(listings):
    result = add_no_reviews_features(listings)

    assert result.loc[[3, 4], "review_scores_rating"].tolist() == [
        NO_REVIEW_SCORE_FILL,
        NO_REVIEW_SCORE_FILL,
    ]
    assert result.loc[[3, 4], "review_scores_value"].tolist() == [
        NO_REVIEW_SCORE_FILL,
        NO_REVIEW_SCORE_FILL,
    ]


def test_fills_reviews_per_month_with_zero_for_unreviewed_rows(listings):
    """Zero is the true rate for a listing with no reviews, not a sentinel."""
    result = add_no_reviews_features(listings)

    assert result.loc[[3, 4], "reviews_per_month"].tolist() == [
        NO_REVIEW_RATE_FILL,
        NO_REVIEW_RATE_FILL,
    ]


def test_sentinel_sits_below_the_observed_rating_range(listings):
    """
    The whole point of the sentinel: an unreviewed listing must not land in
    the middle of the rating distribution, and must not be confused with the
    worst-rated reviewed listing either.
    """
    result = add_no_reviews_features(listings)
    reviewed = result.loc[result[NO_REVIEWS_FLAG] == 0, "review_scores_rating"]

    assert NO_REVIEW_SCORE_FILL < reviewed.min()


def test_does_not_fill_random_missingness_for_a_reviewed_listing(listings):
    """
    Row 5 has 20 reviews but a missing rating. That is ordinary missingness,
    so it stays NaN here and is median-imputed by the preprocessor instead.
    """
    result = add_no_reviews_features(listings)

    assert np.isnan(result.loc[5, "review_scores_rating"])


def test_unreviewed_rows_are_not_given_the_median_rating(listings):
    """
    The regression this module exists to prevent. Median imputation of the
    review scores would place every unreviewed listing at the centre of the
    rating distribution.
    """
    median = listings["review_scores_rating"].median()

    result = add_no_reviews_features(listings)

    assert (result.loc[[3, 4], "review_scores_rating"] != median).all()


def test_leaves_the_input_frame_unchanged(listings):
    before = listings.copy()

    add_no_reviews_features(listings)

    pd.testing.assert_frame_equal(listings, before)


def test_other_columns_pass_through_untouched():
    df = pd.DataFrame({"number_of_reviews": [0.0, 4.0], "accommodates": [2.0, np.nan]})

    result = add_no_reviews_features(df)

    assert result.loc[0, "accommodates"] == 2.0
    assert np.isnan(result.loc[1, "accommodates"])


def test_is_idempotent(listings):
    once = add_no_reviews_features(listings)

    twice = add_no_reviews_features(once)

    pd.testing.assert_frame_equal(once, twice)


# ---------------------------------------------------------------------------
# NoReviewsIndicator
# ---------------------------------------------------------------------------
def test_indicator_transform_matches_the_function(listings):
    indicator = NoReviewsIndicator().fit(listings)

    pd.testing.assert_frame_equal(
        indicator.transform(listings), add_no_reviews_features(listings)
    )


def test_indicator_returns_a_dataframe_for_the_column_transformer(listings):
    result = NoReviewsIndicator().fit_transform(listings)

    assert isinstance(result, pd.DataFrame)


def test_indicator_announces_the_flag_in_its_output_names(listings):
    indicator = NoReviewsIndicator().fit(listings)

    names = list(indicator.get_feature_names_out())

    assert names[-1] == NO_REVIEWS_FLAG
    assert names[: len(listings.columns)] == list(listings.columns)


def test_indicator_is_stateless_across_differing_batches(listings):
    """
    Fill values are constants, so a single row must transform identically
    whether it arrives alone or inside a batch. This is what makes the step
    safe to run inside a CV loop.
    """
    indicator = NoReviewsIndicator().fit(listings)
    row = listings.iloc[[3]]

    alone = indicator.transform(row)
    in_batch = indicator.transform(listings).iloc[[3]]

    pd.testing.assert_frame_equal(alone, in_batch)


def test_indicator_rejects_array_input(listings):
    with pytest.raises(TypeError):
        NoReviewsIndicator().fit(listings.to_numpy())


# ---------------------------------------------------------------------------
# Config wiring
# ---------------------------------------------------------------------------
def test_flag_is_in_both_feature_sets():
    assert NO_REVIEWS_FLAG in config.full_feature_set()
    assert NO_REVIEWS_FLAG in config.baseline_feature_set()


def test_flag_is_a_performance_feature():
    assert NO_REVIEWS_FLAG in config.MENTOR_PERFORMANCE_FEATURES


def test_flag_is_never_iqr_capped():
    """Capping a 0/1 indicator at Tukey fences could erase a rare class."""
    assert NO_REVIEWS_FLAG not in config.CAPPED_FEATURES


# ---------------------------------------------------------------------------
# End to end through the preprocessor
# ---------------------------------------------------------------------------
def preprocessed(listings):
    pipeline = Pipeline(
        [
            ("reviews", NoReviewsIndicator()),
            ("preprocess", build_preprocessor(REVIEW_FEATURES)),
        ]
    ).fit(listings)
    return pd.DataFrame(
        pipeline.transform(listings),
        columns=pipeline.named_steps["preprocess"].get_feature_names_out(),
    )


def test_flag_survives_the_preprocessor_as_a_zero_one_column(listings):
    transformed = preprocessed(listings)

    assert set(transformed[NO_REVIEWS_FLAG].unique()) == {0.0, 1.0}


def test_preprocessed_unreviewed_rows_differ_from_low_rated_rows(listings):
    """
    After scaling, an unreviewed listing and a 1.2-star listing must not land
    on the same rating value.
    """
    transformed = preprocessed(listings)

    unreviewed = transformed.loc[3, "review_scores_rating"]
    low_rated = transformed.loc[2, "review_scores_rating"]
    assert unreviewed != pytest.approx(low_rated)


def test_preprocessed_output_has_no_missing_values(listings):
    pipeline = Pipeline(
        [
            ("reviews", NoReviewsIndicator()),
            ("preprocess", build_preprocessor(REVIEW_FEATURES)),
        ]
    ).fit(listings)

    assert not np.isnan(pipeline.transform(listings)).any()
