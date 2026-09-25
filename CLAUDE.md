# Project Context

Final year project (ISP II), Strathmore University. Use Case 6 of the Career
Mentor platform, developed with Webmasters Kenya.

## What this system does

Predicts a market-consistent, demand-informed session price for mentors on a
digital mentorship platform. The price is advisory — the mentor may accept,
modify, or reject it. The system never sets a price automatically.

## Locked design decisions

- **Three candidate models**: Linear Regression (baseline), Random Forest, XGBoost
- **10-fold cross-validation**, applied consistently across all three models.
  Justified by Raschka (2016). Related works used inconsistent fold counts;
  consistency here is a deliberate methodological contribution.
- **GridSearchCV** for hyperparameter tuning, inside the CV loop, never
  touching the test set
- **80/20 train/test split**, test set withheld from training and tuning
- **Metrics**: RMSE (primary selection criterion), MAE, R²
- **Target variable**: current listed price. NOT a theoretically optimal or
  revenue-maximising price.

## Hypothesis

Incorporating demand-responsive features (profile views, booking requests,
skill demand trends) improves predictive accuracy relative to a baseline
trained only on profile and performance variables.

Tested by an ablation study: train each model twice, once on
`baseline_feature_set()` and once on `full_feature_set()` from `src/config.py`,
then compare metrics.

## Input variable categories

1. Mentor profile — experience, certifications, education, specialisation
2. Mentor performance — ratings, reviews, completion rate, repeat booking rate
3. Demand indicators — profile views, booking requests, skill demand trends
4. Market variables — average price for similar mentors, category averages

## Data

Primary: Career Mentor platform via Webmasters Kenya. Not yet received.

Contingency: Inside Airbnb as a structural proxy. The claim is narrow — the
_problem structure_ matches (provider attributes + performance + demand →
price). It is NOT a claim that accommodation and mentorship pricing behave
alike. Column mapping lives in `src/data/airbnb_mapping.py`.

## Code structure

`src/` mirrors the component diagram in Chapter 4:

- `data/` — acquisition and loading
- `preprocessing/` — Data Preprocessing component
- `models/` — ML Model component
- `api/` — FastAPI Application component
- `config.py` — paths, seeds, experiment parameters, feature set definitions

## Conventions

- Black + Ruff, 88 char line length, enforced by pre-commit
- Pinned dependency versions for reproducibility
- Raw data and model artefacts are gitignored, never committed
- Tests for any module with logic
