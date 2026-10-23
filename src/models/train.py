"""
ML Model component: train, tune and compare the three candidate models.

Run with::

    python -m src.models.train

What it does, in the order the methodology requires:

1. Load the raw listings table, parse the price target and drop the
   target-leakage columns listed in ``src.config``.
2. Take the target to the log scale. Price is strongly right-skewed, so a
   model fitted on dollars is dominated by a handful of very expensive
   listings. Every reported dollar figure comes from converting predictions
   back with ``exp``, so the metrics stay in the units a mentor cares about.
3. Split 80/20 with ``RANDOM_SEED``. The test set is touched exactly once,
   after tuning.
4. For each of Ridge, Random Forest and XGBoost, run ``GridSearchCV`` with
   ``CV_FOLDS`` folds on the training set only. Scoring is RMSE on the log
   scale, which is the scale the models are fitted on.
5. Score each tuned model once on the held-out test set, save the artefacts
   and write a timestamped report.

Feature preparation sits inside the ``Pipeline`` handed to ``GridSearchCV``,
so imputation statistics, capping bounds, scaler ranges and one-hot
categories are refitted on each training fold and never see the validation
fold. The target transform is a fixed function with no fitted parameters, so
applying it before the split cannot leak anything either.

Grids are deliberately small. The target machine is a 6-core Ryzen 5 with
8 GB RAM, so ``GridSearchCV`` itself runs single-process and the parallelism
is left to the estimators, which share one copy of the data instead of
holding one copy per worker.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV, KFold, train_test_split
from sklearn.pipeline import Pipeline
from xgboost import XGBRegressor

from src.config import (
    CV_FOLDS,
    MODEL_STORE_DIR,
    PROJECT_ROOT,
    RANDOM_SEED,
    TARGET_LEAKAGE_COLUMNS,
    TEST_SIZE,
    full_feature_set,
)
from src.data.loader import load_raw_csv
from src.preprocessing import NoReviewsIndicator, build_preprocessor
from src.preprocessing.target import split_features_and_target

RAW_FILENAME = "listings.csv.gz"
DATA_SOURCE = "Inside Airbnb Sydney (proxy)"
TARGET_DESCRIPTION = "log(price)"
REPORTS_DIR = PROJECT_ROOT / "reports"
TOP_IMPORTANCES = 15
BEST_MODEL_FILENAME = "best_model.joblib"
BEST_METADATA_FILENAME = "best_model_metadata.json"

# Scoring is on the log scale because that is the scale the estimators are
# fitted on. Dollar metrics are computed afterwards, from the test set only.
CV_SCORING = "neg_root_mean_squared_error"

# Selection criterion. Section 3.2.3 names RMSE as primary, and the price a
# mentor sees is in dollars, so the dollar-scale figure decides.
SELECTION_METRIC = "rmse_dollars"


@dataclass
class ModelSpec:
    """A candidate model and the grid searched over it."""

    key: str
    label: str
    estimator: Any
    param_grid: dict[str, list] = field(default_factory=dict)

    @property
    def n_candidates(self) -> int:
        total = 1
        for values in self.param_grid.values():
            total *= len(values)
        return total


def model_specs() -> list[ModelSpec]:
    """
    The three candidate models of Section 3.2.3.

    Grid keys address the ``model`` step of the pipeline built by
    :func:`build_model_pipeline`.
    """
    return [
        ModelSpec(
            key="ridge",
            # Linear Regression is implemented as Ridge (L2), per Section
            # 3.2.3. The one-hot neighbourhood columns are near-collinear,
            # which an unpenalised fit turns into unstable coefficients.
            label="Linear Regression (Ridge)",
            estimator=Ridge(random_state=RANDOM_SEED),
            param_grid={"model__alpha": [0.01, 0.1, 1, 10, 100]},
        ),
        ModelSpec(
            key="random_forest",
            label="Random Forest",
            estimator=RandomForestRegressor(random_state=RANDOM_SEED, n_jobs=-1),
            param_grid={
                "model__n_estimators": [100, 200],
                "model__max_depth": [10, 20],
                "model__min_samples_leaf": [1, 5],
            },
        ),
        ModelSpec(
            key="xgboost",
            label="XGBoost",
            estimator=XGBRegressor(
                tree_method="hist",
                random_state=RANDOM_SEED,
                n_jobs=-1,
                verbosity=0,
            ),
            param_grid={
                "model__n_estimators": [200, 400],
                "model__max_depth": [4, 6],
                "model__learning_rate": [0.05, 0.1],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Target scale
# ---------------------------------------------------------------------------
def to_log_price(prices: np.ndarray | pd.Series) -> np.ndarray:
    """
    Map prices in dollars to the log scale the models are fitted on.

    Raises:
        ValueError: If any price is not strictly positive. ``log`` is
            undefined there, and a non-positive listed price is a data error
            rather than something to silently shift away.
    """
    values = np.asarray(prices, dtype=np.float64)
    if values.size and np.any(values <= 0):
        raise ValueError("prices must be strictly positive to take log(price)")
    return np.log(values)


def to_dollars(log_prices: np.ndarray) -> np.ndarray:
    """Invert :func:`to_log_price`, returning dollars."""
    return np.exp(np.asarray(log_prices, dtype=np.float64))


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def load_dataset(filename: str = RAW_FILENAME) -> tuple[pd.DataFrame, pd.Series]:
    """
    Load the raw table, parse the price target and drop leaking columns.

    Rows without a usable price are dropped by
    :func:`split_features_and_target`. Rows whose price is not strictly
    positive are dropped here, because the log target cannot represent them.

    Returns:
        ``(X, y)`` where ``y`` is price in dollars.
    """
    df = load_raw_csv(filename)
    X, y = split_features_and_target(df)

    usable = y > 0
    X, y = X.loc[usable], y.loc[usable]

    leaking = [column for column in TARGET_LEAKAGE_COLUMNS if column in X.columns]
    return X.drop(columns=leaking), y


def build_model_pipeline(estimator: Any, features: list[str]) -> Pipeline:
    """
    Wrap one estimator with the shared preprocessing steps.

    ``NoReviewsIndicator`` runs first so that ``has_no_reviews`` exists as a
    column before the ColumnTransformer selects features by name.
    """
    return Pipeline(
        [
            ("reviews", NoReviewsIndicator()),
            ("preprocess", build_preprocessor(features)),
            ("model", estimator),
        ]
    )


# ---------------------------------------------------------------------------
# Tuning and evaluation
# ---------------------------------------------------------------------------
def tune(
    spec: ModelSpec,
    features: list[str],
    X_train: pd.DataFrame,
    y_log_train: np.ndarray,
    cv_folds: int = CV_FOLDS,
) -> GridSearchCV:
    """
    Grid-search one model on the training set only.

    ``n_jobs=1`` on the search itself: the estimators already use every core,
    and parallelising the outer loop as well would hold one copy of the
    training fold per worker, which is what exhausts 8 GB of RAM.
    """
    search = GridSearchCV(
        build_model_pipeline(spec.estimator, features),
        spec.param_grid,
        cv=KFold(n_splits=cv_folds, shuffle=True, random_state=RANDOM_SEED),
        scoring=CV_SCORING,
        n_jobs=1,
        refit=True,
        error_score="raise",
    )
    search.fit(X_train, y_log_train)
    return search


def evaluate(
    search: GridSearchCV, X_test: pd.DataFrame, y_test: pd.Series
) -> dict[str, float]:
    """
    Score a tuned model once on the held-out test set.

    RMSE in dollars is the primary criterion (Section 3.2.3). It is computed
    after converting predictions back with ``exp``, not by exponentiating a
    log-scale error: those are different quantities.

    Also records the cross-validated log RMSE for the selected parameters, so
    the models can be ranked without reference to the test set.
    """
    y_dollars = np.asarray(y_test, dtype=np.float64)
    predicted_log = np.asarray(search.predict(X_test), dtype=np.float64)
    predicted_dollars = to_dollars(predicted_log)
    actual_log = to_log_price(y_dollars)

    best = search.best_index_
    return {
        "rmse_dollars": float(
            np.sqrt(mean_squared_error(y_dollars, predicted_dollars))
        ),
        "mae_dollars": float(mean_absolute_error(y_dollars, predicted_dollars)),
        "r2_dollars": float(r2_score(y_dollars, predicted_dollars)),
        "rmse_log": float(np.sqrt(mean_squared_error(actual_log, predicted_log))),
        "cv_rmse_log_mean": float(-search.cv_results_["mean_test_score"][best]),
        "cv_rmse_log_std": float(search.cv_results_["std_test_score"][best]),
    }


def preprocessed_feature_names(search: GridSearchCV) -> list[str]:
    """Column names the model actually sees, after encoding and scaling."""
    preprocess = search.best_estimator_.named_steps["preprocess"]
    return [str(name) for name in preprocess.get_feature_names_out()]


def top_feature_importances(
    search: GridSearchCV, top_n: int = TOP_IMPORTANCES
) -> list[dict[str, Any]] | None:
    """
    The ``top_n`` largest tree importances, or None for a model without them.

    Importances are reported against the preprocessed column names, so each
    one-hot level appears under its own name.
    """
    model = search.best_estimator_.named_steps["model"]
    importances = getattr(model, "feature_importances_", None)
    if importances is None:
        return None

    ranked = sorted(
        zip(preprocessed_feature_names(search), np.asarray(importances, float)),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return [
        {"feature": name, "importance": float(value)} for name, value in ranked[:top_n]
    ]


def readable_params(params: dict[str, Any]) -> dict[str, Any]:
    """Strip the ``model__`` pipeline prefix for display."""
    return {key.removeprefix("model__"): value for key, value in params.items()}


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------
def run_experiment(
    X: pd.DataFrame,
    y: pd.Series,
    features: list[str] | None = None,
    specs: list[ModelSpec] | None = None,
    cv_folds: int = CV_FOLDS,
    model_dir: Path = MODEL_STORE_DIR,
    report_dir: Path = REPORTS_DIR,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """
    Tune, evaluate, persist and report every candidate model.

    Args:
        X: Features in dollars-free form, as returned by :func:`load_dataset`.
        y: Price in dollars.
        features: Columns to use. Defaults to ``full_feature_set()``.
        specs: Candidate models. Defaults to :func:`model_specs`.
        cv_folds: Folds for the inner search. Defaults to ``CV_FOLDS``.
        model_dir: Where the fitted pipelines and metadata are written.
        report_dir: Where the JSON and markdown reports are written.
        timestamp: Run time, used in the report filenames.

    Returns:
        The report dictionary that was written as JSON.
    """
    features = list(full_feature_set() if features is None else features)
    specs = model_specs() if specs is None else specs
    timestamp = datetime.now() if timestamp is None else timestamp
    model_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_SEED
    )
    y_log_train = to_log_price(y_train)

    print(
        f"Rows: {len(X):,} total, {len(X_train):,} train, {len(X_test):,} test\n"
        f"Features: {len(features)} configured columns\n"
        f"Target: {TARGET_DESCRIPTION}, cross-validation: {cv_folds}-fold\n"
    )

    results: list[dict[str, Any]] = []
    # Every pipeline shares one preprocessor configuration, so the encoded
    # column names are the same for all three; record them once.
    feature_names: list[str] = []
    for position, spec in enumerate(specs, start=1):
        print(
            f"[{position}/{len(specs)}] {spec.label}: "
            f"{spec.n_candidates} candidates x {cv_folds} folds = "
            f"{spec.n_candidates * cv_folds} fits",
            flush=True,
        )
        started = time.perf_counter()
        search = tune(spec, features, X_train, y_log_train, cv_folds=cv_folds)
        elapsed = time.perf_counter() - started

        metrics = evaluate(search, X_test, y_test)
        feature_names = feature_names or preprocessed_feature_names(search)
        path = model_dir / f"{spec.key}.joblib"
        joblib.dump(search.best_estimator_, path)

        results.append(
            {
                "key": spec.key,
                "model": spec.label,
                "best_params": readable_params(search.best_params_),
                "metrics": metrics,
                "fit_seconds": round(elapsed, 1),
                "artefact": path.name,
                "feature_importances": top_feature_importances(search),
            }
        )
        print(
            f"    done in {elapsed / 60:.1f} min: "
            f"test RMSE ${metrics['rmse_dollars']:,.2f}, "
            f"MAE ${metrics['mae_dollars']:,.2f}, "
            f"R2 {metrics['r2_dollars']:.3f}, "
            f"log RMSE {metrics['rmse_log']:.4f} "
            f"(CV {metrics['cv_rmse_log_mean']:.4f} "
            f"+/- {metrics['cv_rmse_log_std']:.4f})\n",
            flush=True,
        )

    results.sort(key=lambda row: row["metrics"][SELECTION_METRIC])
    best = results[0]
    cv_ranking = [
        row["model"]
        for row in sorted(results, key=lambda r: r["metrics"]["cv_rmse_log_mean"])
    ]

    report = {
        "generated_at": timestamp.isoformat(timespec="seconds"),
        "data_source": DATA_SOURCE,
        "target": TARGET_DESCRIPTION,
        "rows_total": int(len(X)),
        "rows_train": int(len(X_train)),
        "rows_test": int(len(X_test)),
        "test_size": TEST_SIZE,
        "cv_folds": cv_folds,
        "random_seed": RANDOM_SEED,
        "configured_features": features,
        "preprocessed_features": feature_names,
        "selection_metric": SELECTION_METRIC,
        "best_model": best["model"],
        "cv_ranking": cv_ranking,
        "results": results,
        "limitations": LIMITATIONS,
    }

    _save_best(best, results, model_dir, feature_names, timestamp)
    _write_reports(report, report_dir, timestamp)
    return report


LIMITATIONS = [
    "The best model is selected by test-set RMSE, so the reported test "
    "metrics are mildly optimistic for the selected model: the test set has "
    "informed one choice. The CV ranking below is computed from training "
    "folds only and is the leakage-free comparison.",
    "The target is the current listed price, not a revenue-maximising or "
    "theoretically optimal price. The model reproduces market convention, "
    "including any mispricing in it.",
    "Data is the Inside Airbnb Sydney snapshot used as a structural proxy. "
    "The problem structure matches (provider attributes, performance and "
    "demand predicting price), but the coefficients do not transfer to "
    "mentorship pricing.",
    "Dollar RMSE is inflated by a small number of very expensive listings "
    "that a log-scale model will not predict. MAE in dollars is the more "
    "stable read on typical error.",
]


def _save_best(
    best: dict[str, Any],
    results: list[dict[str, Any]],
    model_dir: Path,
    feature_names: list[str],
    timestamp: datetime,
) -> Path:
    """Copy the winning pipeline to ``best_model.joblib`` with metadata."""
    source = model_dir / best["artefact"]
    best_path = model_dir / BEST_MODEL_FILENAME
    joblib.dump(joblib.load(source), best_path)

    metadata = {
        "model_name": best["model"],
        "artefact": BEST_MODEL_FILENAME,
        "source_artefact": best["artefact"],
        "best_params": best["best_params"],
        "metrics": best["metrics"],
        "selection_metric": SELECTION_METRIC,
        "trained_at": timestamp.isoformat(timespec="seconds"),
        "data_source": DATA_SOURCE,
        "target": TARGET_DESCRIPTION,
        "random_seed": RANDOM_SEED,
        "cv_folds": CV_FOLDS,
        "feature_names": feature_names,
        "all_models": {row["model"]: row["metrics"] for row in results},
    }
    (model_dir / BEST_METADATA_FILENAME).write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return best_path


def _comparison_table(results: list[dict[str, Any]]) -> list[str]:
    header = (
        "| Model | Test RMSE ($) | Test MAE ($) | Test R2 | Test RMSE (log) "
        "| CV RMSE (log) mean | CV RMSE (log) std | Best params |"
    )
    lines = [header, "|" + "---|" * 8]
    for row in results:
        m = row["metrics"]
        params = ", ".join(f"{k}={v}" for k, v in row["best_params"].items())
        lines.append(
            f"| {row['model']} | {m['rmse_dollars']:,.2f} | "
            f"{m['mae_dollars']:,.2f} | {m['r2_dollars']:.4f} | "
            f"{m['rmse_log']:.4f} | {m['cv_rmse_log_mean']:.4f} | "
            f"{m['cv_rmse_log_std']:.4f} | {params} |"
        )
    return lines


def _importance_table(row: dict[str, Any]) -> list[str]:
    lines = [
        f"### {row['model']}",
        "",
        "| Rank | Feature | Importance |",
        "|---|---|---|",
    ]
    for rank, item in enumerate(row["feature_importances"], start=1):
        lines.append(f"| {rank} | {item['feature']} | {item['importance']:.4f} |")
    lines.append("")
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    """Render the report dictionary as a markdown document."""
    lines = [
        "# Model training report",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Data source: {report['data_source']}",
        f"- Target: {report['target']}",
        f"- Rows: {report['rows_total']:,} "
        f"({report['rows_train']:,} train / {report['rows_test']:,} test, "
        f"test_size={report['test_size']})",
        f"- Cross-validation: {report['cv_folds']}-fold, "
        f"random_seed={report['random_seed']}",
        f"- Configured feature columns: {len(report['configured_features'])}",
        "",
        "## Comparison",
        "",
        f"Ordered by {report['selection_metric']} on the held-out test set.",
        "",
    ]
    lines += _comparison_table(report["results"])
    lines += [
        "",
        f"**Selected model: {report['best_model']}** "
        f"(lowest {report['selection_metric']}).",
        "",
        "CV-based ranking, computed from training folds only "
        "(lowest mean log RMSE first):",
        "",
    ]
    lines += [f"{i}. {name}" for i, name in enumerate(report["cv_ranking"], start=1)]
    lines += ["", "## Limitations", ""]
    lines += [f"- {note}" for note in report["limitations"]]

    with_importances = [
        row for row in report["results"] if row.get("feature_importances")
    ]
    if with_importances:
        lines += ["", f"## Feature importances (top {TOP_IMPORTANCES})", ""]
        for row in with_importances:
            lines += _importance_table(row)

    return "\n".join(lines) + "\n"


def _write_reports(
    report: dict[str, Any], report_dir: Path, timestamp: datetime
) -> tuple[Path, Path]:
    stamp = timestamp.strftime("%Y%m%d_%H%M%S")
    json_path = report_dir / f"training_report_{stamp}.json"
    md_path = report_dir / f"training_report_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {json_path.name} and {md_path.name}")
    return json_path, md_path


def main() -> dict[str, Any]:
    X, y = load_dataset()
    report = run_experiment(X, y)
    print()
    print("\n".join(_comparison_table(report["results"])))
    print()
    print(f"Selected by {SELECTION_METRIC}: {report['best_model']}")
    print(f"CV ranking (training folds only): {', '.join(report['cv_ranking'])}")
    return report


if __name__ == "__main__":
    main()
