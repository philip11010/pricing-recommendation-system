# AI-Driven Demand-Responsive Pricing Recommendation System

Final year project (ISP II), Strathmore University.
Use Case 6 of the Career Mentor platform, developed with Webmasters Kenya.

Predicts a market-consistent, demand-informed session price for mentors on a
digital mentorship platform, presented as an advisory recommendation that the
mentor may accept, modify, or reject. The system never sets a price.

All prices are in AUD.

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
make assets    # build app_assets/ from a local training run
make migrate   # apply database migrations
make api       # run the pricing API on :8000
make test      # run test suite with coverage
make lint      # check formatting and linting
make format    # auto-fix formatting
make clean     # clear caches
```

---

## Running the pricing API

Three steps, in order. The first two are only needed once.

### 1. Prepare the application assets

The API loads two trained models at startup. They are build outputs of a
local training run rather than source, so they are not in the repository.
Produce them with:

```bash
python scripts/prepare_app_assets.py
```

This writes `app_assets/` (git-ignored):

- `app_assets/models/core.joblib` and `full.joblib` — the two served pipelines
- `app_assets/ranges.json` — the multipliers that turn a point prediction into
  the range a mentor is shown, with the method used for each model recorded
  alongside it
- `app_assets/model_info.json` — model version, training date, RMSE, MAE and R²
  on the held-out test rows, the price fences, and the exact input columns each
  model expects

The script prints what it wrote and fails with the name of the missing file if
an input is absent. Its inputs are the trained pipelines in `models_store/`,
the reports in `reports/`, and the processed dataset, all of which are
git-ignored and produced locally by `scripts/train_experiments.py`.

Delete `app_assets/` and run the script again to rebuild.

### 2. Create the database schema

`DATABASE_URL` is read from the environment and falls back to a local SQLite
file. PostgreSQL is the deployment target, and the schema is versioned with
Alembic rather than created from the models at boot:

```bash
alembic upgrade head
```

The earlier dashboard prototype owned tables called `recommendations` and
`decisions` with a different shape, and the pricing API now uses those names
for its own. The migration creates the prototype's two under
`legacy_recommendations` and `legacy_decisions`, so a database that already
holds them under the old names cannot be upgraded in place. A local `app.db`
from the prototype holds nothing but demo rows: delete it, or point
`DATABASE_URL` at a fresh database, and the migration runs.

### 3. Start the API

```bash
uvicorn src.mentor.app:app --reload --port 8000
```

Interactive documentation is at `/docs`, and the OpenAPI schema at
`/openapi.json`.

A server without prepared models still starts. `/health` reports
`models_loaded: false`, the options endpoint still answers so the registration
form can render, and any endpoint that needs a price returns 503 with an
explanation rather than failing.

### Endpoints

| Method | Path                                   | Purpose                                               |
| ------ | -------------------------------------- | ----------------------------------------------------- |
| GET    | `/health`                              | Liveness, and whether a price can be produced         |
| GET    | `/meta/options`                        | Every option list the registration form needs         |
| POST   | `/mentors`                             | Register a mentor and first service, and price it     |
| GET    | `/mentors/{id}`                        | A mentor's own record                                 |
| POST   | `/services/{service_id}/recommendations` | Price one of the mentor's services again            |
| GET    | `/recommendations/{id}`                | Read back one advisory price                          |

Every advisory price comes back as two sets of three figures. The session
total is `recommended_price` with `price_low` and `price_high` around it: one
booking at one price, however many mentees are in it. Alongside them,
`price_per_mentee`, `price_per_mentee_low` and `price_per_mentee_high` are the
same three divided by the number of mentees who can join and rounded to whole
AUD, which is what one mentee pays. For a session of one the two sets are
identical. The per-mentee figures are derived rather than stored, and are
divided out of the stored session prices using the group size recorded in the
price's own input snapshot, so a mentor who later changes the number of seats
does not change what an old price says each mentee was paying.

The registration form asks how many mentees can join one session, from 1 to
8. Anything from 9 upwards is refused with the same message as any other
out-of-range answer, because 8 is where the training data runs out: it is the
95th percentile of group size there, with plenty of rows behind it, and above
it the per-mentee price stops falling as the group grows, which is the
opposite of what a bigger group means. The maximum is the constant
`MAX_MENTEES_MAX` in `src/mentor/mapping.py`, and the request schema, the
options endpoint and the database check constraint all read it from there.

The form does not ask for a session format: what a session is called follows
from its size, and `/meta/options` publishes that rule as
`session_label_rule` rather than a list to choose from. One mentee is
`one_to_one`, two or more is `group`, and the label is stored on the service
and returned as `session_label`.

How long a mentor has been mentoring is asked at registration and shown on
their profile. It does not affect the price: see the note below.

Identity is a placeholder. A mentor-scoped request carries the mentor's id in
an `X-Mentor-Id` header, and there is no authentication yet. Every query is
filtered by that id, so a mentor can only read their own records; a request
for another mentor's row returns 404 rather than 403, which would confirm the
row exists. Replacing `get_current_mentor_id` in `src/mentor/dependencies.py`
with a real token check is the whole of the work to add authentication.

### Two models, one API

A newly registered mentor is priced from the eight core inputs: six that the
registration form collects, and two that `src/mentor/mapping.py` holds at a
constant and explains there. Those prices carry `low_confidence: true`: a
form alone is a weaker basis than a record of completed sessions. Once a
mentor has a track record, the same endpoints price them with a second model
that takes 28 further inputs and is measurably more accurate, and the flag
goes away.

### Two inputs that are decided rather than asked

Both are documented at the top of `src/mentor/mapping.py`, which is the only
place either one is set.

The **session format** column is held at a single value for every mentor. It
has one value the training data supports well and one it barely supports, and
prices built on the thin one did not rise sensibly with the size of the
group: a group of two came out below one-to-one work, and a group of eight
below a group of four. The group size is asked on its own and is what
distinguishes one session from another, so the format is held at the
well-supported value and nothing a mentor answers can move it. Within the
supported range of 1 to 8 mentees, the session total then rises with every
seat added and the per-mentee price falls with every seat added.

A **new mentor's tenure** is the constant `NEW_MENTOR_TENURE_YEARS`, because
a mentor who has just registered has no time on the platform whatever their
career length. The experience band the form asks for is profile text: it is
stored, returned on the mentor's record and never given to the model. In the
training data a longer tenure goes with a lower price, which describes that
dataset rather than anything true about mentoring, and routing the answer
into that column would have advised the most experienced mentors to charge
the least. A mentor who does have a record will be priced on the tenure from
that record, which is a later step.

---

## Project structure

The `src/` layout mirrors the component diagram in Chapter 4 of the proposal,
so each directory corresponds to a documented system component.

```
src/
├── data/            Data acquisition and loading
├── preprocessing/   Data Preprocessing component
├── models/          ML Model component
├── mentor/          Mentor-facing pricing API
│   ├── mapping.py   The only translation between mentor terms and model inputs
│   ├── prediction.py  Loads both models, produces a price and its range
│   ├── schemas.py   Request and response shapes
│   ├── dependencies.py  The identity hook that will become authentication
│   └── app.py       The FastAPI application
├── api/             Earlier dashboard prototype
├── db/              SQLAlchemy models
└── config.py        Paths, seeds, experiment parameters, feature sets
```

Other directories:

- `migrations/` — Alembic revisions
- `scripts/` — training runs and asset preparation
- `notebooks/` — exploratory analysis only, not production code
- `tests/` — test suite
- `data/raw/`, `data/processed/` — datasets (git-ignored)
- `models_store/` — serialised model artefacts (git-ignored)
- `app_assets/` — what the API loads at startup (git-ignored)
- `reports/` — training run outputs (git-ignored)

`src/mentor/mapping.py` is worth knowing about before changing anything else:
it is the single place where a mentor's answers become model inputs, and the
single source of the option lists the frontend renders. Nothing outside it
refers to a model column by name.

---

## Testing

```bash
pytest
```

Tests that need the prepared models are marked `app_assets` and skip
themselves with an explanatory message when `app_assets/` is absent, so a
clone without a local training run still runs green:

```bash
pytest -m "not app_assets"    # skip them explicitly
pytest -m app_assets          # run only those
```

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

Tested by training each model on both feature sets and comparing metrics. The
two served models are the result: the eight-input model and the 36-input model
are the two arms of that comparison, and the larger one wins on all three
metrics.

---

## Data

Primary source: Career Mentor platform data via Webmasters Kenya.

Where platform data is insufficient in volume, the methodology is validated
against a documented proxy dataset, described in the project report. The proxy
validates that the pipeline and models learn meaningful pricing patterns from
real marketplace data; it does not claim equivalence between the two markets.

Raw data, trained models and prepared assets are never committed to version
control.

---

## Reproducibility

- Dependencies pinned to exact versions
- Random seed fixed in `config.py`
- Train/test split ratio and CV fold count defined in one place
- The served models' version, training date, metrics and input columns are
  recorded in `app_assets/model_info.json` and reported by `/health`
- Database schema versioned with Alembic
- CI runs linting and tests on every push
