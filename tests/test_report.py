"""
Tests for reading the training reports the dashboard displays.

Reports are gitignored, so every test here builds its own under ``tmp_path``.
"""

import json

import pytest

from src.config import REPORTS_DIR
from src.models.report import (
    comparison_rows,
    latest_report_path,
    load_latest_report,
    raw_feature_ranking,
)

INPUT_COLUMNS = [
    "accommodates",
    "number_of_reviews",
    "number_of_reviews_ltm",
    "room_type",
    "neighbourhood_cleansed",
]

REPORT = {
    "selection_metric": "rmse_dollars",
    "best_model": "XGBoost",
    "results": [
        {
            "model": "XGBoost",
            "metrics": {
                "rmse_dollars": 512.46,
                "mae_dollars": 131.36,
                "r2_dollars": 0.496,
            },
            "feature_importances": [
                {"feature": "room_type_Private room", "importance": 0.60},
                {"feature": "accommodates", "importance": 0.30},
                {"feature": "number_of_reviews_ltm", "importance": 0.10},
            ],
        },
        {
            "model": "Random Forest",
            "metrics": {
                "rmse_dollars": 550.33,
                "mae_dollars": 136.29,
                "r2_dollars": 0.419,
            },
            "feature_importances": [
                {"feature": "neighbourhood_cleansed_Burwood", "importance": 0.5},
                {"feature": "neighbourhood_cleansed_Sydney", "importance": 0.3},
                {"feature": "number_of_reviews", "importance": 0.2},
            ],
        },
        {
            "model": "Linear Regression (Ridge)",
            "metrics": {
                "rmse_dollars": 606.39,
                "mae_dollars": 169.20,
                "r2_dollars": 0.294,
            },
            "feature_importances": None,
        },
    ],
}


def write_report(directory, stamp: str, payload=None):
    path = directory / f"training_report_{stamp}.json"
    path.write_text(json.dumps(payload if payload is not None else REPORT), "utf-8")
    return path


# ---------------------------------------------------------------------------
# Finding and loading
# ---------------------------------------------------------------------------
def test_picks_the_newest_report_by_name(tmp_path):
    write_report(tmp_path, "20260101_000000")
    newest = write_report(tmp_path, "20260301_120000")
    write_report(tmp_path, "20260201_000000")

    assert latest_report_path(tmp_path) == newest


def test_no_report_directory_is_not_an_error(tmp_path):
    assert latest_report_path(tmp_path / "missing") is None
    assert load_latest_report(tmp_path / "missing") is None


def test_empty_report_directory_returns_none(tmp_path):
    assert load_latest_report(tmp_path) is None


def test_unrelated_files_are_ignored(tmp_path):
    (tmp_path / "notes.json").write_text("{}", encoding="utf-8")

    assert latest_report_path(tmp_path) is None


def test_malformed_report_returns_none(tmp_path):
    """A display concern must not stop the app serving predictions."""
    write_report(tmp_path, "20260101_000000")
    (tmp_path / "training_report_20260101_000000.json").write_text("{oops", "utf-8")

    assert load_latest_report(tmp_path) is None


def test_report_that_is_not_an_object_returns_none(tmp_path):
    write_report(tmp_path, "20260101_000000", payload=["not", "a", "report"])

    assert load_latest_report(tmp_path) is None


def test_loads_a_well_formed_report(tmp_path):
    write_report(tmp_path, "20260101_000000")

    assert load_latest_report(tmp_path)["best_model"] == "XGBoost"


# ---------------------------------------------------------------------------
# Comparison rows
# ---------------------------------------------------------------------------
def test_comparison_lists_every_model_ordered_by_the_selection_metric():
    rows = comparison_rows(REPORT)

    assert [row["model_name"] for row in rows] == [
        "XGBoost",
        "Random Forest",
        "Linear Regression (Ridge)",
    ]


def test_comparison_carries_rmse_mae_and_r2():
    row = comparison_rows(REPORT)[0]

    assert row["rmse_dollars"] == pytest.approx(512.46)
    assert row["mae_dollars"] == pytest.approx(131.36)
    assert row["r2_dollars"] == pytest.approx(0.496)


def test_comparison_marks_the_named_model_not_the_reports_best():
    """
    The served artefact decides what "selected" means, because the newest
    report may describe a run whose artefact was never deployed.
    """
    rows = comparison_rows(REPORT, selected_model="Random Forest")

    selected = [row["model_name"] for row in rows if row["is_selected"]]
    assert selected == ["Random Forest"]


def test_comparison_falls_back_to_the_reports_best_model():
    rows = comparison_rows(REPORT)

    assert [row["model_name"] for row in rows if row["is_selected"]] == ["XGBoost"]


def test_comparison_of_no_report_is_empty():
    assert comparison_rows(None) == []


def test_comparison_of_a_report_without_results_is_empty():
    assert comparison_rows({"best_model": "XGBoost"}) == []


def test_comparison_survives_a_missing_metric():
    rows = comparison_rows({"results": [{"model": "Partial", "metrics": {}}]})

    assert rows[0]["model_name"] == "Partial"
    assert rows[0]["mae_dollars"] != rows[0]["mae_dollars"]  # NaN


# ---------------------------------------------------------------------------
# Feature ranking
# ---------------------------------------------------------------------------
def test_ranking_folds_one_hot_levels_back_onto_their_column():
    """
    neighbourhood_cleansed scores 0.8 across two levels in the Random Forest,
    which must beat number_of_reviews at 0.2 in the same model.
    """
    ranking = raw_feature_ranking(REPORT, INPUT_COLUMNS)

    assert ranking.index("neighbourhood_cleansed") < ranking.index("number_of_reviews")


def test_ranking_is_ordered_by_summed_normalised_importance():
    ranking = raw_feature_ranking(REPORT, INPUT_COLUMNS)

    # room_type 0.60 and neighbourhood 0.80 lead; accommodates 0.30 follows.
    assert ranking[:2] == ["neighbourhood_cleansed", "room_type"]
    assert ranking.index("accommodates") < ranking.index("number_of_reviews_ltm")


def test_ranking_combines_every_model_that_reports_importances():
    ranking = raw_feature_ranking(REPORT, INPUT_COLUMNS)

    # XGBoost alone never mentions neighbourhood; Random Forest alone never
    # mentions room_type. Both must appear.
    assert {"room_type", "neighbourhood_cleansed"} <= set(ranking)


def test_ranking_ignores_columns_that_are_not_inputs():
    ranking = raw_feature_ranking(REPORT, ["accommodates"])

    assert ranking == ["accommodates"]


def test_ranking_does_not_confuse_a_prefix_for_a_one_hot_level():
    """
    number_of_reviews is a prefix of number_of_reviews_ltm. An exact match
    must win, or the two columns' importances would be merged.
    """
    report = {
        "results": [
            {
                "model": "m",
                "metrics": {},
                "feature_importances": [
                    {"feature": "number_of_reviews_ltm", "importance": 1.0}
                ],
            }
        ]
    }

    assert raw_feature_ranking(report, INPUT_COLUMNS) == ["number_of_reviews_ltm"]


def test_ranking_of_no_report_is_empty():
    assert raw_feature_ranking(None, INPUT_COLUMNS) == []


def test_ranking_of_a_report_without_importances_is_empty():
    report = {"results": [{"model": "Ridge", "metrics": {}}]}

    assert raw_feature_ranking(report, INPUT_COLUMNS) == []


def test_ranking_survives_all_zero_importances():
    report = {
        "results": [
            {
                "model": "m",
                "metrics": {},
                "feature_importances": [{"feature": "accommodates", "importance": 0.0}],
            }
        ]
    }

    assert raw_feature_ranking(report, INPUT_COLUMNS) == []


# ---------------------------------------------------------------------------
# The real reports directory, when a training run has happened
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    latest_report_path() is None,
    reason="no training report; run python -m src.models.train",
)
def test_the_real_report_ranks_the_configured_input_columns():
    from src.models.predict import load_best_model

    report = load_latest_report()
    model = load_best_model()

    ranking = raw_feature_ranking(report, model.input_columns)

    assert ranking
    assert set(ranking) <= set(model.input_columns)
    assert len(ranking) == len(set(ranking))


def test_reports_directory_is_inside_the_project():
    assert REPORTS_DIR.name == "reports"
