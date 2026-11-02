"""
Checkpointed, memory-safe training for the three candidate models.

Run with::

    python -m scripts.train_experiments

Why this exists rather than a notebook cell. On the target machine (8 GB RAM,
often under 1 GB free) a single ``max_depth=None`` random forest serialises to
448 MB, and holding several fitted pipelines at once exhausted memory twice:
a worker died with ``MemoryError``, which joblib reported as a
``PicklingError``, and the whole run was lost.

So the work is split into independent, resumable units. One unit is one
``(model, feature_set)`` search. After a unit finishes, its results, its
test-set predictions and its fitted pipeline go straight to disk, the objects
are deleted and the garbage collector runs. At most one fitted model is ever
in memory. Re-running the script skips any unit that already has a
checkpoint, so a crash costs one unit rather than the whole run.

Ordering is deliberate: Ridge first because it is almost free, then XGBoost,
then Random Forest last because it is the memory risk. Within Random Forest
the cheapest feature set runs first, so a failure on the largest still leaves
the smaller ones done.

Everything about the experiment itself matches the earlier design: the
host-grouped split, fences from the training rows only, a ``log1p`` target,
pipelines that learn every statistic inside each CV fold, 10-fold
cross-validation, and metrics on two test sets.
"""

from __future__ import annotations

import argparse
import gc
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import psutil
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import (
    GridSearchCV,
    GroupShuffleSplit,
    KFold,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBRegressor

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"
CHECKPOINT_DIR = REPORTS_DIR / "checkpoints"
EXPERIMENT_DIR = PROJECT_ROOT / "models_store" / "experiments"
PROGRESS_LOG = REPORTS_DIR / "training_progress.log"
V1_RESULTS = REPORTS_DIR / "model_results_v1_sqrt.json"
COLUMN_SETS = REPORTS_DIR / "column_sets.json"
MASTER = PROCESSED_DIR / "master_listings.parquet"

RANDOM_SEED = 42
TEST_SIZE = 0.20
CV_FOLDS = 10
IQR_K = 1.5
SCORING = "neg_root_mean_squared_error"
CURRENCY = "AUD"
LONG_STAY_SCOPE = False
CATEGORICAL_COLUMNS = ["room_type", "neighbourhood_cleansed"]

# Memory guard. 0.4 GB is the floor below which a forest fit is not attempted.
MIN_FREE_GB = 0.4
MEMORY_POLL_SECONDS = 60
MEMORY_TIMEOUT_SECONDS = 30 * 60

# Every search runs single threaded, XGBoost included.
#
# XGBoost was first given n_jobs=2, since its fitted boosters are only about
# 19 MB against 338 MB for the largest forest, so the models were never the
# problem. It still died with
# ``BrokenProcessPool: A task has failed to un-serialize``. The cause is not
# the model size: joblib's loky backend spawns a fresh interpreter per worker,
# roughly 200 MB before it has unpickled anything, and at 0.74 GB free the
# worker could not allocate enough to receive the task. A probe confirmed
# n_jobs=2 works perfectly on the same machine with small data, so this is
# memory, not a pickling bug.
#
# With n_jobs=1 joblib uses its sequential backend, which forks nothing: no
# second interpreter, no second copy of the data, nothing to serialise. That is
# the whole reason this script can finish here at all. It roughly doubles the
# XGBoost time, which does not matter; finishing does.
N_JOBS_DEFAULT = 1
N_JOBS_XGBOOST = 1

RF_MAX_FEATURES_TOLERANCE = 0.01

# Importance groups, used to attribute the full model's fit.
GROUPS: dict[str, list[str]] = {
    "location": ["neighbourhood_cleansed"],
    "performance": [
        "review_scores_rating",
        "review_scores_accuracy",
        "review_scores_cleanliness",
        "review_scores_checkin",
        "review_scores_communication",
        "review_scores_location",
        "review_scores_value",
        "number_of_reviews",
        "host_is_superhost",
        "has_no_reviews",
    ],
    "demand": [
        "number_of_reviews_ltm",
        "reviews_per_month",
        "availability_365",
        "occ_30",
        "occ_60",
        "occ_90",
        "occ_365",
        "weekend_occ_365",
        "weekday_occ_365",
        "weekend_minus_weekday_occ",
        "n_availability_blocks_365",
        "reviews_last_90d",
        "reviews_last_180d",
        "reviews_last_365d",
        "days_since_last_review",
        "review_growth",
        "first_review_age_years",
        "has_calendar_data",
    ],
    "profile_other": [
        "accommodates",
        "room_type",
        "minimum_nights",
        "amenities_count",
        "host_identity_verified",
        "host_tenure_years",
        "calculated_host_listings_count",
    ],
    "space": ["bedrooms", "beds", "bathrooms"],
}
GROUP_OF_COLUMN = {
    column: group for group, columns in GROUPS.items() for column in columns
}


# ---------------------------------------------------------------------------
# Logging and the memory guard
# ---------------------------------------------------------------------------
def log(message: str, *, echo: bool = False) -> None:
    """Append a timestamped line to the progress log."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    available = psutil.virtual_memory().available / 1e9
    line = f"{stamp}  free={available:5.2f}GB  {message}"
    PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PROGRESS_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    if echo:
        print(line, flush=True)


def available_gb() -> float:
    return psutil.virtual_memory().available / 1e9


def wait_for_memory(label: str) -> float | None:
    """
    Block until enough memory is free, or give up cleanly.

    Returns the available GB once the floor is met, or ``None`` when the
    timeout expires, which the caller treats as "stop, do not crash".
    """
    waited = 0
    while True:
        free = available_gb()
        if free >= MIN_FREE_GB:
            return free
        if waited >= MEMORY_TIMEOUT_SECONDS:
            log(
                f"GIVING UP before {label}: only {free:.2f} GB free after "
                f"{waited // 60} minutes of waiting, floor is {MIN_FREE_GB} GB",
                echo=True,
            )
            return None
        log(
            f"waiting before {label}: {free:.2f} GB free, need {MIN_FREE_GB} GB, "
            f"waited {waited // 60} min",
            echo=True,
        )
        time.sleep(MEMORY_POLL_SECONDS)
        waited += MEMORY_POLL_SECONDS


# ---------------------------------------------------------------------------
# Data, split and fences
# ---------------------------------------------------------------------------
def build_preprocessor(features: list[str], scale: bool) -> ColumnTransformer:
    """Median impute with indicators, one-hot the categoricals, scale if asked."""
    numeric = [c for c in features if c not in CATEGORICAL_COLUMNS]
    categorical = [c for c in features if c in CATEGORICAL_COLUMNS]
    numeric_steps: list[tuple[str, Any]] = [
        ("impute", SimpleImputer(strategy="median", add_indicator=True))
    ]
    if scale:
        numeric_steps.append(("scale", StandardScaler()))
    branches = [("numeric", Pipeline(numeric_steps), numeric)]
    if categorical:
        branches.append(
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                categorical,
            )
        )
    return ColumnTransformer(branches, remainder="drop", verbose_feature_names_out=True)


def build_pipeline(estimator, features: list[str], scale: bool) -> Pipeline:
    return Pipeline(
        [("preprocess", build_preprocessor(features, scale)), ("model", estimator)]
    )


def encoded_feature_names(pipeline: Pipeline) -> list[str]:
    return [
        name.split("__", 1)[-1]
        for name in pipeline.named_steps["preprocess"].get_feature_names_out()
    ]


class Experiment:
    """Everything shared by the units: the data, the split and the fences."""

    def __init__(self) -> None:
        master = pd.read_parquet(MASTER, engine="pyarrow")
        self.sets = json.loads(COLUMN_SETS.read_text(encoding="utf-8"))["sets"]
        self.feature_sets = {
            "core": self.sets["core"],
            "full": self.sets["full"],
            "core_plus_space": self.sets["core"] + self.sets["space_benchmark"],
        }

        in_scope = master["long_stay"] == LONG_STAY_SCOPE
        self.rows = master.loc[in_scope].reset_index(drop=True)
        self.y = np.log1p(self.rows["price_num"])
        self.groups = self.rows["host_id"]
        self.master_rows = int(len(master))
        self.excluded_long_stay = int((master["long_stay"] == True).sum())  # noqa: E712
        self.excluded_unknown = int(master["long_stay"].isna().sum())

        splitter = GroupShuffleSplit(
            n_splits=1, test_size=TEST_SIZE, random_state=RANDOM_SEED
        )
        self.train_index, self.test_index = next(
            splitter.split(self.rows, self.y, self.groups)
        )
        overlap = set(self.groups.iloc[self.train_index]) & set(
            self.groups.iloc[self.test_index]
        )
        if overlap:
            raise RuntimeError(f"{len(overlap)} hosts appear on both sides")

        self.random_train_index, self.random_test_index = train_test_split(
            np.arange(len(self.rows)), test_size=TEST_SIZE, random_state=RANDOM_SEED
        )

        self.q1, self.q3 = np.percentile(self.y.iloc[self.train_index], [25, 75])
        self.iqr = self.q3 - self.q1
        self.lower_log = self.q1 - IQR_K * self.iqr
        self.upper_log = self.q3 + IQR_K * self.iqr
        self.lower_aud = float(np.expm1(self.lower_log))
        self.upper_aud = float(np.expm1(self.upper_log))
        self.inside = self.y.between(self.lower_log, self.upper_log)

        self.fit_index = np.array(
            [i for i in self.train_index if self.inside.iloc[i]]
        )
        self.test_sets = {
            "typical": np.array(
                [i for i in self.test_index if self.inside.iloc[i]]
            ),
            "all": np.asarray(self.test_index),
        }
        self.cv = KFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_SEED)

    def fence_counts(self) -> dict[str, dict[str, Any]]:
        counts = {}
        for name, index in (("train", self.train_index), ("test", self.test_index)):
            keep = self.inside.iloc[index]
            prices = self.rows["price_num"].iloc[index]
            counts[name] = {
                "rows": int(len(index)),
                "inside": int(keep.sum()),
                "outside": int((~keep).sum()),
                "below_lower": int((prices < self.lower_aud).sum()),
                "above_upper": int((prices > self.upper_aud).sum()),
                "pct_outside": round(100 * float((~keep).mean()), 2),
            }
        return counts

    def evaluate(self, pipeline: Pipeline, index: np.ndarray) -> dict[str, float]:
        features = list(pipeline.named_steps["preprocess"].feature_names_in_)
        predicted_log = pipeline.predict(self.rows.iloc[index][features])
        predicted_aud = np.expm1(predicted_log)
        actual_log = self.y.iloc[index].to_numpy()
        actual_aud = self.rows["price_num"].iloc[index].to_numpy()
        return {
            "rmse_aud": float(np.sqrt(mean_squared_error(actual_aud, predicted_aud))),
            "mae_aud": float(mean_absolute_error(actual_aud, predicted_aud)),
            "r2": float(r2_score(actual_aud, predicted_aud)),
            "rmse_log": float(np.sqrt(mean_squared_error(actual_log, predicted_log))),
        }

    def context(self, rf_max_features, rf_evidence) -> dict[str, Any]:
        return {
            "generated_by": "scripts/train_experiments.py",
            "dataset": f"data/processed/{MASTER.name}",
            "currency": CURRENCY,
            "seed": RANDOM_SEED,
            "cv": {
                "folds": CV_FOLDS,
                "splitter": "KFold(shuffle=True, random_state=42)",
                "scoring": SCORING,
                "target": "log1p(price_num)",
            },
            "scope": {
                "filter": f"long_stay == {LONG_STAY_SCOPE}",
                "master_rows": self.master_rows,
                "rows_modelled": int(len(self.rows)),
                "rows_excluded_long_stay": self.excluded_long_stay,
                "rows_excluded_long_stay_unknown": self.excluded_unknown,
            },
            "split": {
                "method": "GroupShuffleSplit on host_id",
                "test_size": TEST_SIZE,
                "train_rows": int(len(self.train_index)),
                "test_rows": int(len(self.test_index)),
                "train_hosts": int(self.groups.iloc[self.train_index].nunique()),
                "test_hosts": int(self.groups.iloc[self.test_index].nunique()),
                "hosts_in_both": 0,
            },
            "fences": {
                "k": IQR_K,
                "scale": "log1p(price)",
                "fitted_on": "training rows only",
                "q1_log": float(self.q1),
                "q3_log": float(self.q3),
                "lower_log": float(self.lower_log),
                "upper_log": float(self.upper_log),
                "lower_aud": round(self.lower_aud, 2),
                "upper_aud": round(self.upper_aud, 2),
                "rows_outside": self.fence_counts(),
                "training_rows_used": int(len(self.fit_index)),
                "test_rows_typical": int(len(self.test_sets["typical"])),
                "test_rows_all": int(len(self.test_sets["all"])),
            },
            "feature_sets": self.feature_sets,
            "importance_groups": GROUPS,
            "rf_max_features": {
                "selected": str(rf_max_features),
                "rule": f"cheapest candidate within "
                f"{RF_MAX_FEATURES_TOLERANCE:.0%} CV log RMSE of the best",
                "source": f"reports/{V1_RESULTS.name} probe record, not rerun",
                "evidence": rf_evidence,
            },
        }


# ---------------------------------------------------------------------------
# Grids
# ---------------------------------------------------------------------------
def rule_selected_max_features() -> tuple[Any, list[dict[str, Any]]]:
    """
    Read the earlier probe and apply the tolerance rule. The probe is not rerun.

    The rule: of the candidates whose CV log RMSE is within the tolerance of the
    best, take the cheapest. Accuracy is the constraint, speed the objective.
    """
    record = json.loads(V1_RESULTS.read_text(encoding="utf-8"))["deviations"][
        "rf_max_features"
    ]
    evidence = pd.DataFrame(record["evidence"])
    best = float(evidence["cv_rmse_log_mean"].min())
    evidence["loss_vs_best_pct"] = (
        100 * (evidence["cv_rmse_log_mean"] - best) / best
    ).round(4)
    evidence["within_tolerance"] = (
        evidence["loss_vs_best_pct"] <= 100 * RF_MAX_FEATURES_TOLERANCE
    )
    eligible = evidence.loc[evidence["within_tolerance"]]
    chosen = eligible.loc[eligible["wall_seconds"].idxmin(), "max_features"]
    value: Any = chosen
    try:
        value = float(chosen)
    except ValueError:
        pass
    return value, evidence.to_dict(orient="records")


def model_specs(rf_max_features) -> dict[str, dict[str, Any]]:
    return {
        "Ridge": {
            "estimator": Ridge(),
            "scale": True,
            "grid": {"model__alpha": [0.01, 0.1, 1, 10, 100]},
            "n_jobs": N_JOBS_DEFAULT,
        },
        "XGBoost": {
            "estimator": XGBRegressor(
                tree_method="hist",
                importance_type="gain",
                random_state=RANDOM_SEED,
                n_jobs=1,
            ),
            "scale": False,
            "grid": {
                "model__n_estimators": [700, 1200, 2000],
                "model__max_depth": [4, 6, 8],
                "model__learning_rate": [0.03, 0.05, 0.1],
            },
            "n_jobs": N_JOBS_XGBOOST,
        },
        "RandomForest": {
            # max_depth=None is dropped: it produced 448 MB forests. The 20/1
            # corner still reaches 338 MB, which is why n_jobs stays at 1 (the
            # sequential backend forks no worker, so there is no second copy).
            "estimator": RandomForestRegressor(
                max_features=rf_max_features, random_state=RANDOM_SEED, n_jobs=1
            ),
            "scale": False,
            "grid": {
                "model__n_estimators": [200, 400],
                "model__max_depth": [10, 20],
                "model__min_samples_leaf": [1, 3, 5],
            },
            "n_jobs": N_JOBS_DEFAULT,
        },
    }


def grid_position(value, candidates) -> str:
    """Where the chosen value sits in its candidate list."""
    ordered = sorted(
        candidates, key=lambda v: float("inf") if v is None else float(v)
    )
    if len(ordered) == 1:
        return "single value"
    index = ordered.index(value)
    if index == 0:
        return "LOW EDGE"
    if index == len(ordered) - 1:
        return "HIGH EDGE (unbounded)" if ordered[-1] is None else "HIGH EDGE"
    return "interior"


def importance_records(pipeline: Pipeline, features: list[str]) -> dict[str, Any]:
    """Importances with the source column and group, as plain records."""
    names = encoded_feature_names(pipeline)
    model = pipeline.named_steps["model"]
    if hasattr(model, "feature_importances_"):
        values = np.asarray(model.feature_importances_, dtype=float)
        kind = "gain" if isinstance(model, XGBRegressor) else "impurity decrease"
    else:
        values = np.abs(np.asarray(model.coef_, dtype=float).ravel())
        kind = "absolute standardised coefficient"

    def source_column(encoded_name: str) -> str:
        stripped = encoded_name
        if stripped.startswith("missingindicator_"):
            stripped = stripped[len("missingindicator_") :]
        if stripped in features:
            return stripped
        for categorical in CATEGORICAL_COLUMNS:
            if stripped.startswith(f"{categorical}_"):
                return categorical
        matches = [c for c in features if stripped.startswith(c)]
        return max(matches, key=len) if matches else stripped

    table = pd.DataFrame({"feature": names, "importance": values})
    table["source_column"] = [source_column(n) for n in table["feature"]]
    table["group"] = table["source_column"].map(GROUP_OF_COLUMN).fillna("other")
    total = float(table["importance"].sum())
    table["share_pct"] = 100 * table["importance"] / total if total else np.nan
    table = table.sort_values("importance", ascending=False, ignore_index=True)
    table.insert(0, "rank", np.arange(1, len(table) + 1))
    return {"kind": kind, "rows": table.to_dict(orient="records")}


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------
def checkpoint_path(model_name: str, set_name: str) -> Path:
    return CHECKPOINT_DIR / f"{model_name}__{set_name}.json".lower()


def predictions_path(model_name: str, set_name: str) -> Path:
    return CHECKPOINT_DIR / f"{model_name}__{set_name}_preds.npz".lower()


def pipeline_path(model_name: str, set_name: str) -> Path:
    return EXPERIMENT_DIR / f"{model_name}__{set_name}.joblib".lower()


def run_search_unit(
    experiment: Experiment, model_name: str, set_name: str, specs: dict[str, Any]
) -> bool:
    """One (model, feature_set) search. Returns False to stop the whole run."""
    label = f"{model_name}/{set_name}"
    free = wait_for_memory(f"search {label}")
    if free is None:
        return False

    spec = specs[model_name]
    features = experiment.feature_sets[set_name]
    started = time.perf_counter()
    log(f"START  {label}  ({len(features)} columns, n_jobs={spec['n_jobs']})",
        echo=True)

    X_fit = experiment.rows.iloc[experiment.fit_index][features]
    y_fit = experiment.y.iloc[experiment.fit_index]

    # refit=False so the final fit is ours to time and to memory-check first.
    search = GridSearchCV(
        build_pipeline(clone(spec["estimator"]), features, spec["scale"]),
        param_grid=spec["grid"],
        cv=experiment.cv,
        scoring=SCORING,
        n_jobs=spec["n_jobs"],
        refit=False,
    )
    search.fit(X_fit, y_fit)
    search_seconds = time.perf_counter() - started

    best = int(np.argmin(-search.cv_results_["mean_test_score"]))
    best_params = {
        key: search.cv_results_["params"][best][key] for key in spec["grid"]
    }
    cv_mean = float(-search.cv_results_["mean_test_score"][best])
    cv_sd = float(search.cv_results_["std_test_score"][best])
    del search
    gc.collect()

    free = wait_for_memory(f"refit {label}")
    if free is None:
        return False

    refit_started = time.perf_counter()
    pipeline = build_pipeline(clone(spec["estimator"]), features, spec["scale"])
    pipeline.set_params(**best_params)
    pipeline.fit(X_fit, y_fit)
    refit_seconds = time.perf_counter() - refit_started

    metrics = {}
    predictions = {}
    for test_name, index in experiment.test_sets.items():
        metrics[test_name] = experiment.evaluate(pipeline, index)
        predictions[test_name] = np.expm1(
            pipeline.predict(experiment.rows.iloc[index][features])
        )

    edges = []
    for key, candidates in spec["grid"].items():
        parameter = key.replace("model__", "")
        value = best_params[key]
        edges.append(
            {
                "parameter": parameter,
                "chosen": str(value),
                "candidates": [str(c) for c in candidates],
                "position": grid_position(value, candidates),
            }
        )

    importances = importance_records(pipeline, features)

    target = pipeline_path(model_name, set_name)
    joblib.dump(pipeline, target, compress=3)
    np.savez_compressed(
        predictions_path(model_name, set_name),
        typical=predictions["typical"],
        all=predictions["all"],
    )

    record = {
        "model": model_name,
        "feature_set": set_name,
        "n_columns": len(features),
        "n_encoded": len(importances["rows"]),
        "best_params": {k.replace("model__", ""): str(v) for k, v in best_params.items()},
        "best_params_raw": {k: v for k, v in best_params.items()},
        "cv_rmse_log_mean": cv_mean,
        "cv_rmse_log_sd": cv_sd,
        "metrics": metrics,
        "grid_edges": edges,
        "importances": importances,
        "search_seconds": round(search_seconds, 1),
        "refit_seconds": round(refit_seconds, 1),
        "wall_seconds": round(search_seconds + refit_seconds, 1),
        "artefact": f"models_store/experiments/{target.name}",
        "artefact_bytes": int(target.stat().st_size),
        "free_gb_at_start": round(free, 2),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    checkpoint_path(model_name, set_name).write_text(
        json.dumps(record, indent=2, default=str), encoding="utf-8"
    )

    del pipeline, predictions, importances
    gc.collect()

    log(
        f"DONE   {label}  CV log RMSE {cv_mean:.4f} +/- {cv_sd:.4f}  "
        f"typical RMSE {metrics['typical']['rmse_aud']:,.2f} {CURRENCY}  "
        f"{record['wall_seconds']:.1f}s  artefact "
        f"{record['artefact_bytes'] / 1e6:.1f} MB",
        echo=True,
    )
    return True


def run_leakage_unit(experiment: Experiment, specs: dict[str, Any]) -> bool:
    """
    XGBoost at its tuned parameters on a grouped and a random split.

    Each arm takes its fences from its own training rows, so neither borrows a
    filtering decision made with the other's data. The two numbers are not
    measured on the same test set, which is the point: the random split's test
    rows include listings whose owner is also in training.
    """
    label = "leakage/all"
    free = wait_for_memory(f"unit {label}")
    if free is None:
        return False

    started = time.perf_counter()
    log(f"START  {label}", echo=True)

    rows = []
    for set_name, features in experiment.feature_sets.items():
        tuned = checkpoint_path("XGBoost", set_name)
        if not tuned.exists():
            log(f"SKIP   {label}: XGBoost/{set_name} is not done yet", echo=True)
            return True
        best_params = json.loads(tuned.read_text(encoding="utf-8"))["best_params_raw"]

        for split_name, tr_index, te_index in (
            ("grouped", experiment.train_index, experiment.test_index),
            ("random", experiment.random_train_index, experiment.random_test_index),
        ):
            low, high = np.percentile(experiment.y.iloc[tr_index], [25, 75])
            spread = high - low
            split_lower, split_upper = low - IQR_K * spread, high + IQR_K * spread
            split_inside = experiment.y.between(split_lower, split_upper)
            fit_rows = np.array([i for i in tr_index if split_inside.iloc[i]])
            typical_rows = np.array([i for i in te_index if split_inside.iloc[i]])

            pipeline = build_pipeline(
                clone(specs["XGBoost"]["estimator"]),
                features,
                specs["XGBoost"]["scale"],
            )
            pipeline.set_params(**best_params)
            pipeline.fit(
                experiment.rows.iloc[fit_rows][features],
                experiment.y.iloc[fit_rows],
            )
            seen = experiment.groups.iloc[te_index].isin(
                set(experiment.groups.iloc[tr_index])
            )
            rows.append(
                {
                    "feature_set": set_name,
                    "split": split_name,
                    "upper_fence_aud": round(float(np.expm1(split_upper)), 2),
                    "train_rows": int(len(fit_rows)),
                    "test_rows": int(len(typical_rows)),
                    "hosts_in_both": int(
                        len(
                            set(experiment.groups.iloc[tr_index])
                            & set(experiment.groups.iloc[te_index])
                        )
                    ),
                    "test_rows_with_seen_host": int(seen.sum()),
                    **experiment.evaluate(pipeline, typical_rows),
                }
            )
            del pipeline
            gc.collect()

    frame = pd.DataFrame(rows)
    gaps = []
    for set_name in experiment.feature_sets:
        grouped = frame.loc[
            (frame["feature_set"] == set_name) & (frame["split"] == "grouped")
        ].iloc[0]
        random_row = frame.loc[
            (frame["feature_set"] == set_name) & (frame["split"] == "random")
        ].iloc[0]
        gaps.append(
            {
                "feature_set": set_name,
                "rmse_log_grouped": float(grouped["rmse_log"]),
                "rmse_log_random": float(random_row["rmse_log"]),
                "rmse_log_change": float(random_row["rmse_log"] - grouped["rmse_log"]),
                "rmse_log_change_pct": float(
                    100
                    * (random_row["rmse_log"] - grouped["rmse_log"])
                    / grouped["rmse_log"]
                ),
                "rmse_aud_grouped": float(grouped["rmse_aud"]),
                "rmse_aud_random": float(random_row["rmse_aud"]),
                "r2_grouped": float(grouped["r2"]),
                "r2_random": float(random_row["r2"]),
            }
        )

    elapsed = time.perf_counter() - started
    record = {
        "unit": "leakage",
        "method": "XGBoost at its tuned parameters, refitted on a grouped and a "
        "random split, each scored on its own typical test set",
        "rows": rows,
        "gaps": gaps,
        "wall_seconds": round(elapsed, 1),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    checkpoint_path("leakage", "all").write_text(
        json.dumps(record, indent=2, default=str), encoding="utf-8"
    )
    log(f"DONE   {label}  {elapsed:.1f}s", echo=True)
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
# Ridge first (almost free), then XGBoost, then Random Forest last because it
# is the memory risk. Within Random Forest the cheapest set runs first, so a
# failure on the largest still leaves the smaller ones checkpointed.
UNITS: list[tuple[str, str]] = [
    ("Ridge", "core"),
    ("Ridge", "core_plus_space"),
    ("Ridge", "full"),
    ("XGBoost", "core"),
    ("XGBoost", "core_plus_space"),
    ("XGBoost", "full"),
    ("RandomForest", "core"),
    ("RandomForest", "core_plus_space"),
    ("RandomForest", "full"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="redo units that already have a checkpoint",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="run one unit only, as Model/feature_set, e.g. RandomForest/full",
    )
    args = parser.parse_args()

    for directory in (CHECKPOINT_DIR, EXPERIMENT_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    log("=" * 70)
    log(f"run starting, force={args.force}, only={args.only}", echo=True)

    rf_max_features, rf_evidence = rule_selected_max_features()
    log(f"Random Forest max_features={rf_max_features} selected by the "
        f"{RF_MAX_FEATURES_TOLERANCE:.0%} tolerance rule from the stored probe",
        echo=True)

    experiment = Experiment()
    specs = model_specs(rf_max_features)

    context_path = CHECKPOINT_DIR / "_context.json"
    context_path.write_text(
        json.dumps(experiment.context(rf_max_features, rf_evidence), indent=2,
                   default=str),
        encoding="utf-8",
    )
    log(f"context written to reports/checkpoints/{context_path.name}", echo=True)
    log(
        f"fences {experiment.lower_aud:,.2f} to {experiment.upper_aud:,.2f} "
        f"{CURRENCY}; training rows {len(experiment.fit_index):,}; "
        f"typical test {len(experiment.test_sets['typical']):,}; "
        f"all test {len(experiment.test_sets['all']):,}",
        echo=True,
    )

    units = UNITS
    if args.only:
        wanted = tuple(args.only.split("/", 1))
        units = [u for u in UNITS if u == wanted]
        if not units:
            print(f"no unit matches {args.only}", flush=True)
            return 2

    done = skipped = 0
    for model_name, set_name in units:
        path = checkpoint_path(model_name, set_name)
        if path.exists() and not args.force:
            skipped += 1
            log(f"SKIP   {model_name}/{set_name}: checkpoint exists", echo=True)
            continue
        if not run_search_unit(experiment, model_name, set_name, specs):
            log("stopping cleanly: the memory floor was not met", echo=True)
            return 1
        done += 1

    leakage = checkpoint_path("leakage", "all")
    if leakage.exists() and not args.force:
        log("SKIP   leakage/all: checkpoint exists", echo=True)
    elif not args.only:
        if not run_leakage_unit(experiment, specs):
            log("stopping cleanly: the memory floor was not met", echo=True)
            return 1

    complete = sum(1 for m, s in UNITS if checkpoint_path(m, s).exists())
    log(
        f"run finished: {done} unit(s) trained, {skipped} skipped, "
        f"{complete} of {len(UNITS)} search units complete, "
        f"leakage {'done' if leakage.exists() else 'pending'}",
        echo=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
