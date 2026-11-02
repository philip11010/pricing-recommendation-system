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

Failures are loud now. The previous run let scikit-learn's default
``error_score=np.nan`` turn every failed CV fit into a silent ``nan``, and the
units that were affected still wrote checkpoints, reporting
``CV log RMSE nan +/- nan`` as though that were a result. Every search and
every cross-validation here passes ``error_score="raise"``, the CV mean and SD
are asserted finite before anything is written, and the checkpoint, the
predictions and the pipeline are written to temporary names and renamed only
once the whole unit has succeeded. A crash can no longer leave a half-written
checkpoint behind.

Flags::

    --n-jobs N      parallelism for the searches, the forest and XGBoost
    --only UNIT     one unit, as Model/feature_set, or the keyword "leakage"
    --force         redo a unit that already has a checkpoint
    --verify-only   report on the existing checkpoints, train nothing
    --backfill-cv   recompute the CV mean and SD of a finished unit in place
    --dry-run       list what each unit would do, fit nothing
"""

from __future__ import annotations

import argparse
import ctypes
import gc
import json
import math
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
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
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import (
    GridSearchCV,
    GroupShuffleSplit,
    KFold,
    cross_val_predict,
    cross_validate,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBRegressor

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"
MODELS_DIR = PROJECT_ROOT / "models_store"
CHECKPOINT_DIR = REPORTS_DIR / "checkpoints"
EXPERIMENT_DIR = MODELS_DIR / "experiments"
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

# Price bands for the residual quantiles and the error-by-band table. Defined
# here rather than in the notebook so the checkpoint and the figure agree.
PRICE_BANDS = [0, 100, 200, 300, 500, 1000, float("inf")]
PRICE_BAND_LABELS = ["0-99", "100-199", "200-299", "300-499", "500-999", "1000+"]

# Memory guard.
#
# Two numbers matter on Windows, not one. The RAM floor is physical memory
# available, which is what the MemoryError ran out of. The commit floor is the
# commit charge headroom: how much the system will still promise to back with
# RAM or page file. An allocation reserves commit before it touches a page, so
# a fit can die on commit while physical RAM still looks adequate, which is the
# more likely reading of the forest refit that crashed after 70 of its 120 CV
# fits had already failed. Both floors are checked, and both numbers are
# logged with every progress line.
#
# The defaults differ by profile because the fits differ by an order of
# magnitude. The standard profile caps max_depth at 20 and its largest forest
# measured 338 MB, so 0.4 GB is enough to start one. The workstation profile
# puts max_depth=None back in the grid, where a 600-tree unbounded forest is
# over 1 GB on its own and several are held at once, so it refuses to start
# with less than 4 GB. Both are overridable with --min-ram-gb and
# --min-commit-gb.
MIN_FREE_GB = 0.4
MIN_COMMIT_GB = 1.0
MIN_FREE_GB_WORKSTATION = 4.0
MIN_COMMIT_GB_WORKSTATION = 8.0
MEMORY_POLL_SECONDS = 60
MEMORY_TIMEOUT_SECONDS = 30 * 60

# Every search runs single threaded by default, XGBoost included.
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
# the whole reason this script can finish on the 8 GB laptop at all.
#
# These are the defaults, not the only option. --n-jobs raises the search
# parallelism, the forest's n_jobs and XGBoost's thread count together, and
# accepts -1 for every core. XGBoost never drops below N_JOBS_XGBOOST, so the
# flag can only increase it.
N_JOBS_DEFAULT = 1
N_JOBS_XGBOOST = 1

RF_MAX_FEATURES_TOLERANCE = 0.01


# ---------------------------------------------------------------------------
# Profiles, smoke mode and the run configuration
# ---------------------------------------------------------------------------
# A profile is a grid size, nothing more. The experiment itself (the split, the
# fences, the target, the folds, the metrics) is identical across profiles, so
# a standard-profile result and a workstation-profile result are comparable.
#
# They are kept in separate checkpoint folders rather than overwriting each
# other, because the question "did the wider grid actually buy anything" can
# only be answered if both sets of numbers survive.
PROFILES = ("standard", "workstation")

PROFILE_GRIDS: dict[str, dict[str, dict[str, list[Any]]]] = {
    "standard": {
        "Ridge": {"model__alpha": [0.01, 0.1, 1, 10, 100]},
        # 27 combinations. max_depth=None is deliberately absent: it is what
        # produced the 448 MB forests that killed run 2.
        "XGBoost": {
            "model__n_estimators": [700, 1200, 2000],
            "model__max_depth": [4, 6, 8],
            "model__learning_rate": [0.03, 0.05, 0.1],
        },
        "RandomForest": {
            "model__n_estimators": [200, 400],
            "model__max_depth": [10, 20],
            "model__min_samples_leaf": [1, 3, 5],
        },
    },
    "workstation": {
        # Ridge is unchanged: five alphas already bracket its optimum and it
        # costs seconds, so there is nothing to buy by widening it.
        "Ridge": {"model__alpha": [0.01, 0.1, 1, 10, 100]},
        # 48 combinations, up from 27. The standard run put learning_rate on
        # its high edge on core, so 0.2 is added above it, and n_estimators
        # and max_depth are extended upwards for the same reason.
        "XGBoost": {
            "model__n_estimators": [1000, 2000, 3000],
            "model__max_depth": [4, 6, 8, 10],
            "model__learning_rate": [0.02, 0.05, 0.1, 0.2],
        },
        # 32 combinations, up from 12, and max_depth=None is back. That is
        # only safe because this profile also raises the memory floors: an
        # unbounded 600-tree forest on 12,454 rows is over 1 GB.
        "RandomForest": {
            "model__n_estimators": [300, 600],
            "model__max_depth": [10, 20, 30, None],
            "model__min_samples_leaf": [1, 2, 3, 5],
        },
    },
}

# Smoke mode: single-value grids, 50 trees, 3 folds, a tenth of the rows. It
# proves that every unit, the parallel dispatcher, the extras and both
# notebooks execute. It proves nothing about accuracy, and it writes to its own
# folder so a real checkpoint can never be overwritten by a test.
SMOKE_GRIDS: dict[str, dict[str, list[Any]]] = {
    "Ridge": {"model__alpha": [1.0]},
    "XGBoost": {
        "model__n_estimators": [50],
        "model__max_depth": [4],
        "model__learning_rate": [0.1],
    },
    "RandomForest": {
        "model__n_estimators": [50],
        "model__max_depth": [10],
        "model__min_samples_leaf": [1],
    },
}
SMOKE_CV_FOLDS = 3
SMOKE_ROW_FRACTION = 0.10
SMOKE_PERMUTATION_REPEATS = 2

# Extras use these, and they are read back by notebook 04.
LEARNING_CURVE_FRACTIONS = (0.2, 0.4, 0.6, 0.8, 1.0)
PERMUTATION_REPEATS = 10
RESIDUAL_QUANTILES = (10, 90)


@dataclass(frozen=True)
class RunConfig:
    """
    Everything that depends on --profile, --smoke and the memory flags.

    One object rather than a scatter of globals, so a child process started by
    the parallel dispatcher reconstructs exactly the same configuration from
    its own flags, and notebook 04 reconstructs it from the environment.
    """

    profile: str = "standard"
    smoke: bool = False
    min_ram_gb: float | None = None
    min_commit_gb: float | None = None

    @property
    def checkpoints(self) -> Path:
        if self.smoke:
            return REPORTS_DIR / "checkpoints_smoke"
        if self.profile == "workstation":
            return REPORTS_DIR / "checkpoints_workstation"
        return CHECKPOINT_DIR

    @property
    def experiments(self) -> Path:
        if self.smoke:
            return MODELS_DIR / "experiments_smoke"
        if self.profile == "workstation":
            return MODELS_DIR / "experiments_workstation"
        return EXPERIMENT_DIR

    @property
    def cv_folds(self) -> int:
        return SMOKE_CV_FOLDS if self.smoke else CV_FOLDS

    @property
    def grids(self) -> dict[str, dict[str, list[Any]]]:
        return SMOKE_GRIDS if self.smoke else PROFILE_GRIDS[self.profile]

    @property
    def permutation_repeats(self) -> int:
        return SMOKE_PERMUTATION_REPEATS if self.smoke else PERMUTATION_REPEATS

    @property
    def ram_floor(self) -> float:
        if self.min_ram_gb is not None:
            return self.min_ram_gb
        if self.profile == "workstation" and not self.smoke:
            return MIN_FREE_GB_WORKSTATION
        return MIN_FREE_GB

    @property
    def commit_floor(self) -> float:
        if self.min_commit_gb is not None:
            return self.min_commit_gb
        if self.profile == "workstation" and not self.smoke:
            return MIN_COMMIT_GB_WORKSTATION
        return MIN_COMMIT_GB

    def describe(self) -> str:
        parts = [f"profile={self.profile}"]
        if self.smoke:
            parts.append("SMOKE")
        parts.append(f"folds={self.cv_folds}")
        parts.append(f"ram_floor={self.ram_floor}GB")
        parts.append(f"commit_floor={self.commit_floor}GB")
        return ", ".join(parts)

    def as_env(self) -> dict[str, str]:
        """The environment a child process or notebook 04 needs to agree."""
        return {"PRS_PROFILE": self.profile, "PRS_SMOKE": "1" if self.smoke else "0"}


# The active configuration. Rebound by configure(), which main() calls once
# from the parsed flags and notebook 04 calls from the environment.
CONFIG = RunConfig()
# Set in a child process so every log line says which unit wrote it.
LOG_LABEL: str | None = None


def configure(
    profile: str = "standard",
    smoke: bool = False,
    min_ram_gb: float | None = None,
    min_commit_gb: float | None = None,
) -> RunConfig:
    """Rebind the active configuration and return it."""
    global CONFIG
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}, expected one of {PROFILES}")
    CONFIG = RunConfig(
        profile=profile,
        smoke=smoke,
        min_ram_gb=min_ram_gb,
        min_commit_gb=min_commit_gb,
    )
    return CONFIG


def configure_from_env() -> RunConfig:
    """
    Rebind the active configuration from PRS_PROFILE and PRS_SMOKE.

    This is how notebook 04 and the dispatcher's children learn which
    checkpoint folder to read without being passed an argument. Unset means
    the standard profile, which is what a plain ``Run All`` of notebook 04
    should see.
    """
    return configure(
        profile=os.environ.get("PRS_PROFILE", "standard"),
        smoke=os.environ.get("PRS_SMOKE", "0") == "1",
    )


def resolve_n_jobs(requested: int | None, parallel_units: int = 1) -> int:
    """
    Turn the --n-jobs flag into a thread count.

    ``-1`` means every core. ``None`` means the flag was not given: under
    --parallel-units the budget is split, ``cores // K``, so K units running at
    once do not oversubscribe; without it the default stays 1, which is what
    the 8 GB laptop needs.
    """
    cores = os.cpu_count() or 1
    if requested == -1:
        return max(1, cores // max(1, parallel_units))
    if requested is not None:
        return max(1, requested)
    if parallel_units > 1:
        return max(1, cores // parallel_units)
    return N_JOBS_DEFAULT


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
class _MemoryStatusEx(ctypes.Structure):
    """The MEMORYSTATUSEX struct, so the commit charge can be read directly."""

    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def memory_status() -> tuple[float, float]:
    """
    Return (physical RAM available, commit charge available) in GB.

    ``ullAvailPageFile`` from GlobalMemoryStatusEx is not the free space inside
    pagefile.sys, despite the name: it is the commit limit minus the current
    commit charge, which is the number an allocation is actually checked
    against. psutil does not expose it, so the Win32 call is made directly,
    with psutil as the fallback on a non-Windows machine or if the call fails.
    The fallback adds free swap to free RAM, which approximates the same
    headroom rather than reporting it.
    """
    if sys.platform == "win32":
        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return status.ullAvailPhys / 1e9, status.ullAvailPageFile / 1e9
        except (AttributeError, OSError):
            pass
    virtual = psutil.virtual_memory()
    try:
        swap_free = psutil.swap_memory().free
    except (RuntimeError, OSError):
        swap_free = 0
    return virtual.available / 1e9, (virtual.available + swap_free) / 1e9


def log(message: str, *, echo: bool = False) -> None:
    """Append a timestamped line to the progress log, with both memory figures."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    free, commit = memory_status()
    # Several processes append to this file under --parallel-units, so every
    # line says which unit wrote it. Each line is one short append, which is
    # atomic enough on Windows that interleaving does not corrupt a line.
    tag = f"[{LOG_LABEL}] " if LOG_LABEL else ""
    line = f"{stamp}  free={free:5.2f}GB  commit={commit:6.2f}GB  {tag}{message}"
    PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PROGRESS_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    if echo:
        print(line, flush=True)


def available_gb() -> float:
    return memory_status()[0]


def wait_for_memory(label: str) -> float | None:
    """
    Block until enough memory is free, or give up cleanly.

    Both floors have to be met: physical RAM and commit headroom, each taken
    from the active configuration, so --profile and --min-ram-gb /
    --min-commit-gb both reach it. Returns the available RAM in GB once they
    are met, or ``None`` when the timeout expires, which the caller treats as
    "stop, do not crash".
    """
    ram_floor = CONFIG.ram_floor
    commit_floor = CONFIG.commit_floor
    waited = 0
    while True:
        free, commit = memory_status()
        if free >= ram_floor and commit >= commit_floor:
            return free
        short = []
        if free < ram_floor:
            short.append(f"RAM {free:.2f} GB below the {ram_floor} GB floor")
        if commit < commit_floor:
            short.append(f"commit {commit:.2f} GB below the {commit_floor} GB floor")
        reason = " and ".join(short)
        if waited >= MEMORY_TIMEOUT_SECONDS:
            log(
                f"GIVING UP before {label}: {reason} after "
                f"{waited // 60} minutes of waiting",
                echo=True,
            )
            return None
        log(f"waiting before {label}: {reason}, waited {waited // 60} min", echo=True)
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

        self.fit_index = np.array([i for i in self.train_index if self.inside.iloc[i]])
        self.test_sets = {
            "typical": np.array([i for i in self.test_index if self.inside.iloc[i]]),
            "all": np.asarray(self.test_index),
        }
        # Smoke mode keeps a seeded tenth of the rows on both sides. The
        # subsample is taken after the fences so the fences themselves are the
        # real ones, and it is applied to the test sets too, which keeps the
        # extras (permutation importance in particular) to seconds.
        self.smoke = CONFIG.smoke
        self.cv_folds = CONFIG.cv_folds
        if self.smoke:
            rng = np.random.default_rng(RANDOM_SEED)
            self.fit_index = self.subsample(self.fit_index, rng)
            self.test_sets = {
                name: self.subsample(index, rng)
                for name, index in self.test_sets.items()
            }
        self.cv = KFold(n_splits=self.cv_folds, shuffle=True, random_state=RANDOM_SEED)

    @staticmethod
    def subsample(index: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        """A seeded SMOKE_ROW_FRACTION of an index, order preserved."""
        keep = max(2, int(round(len(index) * SMOKE_ROW_FRACTION)))
        chosen = rng.choice(len(index), size=keep, replace=False)
        return np.asarray(index)[np.sort(chosen)]

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
            "profile": CONFIG.profile,
            "smoke": CONFIG.smoke,
            "checkpoint_dir": f"reports/{CONFIG.checkpoints.name}",
            "grids": {
                model_name: {
                    key.replace("model__", ""): [str(v) for v in values]
                    for key, values in grid.items()
                }
                for model_name, grid in CONFIG.grids.items()
            },
            "cv": {
                "folds": self.cv_folds,
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
                # In smoke mode these three are a seeded fraction of the real
                # counts, so they do not reconcile against split.train_rows.
                # Saying so here is cheaper than a reader rediscovering it.
                "smoke_subsample": (SMOKE_ROW_FRACTION if self.smoke else None),
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


def model_specs(
    rf_max_features, n_jobs: int = N_JOBS_DEFAULT
) -> dict[str, dict[str, Any]]:
    """
    The three estimators, their grids and their parallelism.

    The grids come from the active configuration, so --profile and --smoke
    choose them in one place and every caller, including the extras and the
    leakage unit, sees the same thing. The estimators, the preprocessing, the
    split, the fences, the folds and the metrics are identical across
    profiles: a profile widens the search and changes nothing else, which is
    what makes two profiles comparable.

    ``n_jobs`` comes from --n-jobs. It raises the GridSearchCV parallelism for
    all three models and the Random Forest's own n_jobs. XGBoost is floored at
    N_JOBS_XGBOOST, so the flag can only increase its thread count, never
    reduce it below the value known to work on the laptop. Under
    --parallel-units this is already the per-unit share of the cores, so K
    units at once do not oversubscribe.
    """
    grids = CONFIG.grids
    xgboost_jobs = max(N_JOBS_XGBOOST, n_jobs)
    return {
        "Ridge": {
            "estimator": Ridge(),
            "scale": True,
            "grid": grids["Ridge"],
            "n_jobs": n_jobs,
        },
        "XGBoost": {
            "estimator": XGBRegressor(
                tree_method="hist",
                importance_type="gain",
                random_state=RANDOM_SEED,
                n_jobs=xgboost_jobs,
            ),
            "scale": False,
            "grid": grids["XGBoost"],
            "n_jobs": xgboost_jobs,
        },
        "RandomForest": {
            # max_features is the rule-selected 0.33 in both profiles, read
            # from the stored probe rather than rerun. The standard profile
            # drops max_depth=None because it produced the 448 MB forests that
            # killed run 2; the workstation profile puts it back, and raises
            # the memory floors to match.
            "estimator": RandomForestRegressor(
                max_features=rf_max_features, random_state=RANDOM_SEED, n_jobs=n_jobs
            ),
            "scale": False,
            "grid": grids["RandomForest"],
            "n_jobs": n_jobs,
        },
    }


def grid_fit_count(grid: dict[str, list[Any]], folds: int) -> int:
    """How many fits one search costs: every combination times every fold."""
    combinations = 1
    for values in grid.values():
        combinations *= len(values)
    return combinations * folds


def grid_position(value, candidates) -> str:
    """Where the chosen value sits in its candidate list."""
    ordered = sorted(candidates, key=lambda v: float("inf") if v is None else float(v))
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
    return CONFIG.checkpoints / f"{model_name}__{set_name}.json".lower()


def predictions_path(model_name: str, set_name: str) -> Path:
    return CONFIG.checkpoints / f"{model_name}__{set_name}_preds.npz".lower()


def pipeline_path(model_name: str, set_name: str) -> Path:
    return CONFIG.experiments / f"{model_name}__{set_name}.joblib".lower()


def extra_path(name: str) -> Path:
    """
    Where an extras unit keeps its checkpoint.

    The residual file is named for what it is used for rather than for the
    unit that made it, because the application reads it to build the price
    range it shows a mentor.
    """
    filenames = {
        "learning_curve": "extra_learning_curve.json",
        "residuals": "core_residual_quantiles.json",
        "permutation": "extra_permutation_importance.json",
    }
    return CONFIG.checkpoints / filenames[name]


def temporary_path(target: Path) -> Path:
    """The write-ahead name for a target file, in the same directory."""
    return target.with_name(target.name + ".tmp")


def commit(temporary: Path, target: Path) -> None:
    """Rename a finished temporary file over its target, atomically."""
    os.replace(temporary, target)


def discard(*paths: Path) -> None:
    """Remove temporary files left behind by a unit that raised."""
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def cv_mean_and_sd(search: GridSearchCV, scoring: str) -> tuple[float, float]:
    """
    The CV mean and SD of the selected parameters, read the correct way.

    Why the previous run recorded ``nan +/- nan``. Two mistakes compounded.

    First, GridSearchCV defaults to ``error_score=np.nan``, so a fit that died
    (out of memory, in this case) was recorded as ``nan`` rather than raising,
    and every parameter mean that included such a fold became ``nan``.

    Second, the index was taken with ``np.argmin(-mean_test_score)``. NumPy
    ``argmin`` does not skip ``nan``: a ``nan`` compares false against
    everything, so it propagates and ``argmin`` returns the ``nan`` position.
    The script therefore selected the one parameter combination whose fits had
    failed and copied its ``nan`` mean and ``nan`` SD into the checkpoint. The
    ``best_params`` recorded for those units are the failed combination, not
    the winner, which is why those checkpoints cannot simply be patched with a
    number and must be retrained.

    The fix is ``best_index_``, which scikit-learn derives from
    ``rank_test_score``. Ranking sorts ``nan`` scores last rather than first,
    so a failed combination can never be selected. With ``error_score="raise"``
    there should be no ``nan`` left to rank, so this is the second line of
    defence rather than the first.

    On the negation and the scale: the scorer is
    ``neg_root_mean_squared_error``, so the stored score is an already-rooted
    RMSE with its sign flipped. Flipping the sign back gives RMSE, and no
    further square root is taken, since taking one here would silently report
    the square root of an RMSE. The SD of a negated score equals the SD of the
    score, so it is not negated either. (The ``_sqrt`` in
    ``model_results_v1_sqrt.json`` is unrelated: that file is the first run,
    which used ``max_features="sqrt"``.)
    """
    assert scoring == "neg_root_mean_squared_error", (
        f"the sign and scale handling here assumes "
        f"neg_root_mean_squared_error, not {scoring}"
    )
    best = int(search.best_index_)
    mean = float(-search.cv_results_["mean_test_score"][best])
    sd = float(search.cv_results_["std_test_score"][best])
    return mean, sd


def run_search_unit(
    experiment: Experiment, model_name: str, set_name: str, specs: dict[str, Any]
) -> bool:
    """
    One (model, feature_set) search. Returns False to stop the whole run.

    Nothing is written until the unit has succeeded end to end, and every file
    goes to a temporary name first and is renamed into place at the end, so an
    interrupted unit leaves no half-written checkpoint for a later run to skip
    over.
    """
    label = f"{model_name}/{set_name}"
    free = wait_for_memory(f"search {label}")
    if free is None:
        return False

    spec = specs[model_name]
    features = experiment.feature_sets[set_name]
    started = time.perf_counter()
    log(
        f"START  {label}  ({len(features)} columns, n_jobs={spec['n_jobs']})",
        echo=True,
    )

    X_fit = experiment.rows.iloc[experiment.fit_index][features]
    y_fit = experiment.y.iloc[experiment.fit_index]

    checkpoint_target = checkpoint_path(model_name, set_name)
    predictions_target = predictions_path(model_name, set_name)
    pipeline_target = pipeline_path(model_name, set_name)
    checkpoint_tmp = temporary_path(checkpoint_target)
    predictions_tmp = temporary_path(predictions_target)
    pipeline_tmp = temporary_path(pipeline_target)
    temporaries = (checkpoint_tmp, predictions_tmp, pipeline_tmp)

    try:
        # refit=False so the final fit is ours to time and to memory-check
        # first. error_score="raise" so a failed fold stops this unit loudly
        # instead of being averaged into a nan.
        search = GridSearchCV(
            build_pipeline(clone(spec["estimator"]), features, spec["scale"]),
            param_grid=spec["grid"],
            cv=experiment.cv,
            scoring=SCORING,
            n_jobs=spec["n_jobs"],
            refit=False,
            error_score="raise",
        )
        search.fit(X_fit, y_fit)
        search_seconds = time.perf_counter() - started

        best_index = int(search.best_index_)
        best_params = {
            key: search.cv_results_["params"][best_index][key] for key in spec["grid"]
        }
        cv_mean, cv_sd = cv_mean_and_sd(search, SCORING)
        del search
        gc.collect()

        if not (math.isfinite(cv_mean) and math.isfinite(cv_sd)):
            raise RuntimeError(
                f"{label}: CV mean {cv_mean} and SD {cv_sd} are not both "
                f"finite, so no checkpoint is written"
            )

        free = wait_for_memory(f"refit {label}")
        if free is None:
            discard(*temporaries)
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

        joblib.dump(pipeline, pipeline_tmp, compress=3)
        # Through an open handle, not the path: np.savez_compressed appends
        # ".npz" to any filename that does not already end in it, so passing
        # "..._preds.npz.tmp" would silently write "..._preds.npz.tmp.npz"
        # and the rename below would fail on a file that was never there.
        with predictions_tmp.open("wb") as handle:
            np.savez_compressed(
                handle,
                typical=predictions["typical"],
                all=predictions["all"],
            )

        record = {
            "model": model_name,
            "feature_set": set_name,
            # A checkpoint has to say which profile produced it: the folders
            # are separate, but files get copied between machines.
            "profile": CONFIG.profile,
            "smoke": CONFIG.smoke,
            "cv_folds": experiment.cv_folds,
            "grid": {
                key.replace("model__", ""): [str(v) for v in values]
                for key, values in spec["grid"].items()
            },
            "n_columns": len(features),
            "n_encoded": len(importances["rows"]),
            "best_params": {
                k.replace("model__", ""): str(v) for k, v in best_params.items()
            },
            "best_params_raw": dict(best_params),
            "cv_rmse_log_mean": cv_mean,
            "cv_rmse_log_sd": cv_sd,
            "cv_source": "GridSearchCV.best_index_, error_score=raise",
            "metrics": metrics,
            "grid_edges": edges,
            "importances": importances,
            "search_seconds": round(search_seconds, 1),
            "refit_seconds": round(refit_seconds, 1),
            "wall_seconds": round(search_seconds + refit_seconds, 1),
            "n_jobs": spec["n_jobs"],
            # The folder, not a hardcoded one: a workstation or smoke run
            # writes its pipelines beside its own checkpoints, and notebook 04
            # resolves this string to check the artefact is on disk.
            "artefact": (
                f"models_store/{CONFIG.experiments.name}/{pipeline_target.name}"
            ),
            "artefact_bytes": int(pipeline_tmp.stat().st_size),
            "free_gb_at_start": round(free, 2),
            "commit_gb_at_start": round(memory_status()[1], 2),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }
        checkpoint_tmp.write_text(
            json.dumps(record, indent=2, default=str), encoding="utf-8"
        )

        # The unit has succeeded, so rename the three files into place. The
        # checkpoint goes last, because it is what the skip test and the
        # notebook read to decide the unit is done. The renames are inside the
        # try so that a failure here is cleaned up too: that is not
        # hypothetical, an earlier version of this block left two orphaned
        # temporary files when a rename raised.
        commit(pipeline_tmp, pipeline_target)
        commit(predictions_tmp, predictions_target)
        commit(checkpoint_tmp, checkpoint_target)
    except BaseException:
        # Catches MemoryError and KeyboardInterrupt as well as a raised fold.
        # Leave nothing behind that a later run could mistake for a finished
        # unit, then re-raise so the failure is visible.
        discard(*temporaries)
        log(f"FAILED {label}: nothing written, temporary files removed", echo=True)
        raise

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
    target = checkpoint_path("leakage", "all")
    leakage_tmp = temporary_path(target)

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
        "profile": CONFIG.profile,
        "smoke": CONFIG.smoke,
        "method": "XGBoost at its tuned parameters, refitted on a grouped and a "
        "random split, each scored on its own typical test set",
        "rows": rows,
        "gaps": gaps,
        "wall_seconds": round(elapsed, 1),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    leakage_tmp.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    commit(leakage_tmp, target)
    log(f"DONE   {label}  {elapsed:.1f}s", echo=True)
    return True


# ---------------------------------------------------------------------------
# Extras
# ---------------------------------------------------------------------------
# Three questions the nine main units do not answer, each as its own resumable
# unit with its own checkpoint, and none of them touching a main unit's files.
# They run only under --extras, and they run after the searches because each
# one needs to know which model won a feature set.
EXTRA_UNITS = ("learning_curve", "residuals", "permutation")


def best_model_for(set_name: str) -> str | None:
    """
    The model with the lowest finite CV log RMSE on one feature set.

    Returns ``None`` when a checkpoint is missing or its CV figure is not
    finite, which is how an extras unit decides to skip rather than guess. A
    non-finite CV figure is excluded deliberately: that is exactly the state
    the nan bug left behind, and picking a winner from it would launder a
    failed search into a published result.
    """
    best_name = None
    best_score = float("inf")
    for model_name, candidate_set in UNITS:
        if candidate_set != set_name:
            continue
        path = checkpoint_path(model_name, set_name)
        if not path.exists():
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        score = record.get("cv_rmse_log_mean")
        if not isinstance(score, int | float) or not math.isfinite(float(score)):
            continue
        if float(score) < best_score:
            best_score, best_name = float(score), model_name
    return best_name


def tuned_pipeline(
    model_name: str, set_name: str, experiment: Experiment, specs: dict[str, Any]
) -> tuple[Pipeline, dict[str, Any]]:
    """An unfitted pipeline at a finished unit's stored best parameters."""
    record = json.loads(
        checkpoint_path(model_name, set_name).read_text(encoding="utf-8")
    )
    spec = specs[model_name]
    features = experiment.feature_sets[set_name]
    pipeline = build_pipeline(clone(spec["estimator"]), features, spec["scale"])
    pipeline.set_params(**record["best_params_raw"])
    return pipeline, record


def write_extra(name: str, record: dict[str, Any]) -> Path:
    """Write an extras checkpoint through a temporary name, as the units do."""
    target = extra_path(name)
    temporary = temporary_path(target)
    try:
        temporary.write_text(
            json.dumps(record, indent=2, default=str), encoding="utf-8"
        )
    except BaseException:
        discard(temporary)
        raise
    commit(temporary, target)
    return target


def host_grouped_prefix(
    experiment: Experiment, fraction: float
) -> tuple[np.ndarray, int]:
    """
    A nested fraction of the training rows, taken whole hosts at a time.

    Sampling rows would split a host across the boundary and let a 20% subset
    carry information from a host that is mostly still in the held-out part,
    which is the same leak the grouped split exists to prevent. Hosts are
    shuffled once with the run seed and then taken in that order, so the 20%
    subset is contained in the 40% subset and the curve measures added data
    rather than a different sample each time.
    """
    hosts = experiment.groups.iloc[experiment.fit_index]
    order = pd.Series(hosts.unique())
    order = order.sample(frac=1.0, random_state=RANDOM_SEED).tolist()
    wanted = int(round(fraction * len(experiment.fit_index)))
    chosen: set[Any] = set()
    rows = 0
    counts = hosts.value_counts()
    for host in order:
        if rows >= wanted:
            break
        chosen.add(host)
        rows += int(counts[host])
    keep = hosts.isin(chosen).to_numpy()
    return np.asarray(experiment.fit_index)[keep], len(chosen)


def run_learning_curve_unit(experiment: Experiment, specs: dict[str, Any]) -> bool:
    """
    Test log RMSE against training size, for the core and the full winner.

    The question is whether more mentors would buy more accuracy, or whether
    the curve has already flattened. A flat tail means the ceiling is the
    features, not the sample size, which is the more useful finding for a
    project whose real dataset has not arrived yet.
    """
    label = "extras/learning_curve"
    free = wait_for_memory(f"unit {label}")
    if free is None:
        return False

    targets = {name: best_model_for(name) for name in ("core", "full")}
    if any(model is None for model in targets.values()):
        log(
            f"SKIP   {label}: core and full winners are not both decided yet", echo=True
        )
        return True

    started = time.perf_counter()
    log(
        f"START  {label}  ({targets['core']} on core, {targets['full']} on full)",
        echo=True,
    )

    rows = []
    for set_name, model_name in targets.items():
        features = experiment.feature_sets[set_name]
        for fraction in LEARNING_CURVE_FRACTIONS:
            index, hosts = host_grouped_prefix(experiment, fraction)
            pipeline, record = tuned_pipeline(model_name, set_name, experiment, specs)
            pipeline.fit(
                experiment.rows.iloc[index][features], experiment.y.iloc[index]
            )
            metrics = experiment.evaluate(pipeline, experiment.test_sets["typical"])
            rows.append(
                {
                    "feature_set": set_name,
                    "model": model_name,
                    "fraction": fraction,
                    "train_rows": int(len(index)),
                    "train_hosts": int(hosts),
                    "rmse_log_typical": metrics["rmse_log"],
                    "rmse_aud_typical": metrics["rmse_aud"],
                    "mae_aud_typical": metrics["mae_aud"],
                    "r2_typical": metrics["r2"],
                    "best_params": record["best_params"],
                }
            )
            del pipeline
            gc.collect()

    frame = pd.DataFrame(rows)
    gains = []
    for set_name in targets:
        subset = frame.loc[frame["feature_set"] == set_name].sort_values("fraction")
        first = float(subset["rmse_log_typical"].iloc[0])
        last = float(subset["rmse_log_typical"].iloc[-1])
        penultimate = float(subset["rmse_log_typical"].iloc[-2])
        gains.append(
            {
                "feature_set": set_name,
                "model": targets[set_name],
                "rmse_log_at_20pct": first,
                "rmse_log_at_100pct": last,
                "total_gain_pct": 100 * (first - last) / first,
                # The last step is the one that says whether the curve has
                # flattened: a small number means more data would buy little.
                "last_step_gain_pct": 100 * (penultimate - last) / penultimate,
            }
        )

    record = {
        "unit": "learning_curve",
        "profile": CONFIG.profile,
        "smoke": CONFIG.smoke,
        "method": "each winner refitted at nested host-grouped fractions of the "
        "cleaned training rows, scored on the typical test set",
        "fractions": list(LEARNING_CURVE_FRACTIONS),
        "models": targets,
        "rows": rows,
        "gains": gains,
        "wall_seconds": round(time.perf_counter() - started, 1),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    write_extra("learning_curve", record)
    log(f"DONE   {label}  {record['wall_seconds']:.1f}s", echo=True)
    return True


def run_residuals_unit(experiment: Experiment, specs: dict[str, Any]) -> bool:
    """
    Out-of-fold residual quantiles for the core winner, for the app's range.

    The application has to show a mentor a range, not a point, and the range
    has to come from somewhere defensible. These are the 10th and 90th
    percentiles of the log residual measured out of fold on the training rows,
    so no row contributes to the model that predicted it, and the held-out
    test set is not spent on calibration.

    The quantiles are reported in log space and as multiplicative factors,
    because the model predicts ``log1p(price)``: a residual of q in log space
    is a factor of ``exp(q)`` on the price, so the band the app draws is
    ``expm1(predicted_log + q10)`` to ``expm1(predicted_log + q90)``.
    """
    label = "extras/residuals"
    free = wait_for_memory(f"unit {label}")
    if free is None:
        return False

    model_name = best_model_for("core")
    if model_name is None:
        log(f"SKIP   {label}: the core winner is not decided yet", echo=True)
        return True

    started = time.perf_counter()
    log(f"START  {label}  ({model_name} on core, out of fold)", echo=True)

    features = experiment.feature_sets["core"]
    pipeline, tuned = tuned_pipeline(model_name, "core", experiment, specs)
    index = experiment.fit_index
    X_fit = experiment.rows.iloc[index][features]
    y_fit = experiment.y.iloc[index]
    predicted_log = cross_val_predict(
        pipeline,
        X_fit,
        y_fit,
        cv=experiment.cv,
        n_jobs=specs[model_name]["n_jobs"],
    )
    del pipeline
    gc.collect()

    actual_log = y_fit.to_numpy()
    residual_log = actual_log - np.asarray(predicted_log, dtype=float)
    actual_aud = experiment.rows["price_num"].iloc[index].to_numpy()
    low_q, high_q = RESIDUAL_QUANTILES

    def quantiles(values: np.ndarray) -> dict[str, float]:
        low, high = np.percentile(values, [low_q, high_q])
        return {
            f"q{low_q}_log": float(low),
            f"q{high_q}_log": float(high),
            f"q{low_q}_factor": float(np.exp(low)),
            f"q{high_q}_factor": float(np.exp(high)),
            "median_log": float(np.median(values)),
            "mean_log": float(values.mean()),
            "sd_log": float(values.std()),
        }

    overall = quantiles(residual_log)
    bands = pd.cut(actual_aud, bins=PRICE_BANDS, labels=PRICE_BAND_LABELS, right=False)
    by_band = []
    for band in PRICE_BAND_LABELS:
        # pd.cut on an ndarray returns a Categorical, not a Series, so the
        # comparison is already a plain boolean array.
        mask = np.asarray(bands == band)
        if mask.sum() < 20:
            by_band.append(
                {
                    "band": band,
                    "n": int(mask.sum()),
                    "note": "fewer than 20 rows, quantiles not reported",
                }
            )
            continue
        by_band.append(
            {"band": band, "n": int(mask.sum()), **quantiles(residual_log[mask])}
        )

    record = {
        "unit": "residuals",
        "profile": CONFIG.profile,
        "smoke": CONFIG.smoke,
        "model": model_name,
        "feature_set": "core",
        "best_params": tuned["best_params"],
        "method": f"{experiment.cv_folds}-fold out-of-fold predictions on the "
        f"cleaned training rows; residual = log1p(actual) - log1p(predicted)",
        "used_for": "the price range the application shows a mentor",
        "how_to_apply": "low = expm1(predicted_log + q10_log), "
        "high = expm1(predicted_log + q90_log); equivalently multiply the "
        "predicted price by q10_factor and q90_factor",
        "quantiles": list(RESIDUAL_QUANTILES),
        "train_rows": int(len(index)),
        "overall": overall,
        "by_price_band": by_band,
        "price_bands": PRICE_BAND_LABELS,
        "wall_seconds": round(time.perf_counter() - started, 1),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    write_extra("residuals", record)
    log(
        f"DONE   {label}  q{low_q} {overall[f'q{low_q}_log']:+.4f} to "
        f"q{high_q} {overall[f'q{high_q}_log']:+.4f} log "
        f"(x{overall[f'q{low_q}_factor']:.2f} to "
        f"x{overall[f'q{high_q}_factor']:.2f})  "
        f"{record['wall_seconds']:.1f}s",
        echo=True,
    )
    return True


def run_permutation_unit(experiment: Experiment, specs: dict[str, Any]) -> bool:
    """
    Permutation importance on the typical test set for both winners.

    The built-in importances are model-internal: gain for XGBoost, impurity
    decrease for the forest, a coefficient for Ridge, none of them comparable
    across families and all of them measured on the training data. Permutation
    importance is measured on held-out rows and in the units of the metric, so
    it answers a different and more honest question: how much worse does this
    model get when this column is made useless.

    The saved pipeline is loaded from disk rather than refitted, so this costs
    predictions rather than fits, and the columns permuted are the source
    columns, not the one-hot encodings, so a neighbourhood is scored as one
    feature instead of 60 fragments.
    """
    label = "extras/permutation"
    free = wait_for_memory(f"unit {label}")
    if free is None:
        return False

    targets = {name: best_model_for(name) for name in ("core", "full")}
    if any(model is None for model in targets.values()):
        log(
            f"SKIP   {label}: core and full winners are not both decided yet", echo=True
        )
        return True
    missing = [
        f"{model}/{set_name}"
        for set_name, model in targets.items()
        if not pipeline_path(model, set_name).exists()
    ]
    if missing:
        log(
            f"SKIP   {label}: fitted pipeline missing for {', '.join(missing)}",
            echo=True,
        )
        return True

    repeats = CONFIG.permutation_repeats
    started = time.perf_counter()
    log(f"START  {label}  ({repeats} repeats on the typical test set)", echo=True)

    index = experiment.test_sets["typical"]
    results = {}
    for set_name, model_name in targets.items():
        features = experiment.feature_sets[set_name]
        pipeline = joblib.load(pipeline_path(model_name, set_name))
        computed = permutation_importance(
            pipeline,
            experiment.rows.iloc[index][features],
            experiment.y.iloc[index],
            scoring=SCORING,
            n_repeats=repeats,
            n_jobs=specs[model_name]["n_jobs"],
            random_state=RANDOM_SEED,
        )
        del pipeline
        gc.collect()
        table = pd.DataFrame(
            {
                "source_column": features,
                # A positive value is a rise in RMSE when the column is
                # shuffled, so larger means the model relies on it more.
                "rmse_log_increase": computed.importances_mean,
                "sd": computed.importances_std,
            }
        )
        table["group"] = table["source_column"].map(GROUP_OF_COLUMN).fillna("other")
        total = float(table["rmse_log_increase"].clip(lower=0).sum())
        table["share_pct"] = (
            100 * table["rmse_log_increase"].clip(lower=0) / total if total else np.nan
        )
        table = table.sort_values(
            "rmse_log_increase", ascending=False, ignore_index=True
        )
        table.insert(0, "rank", np.arange(1, len(table) + 1))
        group_shares = (
            table.groupby("group")["share_pct"].sum().sort_values(ascending=False)
        )
        results[set_name] = {
            "model": model_name,
            "rows": table.to_dict(orient="records"),
            "group_shares_pct": {k: float(v) for k, v in group_shares.items()},
        }

    record = {
        "unit": "permutation",
        "profile": CONFIG.profile,
        "smoke": CONFIG.smoke,
        "method": f"sklearn permutation_importance, {repeats} repeats, "
        f"{SCORING} on the typical test set, source columns not encodings",
        "n_repeats": repeats,
        "test_rows": int(len(index)),
        "models": targets,
        "by_feature_set": results,
        "wall_seconds": round(time.perf_counter() - started, 1),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    write_extra("permutation", record)
    log(f"DONE   {label}  {record['wall_seconds']:.1f}s", echo=True)
    return True


EXTRA_RUNNERS = {
    "learning_curve": run_learning_curve_unit,
    "residuals": run_residuals_unit,
    "permutation": run_permutation_unit,
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
# Ridge first (almost free), then XGBoost, then Random Forest last because it
# is the memory risk. Within Random Forest the cheapest set runs first, so a
# failure on the largest still leaves the smaller ones checkpointed. This is
# the sequential order; --parallel-units reorders to heaviest first instead,
# which is the right order when units run side by side rather than in turn.
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
LEAKAGE_UNIT = ("leakage", "all")

# Relative cost, used only to order a parallel run. Taken from the measured
# run 3 wall times (Ridge seconds, XGBoost/full 31 minutes, forests in
# between) and scaled by feature count. Wrong by a factor of two does no harm:
# it decides dispatch order, nothing else.
UNIT_WEIGHTS: dict[tuple[str, str], float] = {
    ("RandomForest", "full"): 100.0,
    ("XGBoost", "full"): 90.0,
    ("RandomForest", "core_plus_space"): 35.0,
    ("RandomForest", "core"): 30.0,
    ("XGBoost", "core"): 25.0,
    ("XGBoost", "core_plus_space"): 22.0,
    ("Ridge", "full"): 1.0,
    ("Ridge", "core_plus_space"): 0.5,
    ("Ridge", "core"): 0.4,
}

# The keys a finished search checkpoint must carry. Anything missing means the
# file was written by an older version of this script or was truncated.
REQUIRED_SEARCH_KEYS = (
    "model",
    "feature_set",
    "n_columns",
    "n_encoded",
    "best_params",
    "best_params_raw",
    "cv_rmse_log_mean",
    "cv_rmse_log_sd",
    "metrics",
    "grid_edges",
    "importances",
    "wall_seconds",
    "artefact",
    "finished_at",
)
REQUIRED_LEAKAGE_KEYS = ("unit", "method", "rows", "gaps", "finished_at")
REQUIRED_EXTRA_KEYS = ("unit", "method", "wall_seconds", "finished_at")


def inspect_checkpoint(model_name: str, set_name: str) -> dict[str, Any]:
    """
    Read one checkpoint and judge it, without loading any data or model.

    ``complete`` means: the JSON parses, every required key is present, the CV
    mean and SD are finite, and the predictions file and the fitted pipeline
    are both on disk. The leakage unit and the extras have no pipeline or
    predictions, so only their own keys are checked.
    """
    label = f"{model_name}/{set_name}"
    is_leakage = (model_name, set_name) == LEAKAGE_UNIT
    is_extra = model_name == "extras"
    path = extra_path(set_name) if is_extra else checkpoint_path(model_name, set_name)
    report: dict[str, Any] = {
        "unit": label,
        "checkpoint": path.name,
        "optional": is_extra,
        "exists": path.exists(),
        "cv_mean": None,
        "cv_sd": None,
        "cv_finite": False,
        "complete": False,
        "profile": None,
        "notes": [],
    }
    if not path.exists():
        report["notes"].append("no checkpoint")
        if temporary_path(path).exists():
            report["notes"].append("a .tmp file is present, so a unit was interrupted")
        return report

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        report["notes"].append(f"unreadable JSON: {error}")
        return report

    report["profile"] = record.get("profile")
    if is_extra:
        required: tuple[str, ...] = REQUIRED_EXTRA_KEYS
    elif is_leakage:
        required = REQUIRED_LEAKAGE_KEYS
    else:
        required = REQUIRED_SEARCH_KEYS
    missing = [key for key in required if key not in record]
    if missing:
        report["notes"].append("missing keys: " + ", ".join(missing))

    if is_extra or is_leakage:
        # Neither carries a CV figure, so there is nothing to be non-finite.
        report["cv_finite"] = True
        if is_leakage:
            report["notes"].append(
                f"{len(record.get('rows', []))} rows, "
                f"{len(record.get('gaps', []))} gaps"
            )
            report["complete"] = not missing and bool(record.get("rows"))
        else:
            report["complete"] = not missing
        return report

    mean = record.get("cv_rmse_log_mean")
    sd = record.get("cv_rmse_log_sd")
    report["cv_mean"] = mean
    report["cv_sd"] = sd
    report["cv_finite"] = (
        isinstance(mean, int | float)
        and isinstance(sd, int | float)
        and math.isfinite(float(mean))
        and math.isfinite(float(sd))
    )
    if not report["cv_finite"]:
        report["notes"].append(
            "CV mean or SD is not finite, so this unit needs --force or --backfill-cv"
        )

    predictions = predictions_path(model_name, set_name)
    pipeline = pipeline_path(model_name, set_name)
    if not predictions.exists():
        report["notes"].append(f"predictions missing: {predictions.name}")
    if not pipeline.exists():
        report["notes"].append(f"pipeline missing: {pipeline.name}")
    for target in (path, predictions, pipeline):
        if temporary_path(target).exists():
            report["notes"].append(
                f"stray temporary file: {temporary_path(target).name}"
            )

    report["complete"] = (
        not missing
        and report["cv_finite"]
        and predictions.exists()
        and pipeline.exists()
    )
    report["n_jobs"] = record.get("n_jobs")
    report["finished_at"] = record.get("finished_at")
    return report


def verify_checkpoints(include_extras: bool = True) -> int:
    """
    Report on every checkpoint on disk. Trains nothing, loads nothing.

    Returns 0 when the nine search units and the leakage unit are all
    complete, and 1 otherwise, so a shell or a notebook can branch on it. The
    extras are listed but never decide the exit code: they are optional by
    design, and a missing one is not a broken run.
    """
    required_units = [*UNITS, LEAKAGE_UNIT]
    listed = list(required_units)
    if include_extras:
        listed += [("extras", name) for name in EXTRA_UNITS]

    print(f"verify-only, {CONFIG.describe()}")
    print(f"checkpoints: reports/{CONFIG.checkpoints.name}")
    print()
    header = (
        f"{'unit':34} {'exists':7} {'CV mean':>9} {'CV SD':>8} {'finite':7} complete"
    )
    print(header)
    print("-" * len(header))
    reports = [inspect_checkpoint(m, s) for m, s in listed]
    for report in reports:
        mean = report["cv_mean"]
        sd = report["cv_sd"]
        mean_text = f"{mean:9.4f}" if isinstance(mean, int | float) else f"{'-':>9}"
        sd_text = f"{sd:8.4f}" if isinstance(sd, int | float) else f"{'-':>8}"
        if mean is None:
            mean_text = f"{'n/a':>9}"
            sd_text = f"{'n/a':>8}"
        suffix = " (optional)" if report["optional"] else ""
        print(
            f"{report['unit']:34} {str(report['exists']):7} {mean_text} {sd_text} "
            f"{str(report['cv_finite']):7} {report['complete']}{suffix}"
        )
    print()
    for report in reports:
        for note in report["notes"]:
            print(f"  {report['unit']}: {note}")

    profiles = {r["profile"] for r in reports if r["exists"] and r["profile"]}
    if profiles:
        print()
        print(f"profiles recorded in these checkpoints: {sorted(profiles)}")
        if len(profiles) > 1:
            print(
                "  WARNING: more than one profile in one folder, which should "
                "not happen; the folders are meant to be separate"
            )

    required_reports = reports[: len(required_units)]
    complete = sum(1 for r in required_reports if r["complete"])
    print()
    print(f"{complete} of {len(required_units)} required units are complete")
    if include_extras:
        extras_done = sum(1 for r in reports[len(required_units) :] if r["complete"])
        print(f"{extras_done} of {len(EXTRA_UNITS)} extras are present (optional)")
    not_finite = [
        r["unit"] for r in required_reports if r["exists"] and not r["cv_finite"]
    ]
    if not_finite:
        print("units with a non-finite CV value: " + ", ".join(not_finite))
    missing = [r["unit"] for r in required_reports if not r["exists"]]
    if missing:
        print("units with no checkpoint: " + ", ".join(missing))
    ok = complete == len(required_units)
    print()
    print("VERIFY OK" if ok else "VERIFY INCOMPLETE")
    return 0 if ok else 1


def backfill_cv_unit(
    experiment: Experiment, model_name: str, set_name: str, specs: dict[str, Any]
) -> bool:
    """
    Recompute one finished unit's CV mean and SD in place.

    This reruns cross-validation at the parameters already stored in the
    checkpoint, on the same cleaned training rows, with the same pipeline and
    the same ``KFold(shuffle=True, random_state=42)`` folds, and with
    ``error_score="raise"`` so a failure stops rather than returning a ``nan``.
    Nothing else in the checkpoint is touched and no model is saved: the fitted
    pipeline and the test metrics already on disk are left exactly as they are.

    This repairs the CV numbers only. It does not re-select the parameters, so
    a unit whose stored ``best_params`` came from the ``argmin`` bug is still
    tuned wrongly after a backfill and should be retrained with --force
    instead. The function is kept because recomputing a CV figure is minutes
    where a retrain is an hour, which is the right trade when the parameters
    themselves are known to be sound.
    """
    label = f"{model_name}/{set_name}"
    path = checkpoint_path(model_name, set_name)
    if not path.exists():
        log(f"SKIP   backfill {label}: no checkpoint", echo=True)
        return True

    free = wait_for_memory(f"backfill {label}")
    if free is None:
        return False

    record = json.loads(path.read_text(encoding="utf-8"))
    best_params = record["best_params_raw"]
    spec = specs[model_name]
    features = experiment.feature_sets[set_name]

    started = time.perf_counter()
    log(f"START  backfill {label} at {best_params}", echo=True)

    pipeline = build_pipeline(clone(spec["estimator"]), features, spec["scale"])
    pipeline.set_params(**best_params)
    scores = cross_validate(
        pipeline,
        experiment.rows.iloc[experiment.fit_index][features],
        experiment.y.iloc[experiment.fit_index],
        cv=experiment.cv,
        scoring=SCORING,
        n_jobs=spec["n_jobs"],
        error_score="raise",
        return_train_score=False,
    )
    fold_rmse = -np.asarray(scores["test_score"], dtype=float)
    cv_mean = float(fold_rmse.mean())
    cv_sd = float(fold_rmse.std())
    del pipeline
    gc.collect()

    if not (math.isfinite(cv_mean) and math.isfinite(cv_sd)):
        raise RuntimeError(
            f"{label}: backfilled CV mean {cv_mean} and SD {cv_sd} are not "
            f"both finite, so the checkpoint is left unchanged"
        )

    previous_mean = record.get("cv_rmse_log_mean")
    previous_sd = record.get("cv_rmse_log_sd")
    record["cv_rmse_log_mean"] = cv_mean
    record["cv_rmse_log_sd"] = cv_sd
    record["cv_source"] = (
        f"--backfill-cv: {experiment.cv_folds}-fold cross_validate at the stored "
        f"best_params, error_score=raise"
    )
    record["cv_backfill"] = {
        "profile": CONFIG.profile,
        "previous_mean": previous_mean,
        "previous_sd": previous_sd,
        "folds": experiment.cv_folds,
        "fold_rmse_log": [float(v) for v in fold_rmse],
        "seconds": round(time.perf_counter() - started, 1),
        "note": "CV figures only. best_params and the test metrics are unchanged.",
        "backfilled_at": datetime.now().isoformat(timespec="seconds"),
    }

    temporary = temporary_path(path)
    try:
        temporary.write_text(
            json.dumps(record, indent=2, default=str), encoding="utf-8"
        )
    except BaseException:
        discard(temporary)
        raise
    commit(temporary, path)

    log(
        f"DONE   backfill {label}  CV log RMSE {cv_mean:.4f} +/- {cv_sd:.4f} "
        f"(was {previous_mean} +/- {previous_sd})  "
        f"{record['cv_backfill']['seconds']:.1f}s",
        echo=True,
    )
    return True


def selected_units(
    only: str | None, extras: bool
) -> tuple[list[tuple[str, str]], bool, list[str]] | None:
    """
    Resolve --only into search units, whether to run leakage, and which extras.

    ``--only leakage`` runs the leakage unit alone. ``--only extras`` runs all
    three extras. ``--only learning_curve`` (or ``extras/learning_curve``) runs
    that one extra. ``--only Model/feature_set`` runs that search alone.
    Without the flag everything runs, and the extras only if --extras is on.
    """
    if not only:
        return list(UNITS), True, list(EXTRA_UNITS) if extras else []

    wanted = only.strip()
    lowered = wanted.lower()
    if lowered == "leakage":
        return [], True, []
    if lowered == "extras":
        return [], False, list(EXTRA_UNITS)
    bare = wanted.split("/", 1)[-1]
    if bare in EXTRA_UNITS:
        return [], False, [bare]
    pair = tuple(wanted.split("/", 1))
    units = [u for u in UNITS if u == pair]
    if not units:
        return None
    return units, False, []


def unit_label(unit: tuple[str, str]) -> str:
    return f"{unit[0]}/{unit[1]}"


def pending_units(units: list[tuple[str, str]], force: bool) -> list[tuple[str, str]]:
    """The units that still need running, heaviest first."""
    todo = [u for u in units if force or not checkpoint_path(*u).exists()]
    return sorted(todo, key=lambda u: -UNIT_WEIGHTS.get(u, 1.0))


def child_command(unit_only: str, n_jobs: int, args: argparse.Namespace) -> list[str]:
    """The command line for one unit in its own process."""
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--only",
        unit_only,
        "--n-jobs",
        str(n_jobs),
        "--profile",
        CONFIG.profile,
    ]
    if CONFIG.smoke:
        command.append("--smoke")
    if args.force:
        command.append("--force")
    if args.extras:
        command.append("--extras")
    if args.min_ram_gb is not None:
        command += ["--min-ram-gb", str(args.min_ram_gb)]
    if args.min_commit_gb is not None:
        command += ["--min-commit-gb", str(args.min_commit_gb)]
    return command


def run_unit_subprocess(
    unit_only: str, n_jobs: int, args: argparse.Namespace
) -> tuple[str, int, list[str]]:
    """
    Run one unit in a child process, echoing its output with a unit prefix.

    One process per unit is what makes a parallel run safe. The units are
    already independent on disk (each writes only its own files, through a
    temporary name renamed on success), so the only thing left to isolate is
    memory, and a process does that completely: when a unit finishes, the
    operating system reclaims everything it held, including whatever the
    forest left fragmented. It also contains a crash, which a thread would
    not: a child that dies of MemoryError takes down its own unit and nothing
    else.
    """
    command = child_command(unit_only, n_jobs, args)
    environment = {**os.environ, **CONFIG.as_env(), "PYTHONUNBUFFERED": "1"}
    captured: list[str] = []
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=environment,
        cwd=str(PROJECT_ROOT),
    )
    assert process.stdout is not None
    for line in process.stdout:
        line = line.rstrip()
        captured.append(line)
        print(f"  [{unit_only}] {line}", flush=True)
    process.stdout.close()
    return unit_only, process.wait(), captured


def run_parallel(
    units: list[tuple[str, str]],
    include_leakage: bool,
    extras: list[str],
    parallel_units: int,
    n_jobs: int,
    args: argparse.Namespace,
) -> int:
    """
    Run the units K at a time in separate processes, in dependency waves.

    Two waves, because the later units read the earlier ones' checkpoints: the
    leakage unit needs all three XGBoost units tuned, and every extra needs to
    know which model won a feature set. Running them in the same wave as the
    searches would have them skip for want of a file that was about to be
    written, which is a silent half-result, so they wait.

    A unit that fails does not stop the others. That is the whole point of
    checkpointed units: one failure costs one unit, the rest of the wave
    finishes, and the summary at the end says exactly which ones to rerun.
    """
    wave_one = pending_units(units, args.force)
    wave_two: list[str] = []
    if include_leakage and (args.force or not checkpoint_path(*LEAKAGE_UNIT).exists()):
        wave_two.append("leakage")
    for name in extras:
        if args.force or not extra_path(name).exists():
            wave_two.append(name)

    print()
    print(
        f"parallel plan: {parallel_units} units at a time, "
        f"n_jobs={n_jobs} each, {parallel_units * n_jobs} threads at peak "
        f"on {os.cpu_count()} cores"
    )
    print(f"{'wave':6} {'unit':34} {'weight':>7} n_jobs")
    print("-" * 58)
    for unit in wave_one:
        print(
            f"{'1':6} {unit_label(unit):34} "
            f"{UNIT_WEIGHTS.get(unit, 1.0):7.1f} {n_jobs}"
        )
    for name in wave_two:
        print(f"{'2':6} {name:34} {'-':>7} {n_jobs}")
    skipped = [u for u in units if u not in wave_one]
    for unit in skipped:
        print(f"{'-':6} {unit_label(unit):34} {'-':>7} skip, checkpoint exists")
    if not wave_one and not wave_two:
        print("nothing to do: every requested unit already has a checkpoint")
        return 0
    print()

    results: dict[str, int] = {}
    tails: dict[str, list[str]] = {}
    for wave, names in (
        (1, [unit_label(u) for u in wave_one]),
        (2, wave_two),
    ):
        if not names:
            continue
        log(
            f"wave {wave} starting: {len(names)} unit(s), "
            f"{parallel_units} at a time",
            echo=True,
        )
        workers = max(1, min(parallel_units, len(names)))
        # Threads, not processes, in the parent: each thread does nothing but
        # wait on a child process and copy its output, so the GIL is irrelevant
        # and the parent stays small.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(run_unit_subprocess, name, n_jobs, args) for name in names
            ]
            for future in futures:
                name, code, output = future.result()
                results[name] = code
                tails[name] = output[-12:]
        failed_in_wave = [n for n in names if results.get(n, 1) != 0]
        if failed_in_wave:
            log(
                f"wave {wave} finished with {len(failed_in_wave)} failure(s): "
                f"{', '.join(failed_in_wave)}",
                echo=True,
            )
        else:
            log(f"wave {wave} finished, all {len(names)} unit(s) succeeded", echo=True)

    succeeded = [name for name, code in results.items() if code == 0]
    failed = [name for name, code in results.items() if code != 0]
    print()
    print("=" * 70)
    print(f"parallel run summary: {len(succeeded)} succeeded, {len(failed)} failed")
    print("=" * 70)
    for name in succeeded:
        print(f"  OK     {name}")
    for name in failed:
        print(f"  FAILED {name}  (exit {results[name]})")
        for line in tails[name]:
            print(f"           {line}")
    if failed:
        print()
        print(
            "Re-running this command resumes: the units that succeeded have "
            "checkpoints and will be skipped."
        )
    return 1 if failed else 0


def write_context(
    experiment: Experiment, rf_max_features, rf_evidence, force: bool
) -> Path:
    """
    Write _context.json, atomically, once.

    The parent writes it before dispatching. A child started by the dispatcher
    gets --only, so it leaves the file alone unless it is missing, and the
    write is a temporary file renamed into place, so even two processes racing
    on it cannot produce a half-written file.
    """
    target = CONFIG.checkpoints / "_context.json"
    if target.exists() and not force:
        return target
    temporary = temporary_path(target)
    payload = experiment.context(rf_max_features, rf_evidence)
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
    except BaseException:
        discard(temporary)
        raise
    commit(temporary, target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(
        # The module docstring is for a reader of the file. Printing all of it
        # here buried the flags.
        description="Checkpointed, memory-safe training for the three "
        "candidate models, as 9 resumable (model, feature_set) units plus the "
        "leakage check and the optional extras.",
        epilog="Fits are loud: every search and cross-validation runs with "
        "error_score=raise, and no checkpoint is written for a unit that "
        "raised. See the module docstring for why.",
    )
    parser.add_argument(
        "--profile",
        choices=PROFILES,
        default="standard",
        help="grid size. standard is the laptop grid; workstation widens the "
        "XGBoost and Random Forest grids and puts max_depth=None back. Each "
        "profile keeps its own checkpoint folder (default: standard)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="redo units that already have a checkpoint",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="one unit only: Model/feature_set such as RandomForest/full, or "
        "leakage, or extras, or one extra such as residuals",
    )
    parser.add_argument(
        "--n-jobs",
        type=int,
        default=None,
        help="threads per unit, for GridSearchCV and the Random Forest, and "
        "the floor for XGBoost. -1 means every core, divided by "
        "--parallel-units. Unset means 1, or cores//K under --parallel-units",
    )
    parser.add_argument(
        "--parallel-units",
        type=int,
        default=1,
        help="run up to K units at the same time, each in its own process "
        "(default 1, which runs them in turn in this process)",
    )
    parser.add_argument(
        "--extras",
        action="store_true",
        help="also run the learning curve, the out-of-fold residual quantiles "
        "and the permutation importance, each as its own resumable unit",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        # No percent sign in a help string: argparse runs it through
        # printf-style interpolation and a bare % raises.
        help=f"prove the pipeline executes: {SMOKE_CV_FOLDS}-fold CV, a "
        f"{SMOKE_ROW_FRACTION:.2f} fraction of the rows, single-value grids, "
        f"50 trees, written to reports/checkpoints_smoke so nothing real is "
        f"touched",
    )
    parser.add_argument(
        "--min-ram-gb",
        type=float,
        default=None,
        help=f"refuse to start a fit below this much free RAM (default "
        f"{MIN_FREE_GB} standard, {MIN_FREE_GB_WORKSTATION} workstation)",
    )
    parser.add_argument(
        "--min-commit-gb",
        type=float,
        default=None,
        help=f"refuse to start a fit below this much commit headroom (default "
        f"{MIN_COMMIT_GB} standard, {MIN_COMMIT_GB_WORKSTATION} workstation)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="report on the existing checkpoints and exit, training nothing",
    )
    parser.add_argument(
        "--backfill-cv",
        action="store_true",
        help="recompute the CV mean and SD of finished units at their stored "
        "best_params, writing only those two fields back; combine with --only "
        "for one unit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list what each unit would do, skip or run, and fit nothing",
    )
    args = parser.parse_args()

    global LOG_LABEL
    configure(
        profile=args.profile,
        smoke=args.smoke,
        min_ram_gb=args.min_ram_gb,
        min_commit_gb=args.min_commit_gb,
    )
    # A child process started by the dispatcher runs exactly one unit, so
    # tagging its log lines with that unit is enough to read an interleaved log.
    if args.only:
        LOG_LABEL = args.only

    for directory in (CONFIG.checkpoints, CONFIG.experiments):
        directory.mkdir(parents=True, exist_ok=True)

    if args.verify_only:
        return verify_checkpoints(include_extras=True)

    if args.n_jobs is not None and args.n_jobs != -1 and args.n_jobs < 1:
        print("--n-jobs must be 1 or more, or -1 for every core", flush=True)
        return 2
    if args.parallel_units < 1:
        print("--parallel-units must be 1 or more", flush=True)
        return 2

    resolved = selected_units(args.only, args.extras)
    if resolved is None:
        print(f"no unit matches {args.only}", flush=True)
        return 2
    units, include_leakage, extras = resolved

    n_jobs = resolve_n_jobs(args.n_jobs, args.parallel_units)
    cores = os.cpu_count() or 1
    free, commit_free = memory_status()
    print(f"{CONFIG.describe()}")
    print(
        f"n_jobs={n_jobs} per unit (GridSearchCV and Random Forest; XGBoost "
        f"floored at {N_JOBS_XGBOOST}), parallel_units={args.parallel_units}, "
        f"cores={cores}"
    )
    print(
        f"memory floors: RAM {CONFIG.ram_floor} GB, commit "
        f"{CONFIG.commit_floor} GB; now RAM {free:.2f} GB, commit "
        f"{commit_free:.2f} GB"
    )
    if args.parallel_units * n_jobs > cores:
        print(
            f"WARNING: {args.parallel_units} units x {n_jobs} threads = "
            f"{args.parallel_units * n_jobs} exceeds {cores} cores, so the "
            f"units will contend for CPU"
        )
    print(f"checkpoints: reports/{CONFIG.checkpoints.name}")
    print(f"pipelines  : models_store/{CONFIG.experiments.name}")

    if args.dry_run:
        print()
        print(f"dry run, force={args.force}, only={args.only}, extras={args.extras}")
        print(f"{'unit':34} {'checkpoint':11} {'fits':>6} action")
        print("-" * 72)
        for model_name, set_name in units:
            path = checkpoint_path(model_name, set_name)
            exists = path.exists()
            action = "RUN" if args.force or not exists else "SKIP"
            reason = (
                "forced"
                if args.force and exists
                else ("checkpoint exists" if exists else "no checkpoint")
            )
            fits = grid_fit_count(CONFIG.grids[model_name], CONFIG.cv_folds)
            print(
                f"{model_name + '/' + set_name:34} {str(exists):11} {fits:6d} "
                f"{action}, {reason}"
            )
        if include_leakage:
            exists = checkpoint_path(*LEAKAGE_UNIT).exists()
            action = "RUN" if args.force or not exists else "SKIP"
            print(f"{'leakage/all':34} {str(exists):11} {'-':>6} {action}")
        for name in extras:
            exists = extra_path(name).exists()
            action = "RUN" if args.force or not exists else "SKIP"
            print(f"{'extras/' + name:34} {str(exists):11} {'-':>6} {action}")
        print()
        print("nothing was fitted")
        return 0

    log("=" * 70)
    log(
        f"run starting, {CONFIG.describe()}, force={args.force}, "
        f"only={args.only}, n_jobs={n_jobs}, "
        f"parallel_units={args.parallel_units}, extras={args.extras}, "
        f"backfill_cv={args.backfill_cv}",
        echo=True,
    )

    rf_max_features, rf_evidence = rule_selected_max_features()
    log(
        f"Random Forest max_features={rf_max_features} selected by the "
        f"{RF_MAX_FEATURES_TOLERANCE:.0%} tolerance rule from the stored probe",
        echo=True,
    )

    # The dispatcher needs the context file and the plan, but no model, so it
    # builds the Experiment once (index arithmetic on a 1.3 MB parquet) and
    # then does nothing but supervise child processes.
    experiment = Experiment()
    specs = model_specs(rf_max_features, n_jobs)
    context_path = write_context(
        experiment, rf_max_features, rf_evidence, force=not args.only
    )
    log(
        f"context written to reports/{CONFIG.checkpoints.name}/{context_path.name}",
        echo=True,
    )
    log(
        f"fences {experiment.lower_aud:,.2f} to {experiment.upper_aud:,.2f} "
        f"{CURRENCY}; training rows {len(experiment.fit_index):,}; "
        f"typical test {len(experiment.test_sets['typical']):,}; "
        f"all test {len(experiment.test_sets['all']):,}",
        echo=True,
    )

    if args.backfill_cv:
        # Without --only or --force, only the units whose CV figures are
        # broken are touched. Recomputing a figure that is already finite
        # would replace a recorded number with an equal one at the cost of
        # another set of fits, and would make the checkpoint look repaired
        # when nothing was wrong with it.
        for model_name, set_name in units:
            healthy = inspect_checkpoint(model_name, set_name)["cv_finite"]
            if healthy and not (args.only or args.force):
                log(
                    f"SKIP   backfill {model_name}/{set_name}: CV figures are "
                    f"already finite",
                    echo=True,
                )
                continue
            if not backfill_cv_unit(experiment, model_name, set_name, specs):
                log("stopping cleanly: the memory floors were not met", echo=True)
                return 1
        log("backfill finished", echo=True)
        print()
        return verify_checkpoints(include_extras=args.extras)

    if args.parallel_units > 1:
        # Free the parent's copy of the data before any child starts: the
        # children load their own, and on a 64 GB machine this hardly matters,
        # but on the laptop it is the difference between two smoke units
        # running and one of them waiting on the memory floor.
        del experiment
        gc.collect()
        started = time.perf_counter()
        code = run_parallel(
            units, include_leakage, extras, args.parallel_units, n_jobs, args
        )
        print()
        print(
            f"total parallel wall time: "
            f"{(time.perf_counter() - started) / 60:.1f} minutes"
        )
        return code

    done = skipped = 0
    for model_name, set_name in units:
        path = checkpoint_path(model_name, set_name)
        if path.exists() and not args.force:
            skipped += 1
            log(f"SKIP   {model_name}/{set_name}: checkpoint exists", echo=True)
            continue
        if not run_search_unit(experiment, model_name, set_name, specs):
            log("stopping cleanly: the memory floors were not met", echo=True)
            return 1
        done += 1

    leakage = checkpoint_path(*LEAKAGE_UNIT)
    if include_leakage:
        if leakage.exists() and not args.force:
            log("SKIP   leakage/all: checkpoint exists", echo=True)
        elif not run_leakage_unit(experiment, specs):
            log("stopping cleanly: the memory floors were not met", echo=True)
            return 1

    for name in extras:
        if extra_path(name).exists() and not args.force:
            log(f"SKIP   extras/{name}: checkpoint exists", echo=True)
            continue
        if not EXTRA_RUNNERS[name](experiment, specs):
            log("stopping cleanly: the memory floors were not met", echo=True)
            return 1

    complete = sum(1 for m, s in UNITS if checkpoint_path(m, s).exists())
    log(
        f"run finished: {done} unit(s) trained, {skipped} skipped, "
        f"{complete} of {len(UNITS)} search units complete, "
        f"leakage {'done' if leakage.exists() else 'pending'}, "
        f"extras {sum(1 for n in EXTRA_UNITS if extra_path(n).exists())} "
        f"of {len(EXTRA_UNITS)} present",
        echo=True,
    )
    # Reaching here means no unit raised: a failed fit propagates out of
    # run_search_unit rather than being counted, which is the whole point of
    # error_score="raise".
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
