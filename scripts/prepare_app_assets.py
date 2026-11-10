"""
Prepare everything the API needs to serve prices, into ``app_assets/``.

The trained pipelines, the training reports and the processed dataset are all
gitignored, so a fresh clone cannot serve a price. This script is the one step
that turns a local training run into a servable application: it copies the two
chosen pipelines, derives the price range each one should show, and writes the
metadata the API reads at startup.

``app_assets/`` is gitignored too. It is a build output, not source: delete it
and run this script again.

Run from the project root:

    python scripts/prepare_app_assets.py

Every input is checked before anything is written, so a missing file fails with
a message naming the file rather than half-populating the folder.
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Inputs. All gitignored, all produced by scripts/train_experiments.py or by
# the dataset-build notebook.
EXPERIMENTS_DIR = PROJECT_ROOT / "models_store" / "experiments_workstation"
CHECKPOINTS_DIR = PROJECT_ROOT / "reports" / "checkpoints_workstation"
COLUMN_SETS = PROJECT_ROOT / "reports" / "column_sets.json"
MASTER_DATASET = PROJECT_ROOT / "data" / "processed" / "master_listings.parquet"

# The results file has been written to both places across runs, so both are
# accepted and the one actually used is reported.
MODEL_RESULTS_CANDIDATES = (
    PROJECT_ROOT / "reports" / "model_results.json",
    PROJECT_ROOT / "model_results.json",
    PROJECT_ROOT / "reports" / "model_results (1).json",
)

# Output.
APP_ASSETS = PROJECT_ROOT / "app_assets"
MODELS_OUT = APP_ASSETS / "models"
RANGES_OUT = APP_ASSETS / "ranges.json"
MODEL_INFO_OUT = APP_ASSETS / "model_info.json"

# Not written here. scripts/build_comparables.py produces it, and it reads the
# price fences out of model_info.json, so it has to run after this script.
# Checked for and reported at the end rather than built, because the two are
# independent: the API prices every service without it and simply cannot say
# what other mentors charge.
COMPARABLES = APP_ASSETS / "comparables.parquet"

# The two served models. "core" is the new-mentor model, "full" adds the
# history columns a returning mentor has accumulated.
WINNING_ALGORITHM = "xgboost"
SERVED_MODELS = ("core", "full")

CURRENCY = "AUD"

# Reproduced from scripts/train_experiments.py so the held-out split used for
# the full model's residuals is the same split it was scored on.
RANDOM_SEED = 42
TEST_SIZE = 0.20
IQR_K = 1.5
LONG_STAY_SCOPE = False
TARGET_COLUMN = "price_num"
GROUP_COLUMN = "host_id"
SCOPE_COLUMN = "long_stay"

# The percentiles of the log residual that become the low and high ends of the
# range the mentor is shown.
RESIDUAL_QUANTILES = (10, 90)

# How a range was derived. Recorded per model in ranges.json, because the two
# are not derived the same way and the difference matters when reading them.
METHOD_OUT_OF_FOLD = "out_of_fold_training_residuals"
METHOD_HELD_OUT_TEST = "held_out_test_residuals"

METHOD_NOTES = {
    METHOD_OUT_OF_FOLD: (
        "10-fold out-of-fold predictions on the cleaned training rows, read "
        "from the residual quantiles checkpoint. No row contributed to the "
        "model that predicted it, and the held-out test set was not spent on "
        "calibration."
    ),
    METHOD_HELD_OUT_TEST: (
        "Residuals on the held-out typical test rows, recomputed from the "
        "stored test predictions and the dataset actuals. Used because no "
        "out-of-fold residuals were recorded for this model. The rows are "
        "genuinely held out of training, but they are the same rows the "
        "reported metrics were measured on, so the range is slightly "
        "optimistic relative to the out-of-fold method."
    ),
}


class MissingInputError(RuntimeError):
    """An input this script cannot work without is absent."""


@dataclass(frozen=True)
class Fences:
    """The IQR price fences, fitted on the training rows on the log scale."""

    lower_log: float
    upper_log: float

    @property
    def lower_price(self) -> float:
        return round(float(np.expm1(self.lower_log)), 2)

    @property
    def upper_price(self) -> float:
        return round(float(np.expm1(self.upper_log)), 2)


def require(path: Path, what: str) -> Path:
    """Return ``path``, or fail with a message naming it and what it is for."""
    if not path.exists():
        raise MissingInputError(
            f"missing {what}: {relative(path)}\n"
            f"  this file is gitignored and has to be produced locally; see "
            f"the README section on preparing application assets"
        )
    return path


def relative(path: Path) -> str:
    """``path`` relative to the project root, with forward slashes."""
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def first_existing(paths: tuple[Path, ...], what: str) -> Path:
    """The first of ``paths`` that exists, or a failure listing all of them."""
    for path in paths:
        if path.exists():
            return path
    listed = "\n".join(f"  - {relative(p)}" for p in paths)
    raise MissingInputError(f"missing {what}; looked for:\n{listed}")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def model_checkpoint(feature_set: str) -> dict[str, Any]:
    name = f"{WINNING_ALGORITHM}__{feature_set}.json"
    return read_json(require(CHECKPOINTS_DIR / name, f"{feature_set} checkpoint"))


def quantile_record(residual_log: np.ndarray) -> dict[str, float]:
    """
    Turn log residuals into the multipliers the application applies.

    The models predict ``log1p(price)``, so a residual of ``q`` on that scale
    is a factor of ``exp(q)`` on the price. The range is therefore the point
    prediction multiplied by the two factors, which is what the API does.
    """
    low_q, high_q = RESIDUAL_QUANTILES
    low, high = np.percentile(residual_log, [low_q, high_q])
    return {
        "low_multiplier": float(np.exp(low)),
        "high_multiplier": float(np.exp(high)),
        f"q{low_q}_log": float(low),
        f"q{high_q}_log": float(high),
        "median_log": float(np.median(residual_log)),
        "sd_log": float(residual_log.std()),
    }


def range_from_checkpoint(path: Path) -> dict[str, Any]:
    """
    A range read straight from an out-of-fold residual quantiles checkpoint.

    The checkpoint already reports both factors, so they are read rather than
    recomputed: recomputing would mean refitting the model ten times to arrive
    at numbers the training run already recorded.
    """
    record = read_json(path)
    overall = record["overall"]
    low_q, high_q = RESIDUAL_QUANTILES
    return {
        "method": METHOD_OUT_OF_FOLD,
        "method_note": METHOD_NOTES[METHOD_OUT_OF_FOLD],
        "source": relative(path),
        "quantiles": list(RESIDUAL_QUANTILES),
        "rows": int(record["train_rows"]),
        "low_multiplier": float(overall[f"q{low_q}_factor"]),
        "high_multiplier": float(overall[f"q{high_q}_factor"]),
        f"q{low_q}_log": float(overall[f"q{low_q}_log"]),
        f"q{high_q}_log": float(overall[f"q{high_q}_log"]),
        "median_log": float(overall["median_log"]),
        "sd_log": float(overall["sd_log"]),
    }


def out_of_fold_checkpoint(feature_set: str) -> Path | None:
    """
    The out-of-fold residual checkpoint for ``feature_set``, if one exists.

    Only the core winner had one written. The lookup is by filename so that a
    later training run which adds the full equivalent is picked up without a
    code change here.
    """
    for name in (
        f"{feature_set}_residual_quantiles.json",
        f"residual_quantiles__{feature_set}.json",
    ):
        candidate = CHECKPOINTS_DIR / name
        if candidate.exists():
            return candidate
    return None


def load_scope_rows() -> pd.DataFrame:
    """The modelled rows, in the order the training script put them in."""
    master = pd.read_parquet(
        require(MASTER_DATASET, "processed master dataset"), engine="pyarrow"
    )
    in_scope = master[SCOPE_COLUMN] == LONG_STAY_SCOPE
    return master.loc[in_scope].reset_index(drop=True)


def split_and_fences(rows: pd.DataFrame) -> tuple[np.ndarray, Fences]:
    """
    Rebuild the typical test index and the price fences from the dataset.

    This repeats scripts/train_experiments.py: a seeded GroupShuffleSplit on
    the provider grouping column, then Tukey fences fitted on the training
    rows on the log scale, then the test rows that fall inside them. The
    caller asserts the length against the stored predictions, which is what
    catches a drift between the dataset and the training run.
    """
    target_log = np.log1p(rows[TARGET_COLUMN])
    splitter = GroupShuffleSplit(
        n_splits=1, test_size=TEST_SIZE, random_state=RANDOM_SEED
    )
    train_index, test_index = next(splitter.split(rows, target_log, rows[GROUP_COLUMN]))
    q1, q3 = np.percentile(target_log.iloc[train_index], [25, 75])
    iqr = q3 - q1
    fences = Fences(
        lower_log=float(q1 - IQR_K * iqr), upper_log=float(q3 + IQR_K * iqr)
    )
    inside = target_log.between(fences.lower_log, fences.upper_log)
    typical = np.array([i for i in test_index if inside.iloc[i]])
    return typical, fences


def range_from_test_residuals(feature_set: str, rows: pd.DataFrame) -> dict[str, Any]:
    """
    A range derived from the held-out typical test residuals.

    The stored predictions file holds prices, not residuals, so the actuals
    come from the dataset and the residual is recomputed on the log scale,
    using the same definition the out-of-fold checkpoint uses:
    ``log1p(actual) - log1p(predicted)``.
    """
    path = require(
        CHECKPOINTS_DIR / f"{WINNING_ALGORITHM}__{feature_set}_preds.npz",
        f"{feature_set} test predictions",
    )
    with np.load(path) as stored:
        predicted_price = np.asarray(stored["typical"], dtype=float)

    typical, _ = split_and_fences(rows)
    if len(typical) != len(predicted_price):
        raise MissingInputError(
            f"the {feature_set} predictions file holds {len(predicted_price)} "
            f"typical test rows but the dataset split rebuilds {len(typical)}; "
            f"the dataset and the training run no longer agree, so rerun "
            f"scripts/train_experiments.py"
        )

    actual_price = rows[TARGET_COLUMN].iloc[typical].to_numpy(dtype=float)
    residual_log = np.log1p(actual_price) - np.log1p(predicted_price)
    return {
        "method": METHOD_HELD_OUT_TEST,
        "method_note": METHOD_NOTES[METHOD_HELD_OUT_TEST],
        "source": relative(path),
        "quantiles": list(RESIDUAL_QUANTILES),
        "rows": int(len(typical)),
        **quantile_record(residual_log),
    }


def build_ranges(rows: pd.DataFrame | None) -> dict[str, Any]:
    """The price range for each served model, with how it was derived."""
    models: dict[str, Any] = {}
    for feature_set in SERVED_MODELS:
        checkpoint = out_of_fold_checkpoint(feature_set)
        if checkpoint is not None:
            models[feature_set] = range_from_checkpoint(checkpoint)
        else:
            if rows is None:
                raise MissingInputError(
                    f"the {feature_set} range needs either an out-of-fold "
                    f"residual checkpoint or the processed dataset, and "
                    f"neither was loaded"
                )
            models[feature_set] = range_from_test_residuals(feature_set, rows)
    return {
        "generated_by": "scripts/prepare_app_assets.py",
        "currency": CURRENCY,
        "quantiles": list(RESIDUAL_QUANTILES),
        "how_to_apply": (
            "low = round(prediction * low_multiplier), "
            "high = round(prediction * high_multiplier), both clipped to the "
            "price fences in model_info.json"
        ),
        "models": models,
    }


def build_model_info(
    column_sets: dict[str, Any], results: dict[str, Any]
) -> dict[str, Any]:
    """
    The metadata the API reads at startup: columns, metrics, fences, version.

    The input column lists come from column_sets.json rather than from the
    pipelines, so the file the API trusts is the same one the training run was
    configured from. The prediction service checks them against the loaded
    pipelines when it starts, which is where a disagreement would surface.
    """
    sets = column_sets["sets"]
    fences_record = results["fences"]

    models: dict[str, Any] = {}
    trained_dates = []
    for feature_set in SERVED_MODELS:
        checkpoint = model_checkpoint(feature_set)
        metrics = checkpoint["metrics"]["typical"]
        trained_dates.append(str(checkpoint["finished_at"]))
        columns = [str(column) for column in sets[feature_set]]
        models[feature_set] = {
            "algorithm": str(checkpoint["model"]),
            "feature_set": feature_set,
            "file": f"models/{feature_set}.joblib",
            "trained_at": str(checkpoint["finished_at"]),
            "best_params": checkpoint["best_params"],
            "input_columns": columns,
            "n_columns": len(columns),
            "metrics": {
                "rmse": round(float(metrics["rmse_aud"]), 2),
                "mae": round(float(metrics["mae_aud"]), 2),
                "r2": round(float(metrics["r2"]), 4),
                "measured_on": "the held-out typical test rows",
            },
            "cv_rmse_log_mean": round(float(checkpoint["cv_rmse_log_mean"]), 6),
        }

    trained_at = max(trained_dates)
    version = f"{WINNING_ALGORITHM}-{trained_at[:10].replace('-', '')}"
    return {
        "generated_by": "scripts/prepare_app_assets.py",
        "model_version": version,
        "trained_at": trained_at,
        "currency": CURRENCY,
        "target": "the listed session price, learned on the log scale",
        "price_fences": {
            "lower": round(float(fences_record["lower_aud"]), 2),
            "upper": round(float(fences_record["upper_aud"]), 2),
            "basis": (
                f"Tukey fences with k={fences_record['k']} on "
                f"{fences_record['scale']}, fitted on {fences_record['fitted_on']}"
            ),
        },
        "cross_validation": results["cv"],
        "models": models,
        "notes": {
            "source_dataset": (
                "Trained on a documented proxy dataset. The dataset and the "
                "proxy argument are described in the project report."
            ),
            "advisory": (
                "The price is advice. The mentor may accept, change or reject "
                "it; the system never sets a price."
            ),
        },
    }


def copy_models() -> list[tuple[str, int]]:
    """Copy the two served pipelines into app_assets/models/."""
    copied = []
    for feature_set in SERVED_MODELS:
        source = require(
            EXPERIMENTS_DIR / f"{WINNING_ALGORITHM}__{feature_set}.joblib",
            f"{feature_set} pipeline",
        )
        destination = MODELS_OUT / f"{feature_set}.joblib"
        shutil.copyfile(source, destination)
        copied.append((relative(destination), destination.stat().st_size))
    return copied


def write_json(path: Path, payload: dict[str, Any]) -> int:
    text = json.dumps(payload, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def main() -> int:
    try:
        column_sets = read_json(require(COLUMN_SETS, "column sets report"))
        results_path = first_existing(MODEL_RESULTS_CANDIDATES, "model results report")
        results = read_json(results_path)
        for feature_set in SERVED_MODELS:
            require(
                EXPERIMENTS_DIR / f"{WINNING_ALGORITHM}__{feature_set}.joblib",
                f"{feature_set} pipeline",
            )
            model_checkpoint(feature_set)

        # The dataset is only loaded when a range has to be derived from it.
        # It is the largest input and the one most likely to be absent.
        needs_dataset = any(
            out_of_fold_checkpoint(feature_set) is None for feature_set in SERVED_MODELS
        )
        rows = load_scope_rows() if needs_dataset else None

        ranges = build_ranges(rows)
        model_info = build_model_info(column_sets, results)

        MODELS_OUT.mkdir(parents=True, exist_ok=True)
        copied = copy_models()
        ranges_bytes = write_json(RANGES_OUT, ranges)
        info_bytes = write_json(MODEL_INFO_OUT, model_info)
    except MissingInputError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    except (KeyError, ValueError) as error:
        print(
            f"FAILED: an input file is present but not in the expected shape: "
            f"{error!r}",
            file=sys.stderr,
        )
        return 1

    print(f"Wrote {relative(APP_ASSETS)}/")
    for path, size in copied:
        print(f"  {path}  ({size:,} bytes)")
    print(f"  {relative(RANGES_OUT)}  ({ranges_bytes:,} bytes)")
    print(f"  {relative(MODEL_INFO_OUT)}  ({info_bytes:,} bytes)")
    print()
    if COMPARABLES.exists():
        print(
            f"Comparable mentors: {relative(COMPARABLES)} "
            f"({COMPARABLES.stat().st_size:,} bytes). It was built against an "
            f"earlier run of this script, so rebuild it to match this one:"
        )
    else:
        print(
            f"Comparable mentors: {relative(COMPARABLES)} is not there yet, so "
            f"the API cannot say what mentors like a mentor charge. Build it "
            f"with:"
        )
    print("  python scripts/build_comparables.py")
    print()
    print(f"Model results read from {relative(results_path)}")
    print(
        f"Model version {model_info['model_version']}, "
        f"trained {model_info['trained_at']}"
    )
    fences = model_info["price_fences"]
    print(f"Price fences {fences['lower']:,.2f} to {fences['upper']:,.2f} {CURRENCY}")
    for feature_set in SERVED_MODELS:
        model = model_info["models"][feature_set]
        band = ranges["models"][feature_set]
        print(
            f"  {feature_set:5s} {model['n_columns']:2d} columns  "
            f"RMSE {model['metrics']['rmse']:,.2f}  "
            f"MAE {model['metrics']['mae']:,.2f}  "
            f"R2 {model['metrics']['r2']:.4f}  "
            f"range x{band['low_multiplier']:.4f} to "
            f"x{band['high_multiplier']:.4f}  "
            f"({band['method']}, {band['rows']:,} rows)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
