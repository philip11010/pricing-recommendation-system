"""Tests for the feature preprocessing pipeline and custom transformers."""

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline

from src import config
from src.preprocessing import IQRCapper, build_preprocessor, split_feature_types

FEATURES = [
    "number_of_reviews",
    "accommodates",
    "review_scores_rating",
    "latitude",
    "room_type",
]


@pytest.fixture
def train_df():
    """
    Row 5 is an outlier in every continuous column. Only number_of_reviews
    is configured for capping, so only that column should be pulled in.
    """
    return pd.DataFrame(
        {
            "number_of_reviews": [1.0, 2.0, 3.0, 4.0, 5.0, 100.0, np.nan],
            "accommodates": [1.0, 2.0, 3.0, 4.0, 5.0, 16.0, np.nan],
            "review_scores_rating": [4.9, 4.8, 4.9, 4.7, 4.8, 1.0, np.nan],
            "latitude": [-33.9, -33.8, -33.7, -33.6, -33.5, -33.0, np.nan],
            "room_type": [
                "Entire home/apt",
                "Entire home/apt",
                "Private room",
                "Entire home/apt",
                np.nan,
                "Private room",
                "Entire home/apt",
            ],
            "price": [100.0, 120.0, 80.0, 150.0, 160.0, 900.0, 110.0],
        }
    )


def as_frame(preprocessor, X):
    return pd.DataFrame(
        preprocessor.transform(X), columns=preprocessor.get_feature_names_out()
    )


# ---------------------------------------------------------------------------
# IQRCapper
# ---------------------------------------------------------------------------
def test_iqr_capper_learns_tukey_bounds():
    X = np.array([[1.0], [2.0], [3.0], [4.0], [5.0]])  # Q1=2, Q3=4, IQR=2

    capper = IQRCapper(multiplier=1.5).fit(X)

    assert capper.lower_[0] == pytest.approx(-1.0)
    assert capper.upper_[0] == pytest.approx(7.0)


def test_iqr_capper_clips_only_values_outside_bounds():
    capper = IQRCapper().fit(np.array([[1.0], [2.0], [3.0], [4.0], [5.0]]))

    result = capper.transform(np.array([[-50.0], [3.0], [50.0]]))

    np.testing.assert_array_equal(result, [[-1.0], [3.0], [7.0]])


def test_iqr_capper_uses_fit_bounds_not_transform_data():
    """Prediction-time data must be capped with the training bounds."""
    capper = IQRCapper().fit(np.array([[1.0], [2.0], [3.0], [4.0], [5.0]]))

    result = capper.transform(np.array([[1000.0], [2000.0], [3000.0]]))

    np.testing.assert_array_equal(result, [[7.0], [7.0], [7.0]])


def test_iqr_capper_ignores_and_preserves_missing_values():
    capper = IQRCapper().fit(np.array([[1.0], [2.0], [np.nan], [4.0], [5.0]]))

    result = capper.transform(np.array([[np.nan], [100.0]]))

    assert np.isnan(result[0, 0])
    assert np.isfinite(capper.upper_[0])
    assert result[1, 0] == capper.upper_[0]


def test_iqr_capper_caps_each_column_independently():
    X = np.array([[1.0, 10.0], [2.0, 20.0], [3.0, 30.0], [4.0, 40.0], [5.0, 50.0]])

    capper = IQRCapper().fit(X)

    np.testing.assert_allclose(capper.lower_, [-1.0, -10.0])
    np.testing.assert_allclose(capper.upper_, [7.0, 70.0])


def test_iqr_capper_inverse_transform_returns_input_unchanged():
    capper = IQRCapper().fit(np.array([[1.0], [2.0], [3.0], [4.0], [5.0]]))

    result = capper.inverse_transform(np.array([[3.0], [50.0]]))

    np.testing.assert_array_equal(result, [[3.0], [50.0]])


def test_iqr_capper_rejects_negative_multiplier():
    with pytest.raises(ValueError):
        IQRCapper(multiplier=-1).fit(np.array([[1.0], [2.0]]))


def test_iqr_capper_keeps_feature_names():
    X = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})

    capper = IQRCapper().fit(X)

    assert list(capper.get_feature_names_out()) == ["a", "b"]


# ---------------------------------------------------------------------------
# Feature type split
# ---------------------------------------------------------------------------
def test_split_feature_types_routes_columns_by_config():
    capped, uncapped, categorical = split_feature_types(FEATURES)

    assert capped == ["number_of_reviews"]
    assert uncapped == ["accommodates", "review_scores_rating", "latitude"]
    assert categorical == ["room_type"]


@pytest.mark.parametrize(
    "feature_set", [config.baseline_feature_set, config.full_feature_set]
)
def test_split_feature_types_covers_every_feature_once(feature_set):
    features = feature_set()

    groups = split_feature_types(features)

    assert sorted(sum(groups, [])) == sorted(features)


def test_ratings_size_and_coordinates_are_never_capped():
    features = config.full_feature_set()
    exempt = [f for f in features if f.startswith("review_scores_")] + [
        "accommodates",
        "bedrooms",
        "beds",
        "latitude",
        "longitude",
    ]

    capped, _, _ = split_feature_types(features)

    assert set(capped).isdisjoint(exempt)


def test_skewed_counts_are_capped():
    capped, _, _ = split_feature_types(config.full_feature_set())

    assert "number_of_reviews" in capped
    assert "host_listings_count" in capped


# ---------------------------------------------------------------------------
# Full preprocessor
# ---------------------------------------------------------------------------
def test_preprocessor_output_has_no_missing_values(train_df):
    preprocessor = build_preprocessor(FEATURES).fit(train_df)

    result = preprocessor.transform(train_df)

    assert not np.isnan(result).any()


def test_preprocessor_scales_continuous_to_unit_range_on_training_data(train_df):
    preprocessor = build_preprocessor(FEATURES).fit(train_df)

    result = as_frame(preprocessor, train_df)

    for column in FEATURES[:-1]:
        assert result[column].min() == pytest.approx(0.0)
        assert result[column].max() == pytest.approx(1.0)


def test_preprocessor_caps_configured_column_before_scaling(train_df):
    """
    Without capping, the outlier (100) would squash every other value towards
    zero after Min-Max scaling. With capping, the typical values spread out.
    """
    preprocessor = build_preprocessor(FEATURES).fit(train_df)

    result = as_frame(preprocessor, train_df)

    assert result.loc[4, "number_of_reviews"] > 0.5


@pytest.mark.parametrize("column", ["accommodates", "review_scores_rating", "latitude"])
def test_preprocessor_scales_exempt_columns_without_capping(train_df, column):
    """
    Each exempt column contains a value Tukey fences would cap. Its scaled
    output must match plain Min-Max scaling of the raw training values.
    """
    preprocessor = build_preprocessor(FEATURES).fit(train_df)
    raw = train_df[column].iloc[:6]
    expected = (raw - raw.min()) / (raw.max() - raw.min())

    result = as_frame(preprocessor, train_df)[column].iloc[:6]

    np.testing.assert_allclose(result, expected)


def test_preprocessor_keeps_low_rating_distinct_from_typical_ratings(train_df):
    """A 1-star host must not be scaled up to look like a 4-star host."""
    preprocessor = build_preprocessor(FEATURES).fit(train_df)

    result = as_frame(preprocessor, train_df)["review_scores_rating"]

    assert result.loc[5] == pytest.approx(0.0)
    assert result.loc[[0, 1, 2, 3, 4]].min() > 0.9


def test_preprocessor_imputes_continuous_with_training_median(train_df):
    preprocessor = build_preprocessor(FEATURES).fit(train_df)
    median = train_df["accommodates"].median()

    imputed = as_frame(preprocessor, train_df).loc[6, "accommodates"]
    observed = as_frame(preprocessor, train_df.assign(accommodates=median)).loc[
        6, "accommodates"
    ]

    assert imputed == pytest.approx(observed)


def test_preprocessor_imputes_categorical_with_training_mode(train_df):
    preprocessor = build_preprocessor(FEATURES).fit(train_df)

    result = as_frame(preprocessor, train_df)["room_type_Private room"]

    # Row 4 is missing; the mode is "Entire home/apt", the reference level.
    assert result.loc[4] == 0.0
    assert result.loc[2] == 1.0


def test_preprocessor_one_hot_encodes_with_first_category_dropped(train_df):
    preprocessor = build_preprocessor(FEATURES).fit(train_df)

    names = list(preprocessor.get_feature_names_out())

    assert names == [
        "number_of_reviews",
        "accommodates",
        "review_scores_rating",
        "latitude",
        "room_type_Private room",
    ]


def test_preprocessor_output_is_not_collinear_with_intercept():
    """
    Regression test for the dummy-variable trap. A full one-hot block sums to
    1 on every row, duplicating the intercept, and LinearRegression then fits
    huge offsetting coefficients.
    """
    df = pd.DataFrame(
        {
            "accommodates": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
            "room_type": ["Entire home/apt", "Private room", "Shared room"] * 2,
            "host_is_superhost": ["t", "f", "f", "t", "t", "f"],
        }
    )
    encoded = build_preprocessor(list(df.columns)).fit_transform(df)
    with_intercept = np.column_stack([np.ones(len(df)), encoded])

    assert np.linalg.matrix_rank(with_intercept) == with_intercept.shape[1]


def test_preprocessor_treats_unseen_category_as_reference_level(train_df):
    preprocessor = build_preprocessor(FEATURES).fit(train_df)
    new = train_df.head(1).assign(room_type="Shared room")

    with pytest.warns(UserWarning, match="unknown categories"):
        result = as_frame(preprocessor, new)

    assert result["room_type_Private room"].iloc[0] == 0.0


def test_linear_model_prediction_stays_finite_for_unseen_category(train_df):
    """
    The failure seen on real data: an unseen category at prediction time
    produced a log-price prediction of ~1e13. With a reference level dropped,
    it must stay within a plausible range of the training targets.
    """
    pipeline = Pipeline(
        [("preprocess", build_preprocessor(FEATURES)), ("model", LinearRegression())]
    ).fit(train_df, train_df["price"])
    new = train_df.head(1).assign(room_type="Shared room")

    with pytest.warns(UserWarning, match="unknown categories"):
        prediction = pipeline.predict(new)[0]

    assert abs(prediction) < 10 * train_df["price"].max()


def test_preprocessor_applies_training_statistics_at_prediction_time(train_df):
    """
    A prediction-time row must be transformed with the statistics learned
    from training, independent of any other prediction-time rows.
    """
    preprocessor = build_preprocessor(FEATURES).fit(train_df)
    row = train_df.iloc[[2]]

    alone = preprocessor.transform(row)
    in_batch = preprocessor.transform(pd.concat([row, train_df.iloc[[5]]]))

    np.testing.assert_array_equal(alone[0], in_batch[0])


def test_preprocessor_drops_columns_outside_feature_list(train_df):
    preprocessor = build_preprocessor(FEATURES).fit(train_df)

    assert "price" not in preprocessor.get_feature_names_out()


def test_preprocessor_output_is_identical_after_saving_and_loading(train_df, tmp_path):
    """The artefact the API loads must reproduce training-time output."""
    preprocessor = build_preprocessor(FEATURES).fit(train_df)
    path = tmp_path / "preprocessor.joblib"
    joblib.dump(preprocessor, path)

    reloaded = joblib.load(path)

    np.testing.assert_array_equal(
        preprocessor.transform(train_df), reloaded.transform(train_df)
    )


def test_preprocessor_works_inside_grid_search(train_df):
    """
    GridSearchCV clones the pipeline and refits it per fold, which keeps each
    validation fold out of the preprocessing statistics.
    """
    pipeline = Pipeline(
        [("preprocess", build_preprocessor(FEATURES)), ("model", LinearRegression())]
    )
    search = GridSearchCV(
        pipeline,
        {"preprocess__capped__cap__multiplier": [1.5, 3.0]},
        cv=2,
        scoring="neg_root_mean_squared_error",
    )

    search.fit(train_df, train_df["price"])

    assert search.best_params_["preprocess__capped__cap__multiplier"] in (1.5, 3.0)


@pytest.mark.parametrize(
    "feature_set", [config.baseline_feature_set, config.full_feature_set]
)
def test_preprocessor_builds_for_both_ablation_arms(feature_set):
    preprocessor = build_preprocessor(feature_set())

    configured = [col for _, _, cols in preprocessor.transformers for col in cols]

    assert sorted(configured) == sorted(feature_set())
