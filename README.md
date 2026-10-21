# AI-Driven Demand-Responsive Pricing Recommendation System

Final year project (ISP II), Strathmore University.
Use Case 6 of the Career Mentor platform, developed with Webmasters Kenya.

Predicts a market-consistent, demand-informed session price for mentors on a
digital mentorship platform, presented as an advisory recommendation that the
mentor may accept, modify, or reject.

---

## Setup

Requires Python 3.11 or later.

```bash
make setup
source .venv/bin/activate
```

This creates a virtual environment, installs pinned dependencies, and
registers pre-commit hooks.

## Common tasks

```bash
make test      # run test suite with coverage
make lint      # check formatting and linting
make format    # auto-fix formatting
make api       # run the FastAPI dev server on :8000
make clean     # clear caches
```

---

## Project structure

The `src/` layout mirrors the component diagram in Chapter 4 of the proposal,
so each directory corresponds to a documented system component.

```
src/
├── data/            Data acquisition and loading
├── preprocessing/   Data Preprocessing component
├── models/          ML Model component
├── api/             FastAPI Application component
└── config.py        Paths, seeds, experiment parameters, feature sets
```

Other directories:

- `notebooks/` — exploratory analysis only, not production code
- `tests/` — test suite
- `data/raw/`, `data/processed/` — datasets (git-ignored)
- `models_store/` — serialised model artefacts (git-ignored)

---

## Experimental design

Three candidate models are trained and compared: Linear Regression, Random
Forest, and XGBoost. All use 10-fold cross-validation with GridSearchCV for
hyperparameter tuning, applied consistently across models so that performance
differences reflect model capability rather than evaluation methodology.

Evaluation uses RMSE, MAE, and R² on a held-out test set withheld entirely
from training and tuning.

### Hypothesis

Incorporating demand-responsive input features (profile views, booking
requests, skill demand trends) improves predictive accuracy relative to a
baseline trained only on mentor profile and performance variables.

Tested by training each model on both feature sets defined in `config.py`
(`baseline_feature_set()` and `full_feature_set()`) and comparing metrics.

---

## Data

Primary source: Career Mentor platform data via Webmasters Kenya.

Contingency: where platform data is insufficient in volume, the methodology
is validated against Inside Airbnb data as a structural proxy. The proxy
validates that the pipeline and models learn meaningful pricing patterns from
real marketplace data; it does not claim equivalence between accommodation and
mentorship pricing.

Raw data is never committed to version control.

---

## Reproducibility

- Dependencies pinned to exact versions
- Random seed fixed in `config.py`
- Train/test split ratio and CV fold count defined in one place
- CI runs linting and tests on every push
