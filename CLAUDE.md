## Hard rules

- Never run git add, git commit, git push, git reset, git rebase, git stash or any gh command.
- Read-only git is allowed: git status, git diff, git log.
- Never write Co-Authored-By or Claude-Session lines anywhere.
- Never edit or print .env contents. Never commit data or model files.
- The user does all staging, committing and pushing.
- No em dashes in any text you write.
- Nothing user-facing may mention the source dataset: no listings, hosts, nights or Airbnb.
- Mentor language only in anything a mentor or the frontend can see.
- Internal model column names live only in the mapping layer and the model code.
- If shell commands crash, edit files only and ask the user to run them.

# Project Context

Final year project (ISP II), Strathmore University. Use Case 6 of the Career
Mentor platform, developed with Webmasters Kenya.

## What this system does

Predicts a market-consistent, demand-informed session price for mentors on a
digital mentorship platform. The price is advisory: the mentor may accept,
modify, or reject it. The system never sets a price automatically.

## Locked design decisions

- **Three candidate models**: Ridge (the regularised linear baseline, L2),
  Random Forest, XGBoost.
- **10-fold cross-validation**, the same folds for all three models.
  KFold(n_splits=10, shuffle=True, random_state=42). Justified by Raschka
  (2016). Related works used inconsistent fold counts; consistency here is a
  deliberate methodological contribution.
- **GridSearchCV** for hyperparameter tuning, inside the CV loop, never
  touching the test set.
- **Scoring**: neg_root_mean_squared_error, with error_score="raise". A failed
  fold stops the run loudly instead of being averaged in as a silent nan.
- **Target**: log1p of the price. Metrics are reported in AUD, after expm1.
- **Train/test split**: grouped by host, GroupShuffleSplit with seed 42 and 20
  percent held out, so no host appears in both sets. Two services from one
  provider are not independent, and a plain random split would leak that
  provider's pricing habits across the boundary.
- **Price fences**: 59.51 to 1,913.07 AUD. Tukey IQR fences with k=1.5 on
  log1p(price), fitted on the training rows only.
- **Metrics**: RMSE (primary selection criterion), MAE, R2.
- **The rule that decides every column**: a column is allowed in a model only
  if the application can supply it for a mentor.
- **Target variable**: the current listed price. NOT a theoretically optimal
  or revenue-maximising price.

## Feature sets

- **core** (8 columns): what a mentor supplies at registration, or what the
  system derives from it. Defined for a brand new mentor, so a core model can
  quote a price to someone with no history.
- **core plus space** (11 columns): core plus three physical-property
  attributes. Ablation only, to measure how much achievable accuracy comes
  from property size alone. Not available to the application and never in a
  deployed model.
- **full** (36 columns): core plus 28 performance and demand columns. For
  mentors who have a history.

The machine-readable lists are in reports/column_sets.json, and every column
is documented in docs/data_dictionary.md.

## Deployed models

- **XGBoost core** prices a new mentor, from the registration form alone.
  Those prices carry a low-confidence note, because a form is a weaker basis
  than a record of completed sessions.
- **XGBoost full** prices a mentor who has a history.
- The application shows a price range around each point prediction, derived
  from the models' residual quantiles.
- The price is advisory and market-consistent, not profit-maximising.

## Hypothesis

Mentors with a performance and demand history can be priced more accurately
than from their profile alone.

Tested as core versus full: the same algorithm trained twice, once on each
feature set, compared on the held-out typical test rows.

**Result: supported.** R2 rises from 0.544 to 0.625, log RMSE is 10.7 percent
lower, and MAE falls from 120 to 107 AUD.

## Data

Career Mentor platform data has not been received.

The system is trained on a documented proxy dataset (Inside Airbnb Sydney).
It is a structural proxy only: the problem structure matches, which is
provider attributes plus performance plus demand predicting price. It is NOT a
claim that accommodation and mentorship pricing behave alike. The report says
all of this plainly. The application never mentions it.

## Mapping decisions

src/mentor/mapping.py is the only place a mentor's answers become model
inputs. Each decision below is documented there.

- The room type column is held at one value for every mentor, the one the
  training data supports well.
- Group size alone carries the capacity effect, capped at 8, which is the 95th
  percentile in the training data. Above it the prices stop behaving.
- A new mentor's tenure is fixed at 0.5 years. A mentor with a history is
  priced on the tenure in their own record.
- Years of experience, education and credentials are profile-only. They are
  stored and shown, and never given to a model.
- Each field maps to one neighbourhood, chosen by price level. This is a
  documented assumption, not a claim that a field is a place.

## Code structure

`src/` mirrors the component diagram in Chapter 4:

- `data/`: acquisition and loading
- `preprocessing/`: Data Preprocessing component
- `models/`: ML Model component
- `mentor/`: the mentor-facing pricing API. `mapping.py` (the vocabulary
  boundary), `prediction.py`, `schemas.py`, `dependencies.py`, `app.py`
- `db/`: SQLAlchemy models
- `api/`: the earlier dashboard prototype
- `config.py`: paths, seeds, experiment parameters

Outside `src/`:

- `scripts/`: `train_experiments.py`, `prepare_app_assets.py`,
  `seed_demo_mentors.py` and others
- `migrations/`: Alembic revisions. Add new ones; never edit an existing one
- `app_assets/`: what the API loads at startup. Git-ignored build output
- `tests/`: the test suite

## Conventions

- Black + Ruff, 88 char line length, enforced by pre-commit
- Pinned dependency versions for reproducibility
- AUD everywhere. No currency conversion anywhere in the project
- No authentication yet. Every mentor-scoped query goes through one identity
  function, which reads the X-Mentor-Id header, and filters by that mentor.
  Another mentor's record returns 404, never 403
- Git-ignored and never committed: raw and processed data, `reports/`,
  `models_store/`, `app_assets/`, `app.db`
- Tests for any module with logic
