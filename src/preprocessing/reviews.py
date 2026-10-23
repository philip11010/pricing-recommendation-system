"""
No-review handling.

About 2,792 of the 17,786 priced Sydney listings have never been reviewed.
Every review-derived column is missing for exactly those rows: the four
``review_scores_*`` columns used as features, and ``reviews_per_month``.

Median imputation is the wrong rule here. The missingness is structural, not
random: there is no hidden rating to estimate, because no guest has ever
rated the listing. Filling those rows with the training median would tell the
model that an unreviewed listing is an average-rated listing, which is the
single largest group in the dataset being misdescribed.

Instead:

- ``has_no_reviews`` records the condition explicitly, so a model can learn
  a separate price offset for unreviewed listings.
- Review scores are filled with a sentinel below the observed 1-5 range, so
  an unreviewed listing is never confused with a low-rated one. The flag is
  what carries the meaning; the sentinel only keeps the column numeric.
- ``reviews_per_month`` is filled with 0.0, which is its true value when
  there are no reviews, not a sentinel.

Both fill values are constants rather than learned statistics, so applying
them cannot leak information between folds or from test into train.

The step runs inside the fitted pipeline, ahead of the ColumnTransformer, so
training and prediction cannot drift apart.
"""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

from src.config import NO_REVIEWS_FLAG

# Review score columns in the Inside Airbnb schema. Only those also present
# in the frame are touched, so the step works on the feature subset as well
# as the full listings table.
REVIEW_SCORE_COLUMNS: list[str] = [
    "review_scores_rating",
    "review_scores_accuracy",
    "review_scores_cleanliness",
    "review_scores_checkin",
    "review_scores_communication",
    "review_scores_location",
    "review_scores_value",
]

# Columns whose genuine value is zero when a listing has no reviews.
REVIEW_RATE_COLUMNS: list[str] = ["reviews_per_month"]

REVIEW_COUNT_COLUMN = "number_of_reviews"

# Below the observed 1-5 rating range, so unreviewed listings stay separable
# from the worst-rated reviewed ones after Min-Max scaling.
NO_REVIEW_SCORE_FILL = 0.0
NO_REVIEW_RATE_FILL = 0.0


def flag_no_reviews(df: pd.DataFrame) -> pd.Series:
    """
    Return a 0/1 Series marking listings with no review history.

    A listing counts as unreviewed when ``number_of_reviews`` is zero or
    missing. If that column is absent, a missing ``review_scores_rating`` is
    used as the fallback signal.
    """
    if REVIEW_COUNT_COLUMN in df.columns:
        counts = pd.to_numeric(df[REVIEW_COUNT_COLUMN], errors="coerce")
        flag = counts.isna() | (counts <= 0)
    elif "review_scores_rating" in df.columns:
        flag = df["review_scores_rating"].isna()
    else:
        flag = pd.Series(False, index=df.index)
    return flag.astype(np.float64).rename(NO_REVIEWS_FLAG)


def add_no_reviews_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add ``has_no_reviews`` and fill the review columns for unreviewed rows.

    Review columns that are missing for a *reviewed* listing are left as NaN,
    so the preprocessor's median imputation still handles genuine, random
    missingness. Only structurally missing values are filled here.

    Args:
        df: Any frame containing some or all of the review columns.

    Returns:
        A copy with the flag column added and the structural gaps filled.
    """
    out = df.copy()
    flag = flag_no_reviews(out)
    out[NO_REVIEWS_FLAG] = flag
    unreviewed = flag.astype(bool)

    for column in REVIEW_SCORE_COLUMNS:
        if column in out.columns:
            filled = pd.to_numeric(out[column], errors="coerce")
            out[column] = filled.mask(unreviewed, NO_REVIEW_SCORE_FILL)

    for column in REVIEW_RATE_COLUMNS:
        if column in out.columns:
            filled = pd.to_numeric(out[column], errors="coerce")
            out[column] = filled.mask(unreviewed, NO_REVIEW_RATE_FILL)

    return out


class NoReviewsIndicator(BaseEstimator, TransformerMixin):
    """
    Pipeline step wrapping :func:`add_no_reviews_features`.

    Stateless: both fill values are constants, so ``fit`` learns nothing and
    the transform applied to a validation fold or to a prediction-time row is
    identical to the one applied during training. It is still a fitted
    estimator so it can sit in a ``Pipeline`` ahead of the ColumnTransformer
    and be saved with the rest of the artefact.

    Input and output are DataFrames, because the ColumnTransformer that
    follows selects columns by name.
    """

    def fit(self, X, y=None):
        if not isinstance(X, pd.DataFrame):
            raise TypeError(
                f"{type(self).__name__} needs a DataFrame, got {type(X).__name__}"
            )
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        self.n_features_in_ = X.shape[1]
        return self

    def transform(self, X):
        if not isinstance(X, pd.DataFrame):
            raise TypeError(
                f"{type(self).__name__} needs a DataFrame, got {type(X).__name__}"
            )
        return add_no_reviews_features(X)

    def get_feature_names_out(self, input_features=None):
        if input_features is None:
            input_features = getattr(self, "feature_names_in_", [])
        names = list(input_features)
        if NO_REVIEWS_FLAG not in names:
            names.append(NO_REVIEWS_FLAG)
        return np.asarray(names, dtype=object)
