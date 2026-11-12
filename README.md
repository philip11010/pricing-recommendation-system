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

Five steps, in order. The first three build what the API loads, the fourth
starts it, and the fifth is optional.

The three build scripts go in this order, and the order matters:

```bash
python scripts/prepare_app_assets.py    # 1. the models and their metadata
python scripts/build_comparables.py     # 2. the mentors a price is compared with
python scripts/seed_demo_mentors.py     # 3. ten mentors with a track record
```

Step 1 comes first because both of the others read the price fences out of the
metadata it writes. Steps 2 and 3 are independent of each other, but they share
one thing: the opaque key defined in `src/data/population.py`, which is a row's
position in the processed dataset. A seeded mentor is excluded from their own
comparison by that key, so the two have to be built from the same dataset. If
you rebuild one after changing the dataset, rebuild the other.

### 1. Prepare the models

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

### 2. Build the comparable mentors

A price with nothing to compare it against is a number a mentor has no way to
judge. This step prepares the comparison:

```bash
python scripts/build_comparables.py
```

It writes `app_assets/comparables.parquet` (git-ignored) with one row per
mentor in the modelled population and exactly eight columns: the opaque key,
the field, the group size, the session price, the price per mentee, the overall
rating, the booked share over the last year, and the review count. It prints
the row count and price spread per field.

Nothing that identifies a source record goes into the file. Seven of the eight
columns are quantities a mentor would recognise about themselves, and the
eighth is the key, which is a position in the processed dataset and says
nothing without it. The dataset is git-ignored and never published.

The population is the one the models were fitted within, read through the same
module the seed script uses so the two agree about both the filters and the
key. One filter differs: a row needs five reviews here rather than the ten the
seed script asks for, because a row shown as one of two hundred comparable
mentors needs less of a record than a row turned into a mentor with a track
record of their own.

The API starts without this file. `/health` reports
`comparables_loaded: false`, everything else works, and the two endpoints that
need it say what to run.

### 3. Create the database schema

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

### 4. Start the API

```bash
uvicorn src.mentor.app:app --reload --port 8000
```

Interactive documentation is at `/docs`, and the OpenAPI schema at
`/openapi.json`.

A server without prepared models still starts. `/health` reports
`models_loaded: false`, the options endpoint still answers so the registration
form can render, and any endpoint that needs a price returns 503 with an
explanation rather than failing.

### 5. Seed the demonstration mentors (optional)

On a fresh database every mentor is a new mentor, because nobody has taken a
session yet. The existing-mentor half of the system therefore has nobody on it
and cannot be shown. This step supplies ten established mentors:

```bash
python scripts/seed_demo_mentors.py                  # create the ten
python scripts/seed_demo_mentors.py --no-activity    # skip the chart data
python scripts/seed_demo_mentors.py --reset          # remove them again
```

It prints a table of what it wrote: the mentor, their field, their group size,
what they charge, the advised price and range, what they decided about it,
whether they are verified, and whether what they charge is below, within or
above that range. It then prints their addresses and the password they all
sign in with.

Each of them gets the whole flow rather than just a profile: a service, a
track record, an advisory price from the full model and a decision about that
price, so the dashboard, the history and the decision counts have something in
them on a fresh database. The answers follow from what each mentor charges: a
mentor charging roughly what the model advises has accepted it, one charging
clearly more or less has rejected it and said what they charge instead, and
the two in between have modified it.

Each seeded mentor carries a `source_key`, the key described above, so they are
left out of their own comparison. A mentor compared against themselves would be
told their price is exactly typical, by a comparison they are a data point in.
If you seeded mentors before the key was defined in
`src/data/population.py`, reset and reseed so the keys match the comparables
file:

```bash
python scripts/seed_demo_mentors.py --reset
python scripts/seed_demo_mentors.py
```

The ten are chosen from the population the models were fitted on, so each
one's track record is internally consistent in the way a real one is: rating,
review counts, booked shares and tenure all describe the same provider. They
are chosen to be worth looking at rather than at random:

- **at least five different fields**, so the field list and the directory
  filters are visibly in use,
- **four one-to-one mentors and six running groups**, with six different group
  sizes between two and eight. A session for one is not a smaller group: it is
  labelled `one_to_one` rather than `group`, and its per-mentee figures equal
  its session figures rather than being a division of them,
- **one mentor charging clearly above their advised range, one within it and
  one below it**, which is what makes the comparison on a recommendation
  demonstrable,
- **nine verified and one not**, so the checkmark on the directory is visibly
  something a mentor can be without rather than a decoration every card
  carries. The tenth is priced as an unverified mentor, because verification is
  one of the eight inputs behind a price.

The script says in its output if the population cannot supply one of those,
rather than quietly seeding something smaller.

Their month-by-month activity is a separate build, because it reads the raw
files rather than the processed dataset. The seed runs it at the end unless
`--no-activity` is passed, and it can be run on its own:

```bash
python scripts/build_demo_activity.py
python scripts/build_demo_activity.py --months 6
```

It writes one row per mentor per month for the last twelve complete months. It
reports what it could not build rather than filling it in: in the export this
project was built on, reviews per month are real measurements, while the
booked share and the price per month are not available, because the
availability file is a forward-looking snapshot of the coming year and has no
price column. Those entries are left empty, and the endpoint that serves them
returns null rather than zero. Ratings over time do not exist in the sources at
all and are not shown.

The people are fictional, and they are accounts: each one has a password, so
whoever is running the demonstration signs in as one of them. See
"Authentication and demo accounts" below. The names come from a fixed pool and
are a first name and an initial, every address is at `example.com`, and the
profile text is a template per field. Nothing identifying is copied from the dataset: the
only link back to a source row is `source_key`, a position in the filtered
population, which exists so that running the script twice recognises the
mentors it already wrote. Running it again creates nothing; `--reset` removes
the seeded mentors and everything belonging to them and leaves mentors who
registered alone.

It needs both the prepared models and the processed dataset, and fails with
the name of whichever is missing. The activity build also needs the raw
reviews and availability files. All of them are git-ignored.

## Authentication and demo accounts

A mentor registers with an email address and a password and is given a signed
access token. Every request about their own records carries it as
`Authorization: Bearer <token>`. There are no cookies and no session table: the
token carries the mentor's id and an expiry, signed, and lasts seven days.

**Signing out is the client discarding the token.** There is no logout
endpoint, because the server holds no session to end. A token that has already
been issued stays valid until it expires, which is why it expires in a week
rather than a year.

Passwords are hashed with Argon2id, between 8 and 128 characters. A wrong
password and an address nobody has registered give the same answer and take
about the same time to give it, so the sign-in form cannot be used to find out
who has an account.

| Method | Path             | Purpose                                     |
| ------ | ---------------- | ------------------------------------------- |
| POST   | `/auth/register` | Create the account, profile and first service |
| POST   | `/auth/login`    | Exchange an address and password for a token |
| GET    | `/auth/me`       | Who the current token belongs to             |

Configuration, all read from the environment or `.env`:

- `SECRET_KEY` signs the tokens. **If `ENVIRONMENT` is `production` and it is
  missing or shorter than 32 characters, the server refuses to start**, because
  the alternative is a server that issues forgeable tokens while answering
  `/health` perfectly happily. In development a key is generated at startup
  and one warning line says so; the tokens issued before a restart stop
  working after it.
- `ENVIRONMENT` is `development` unless it is set to `production`.
- `DEMO_PASSWORD` is what the seeded demonstration accounts sign in with,
  defaulting to `Pathwise-demo-1`. The seed prints the addresses and the
  password at the end of a run: they are fictional accounts on `example.com`,
  which can never belong to anyone, created to be signed in to.

**New accounts are not verified.** Verification is what the platform says about
a mentor after a person has checked who they are, so nothing a mentor sends can
set it, including at registration. One script does:

```bash
python scripts/verify_mentor.py mentor@example.com
python scripts/verify_mentor.py mentor@example.com --revoke
```

It sets the flag on the account and on each of that mentor's services, which
is the same claim in the form the model reads, so a mentor shown with a
checkmark is also priced as one. Prices already given are left alone: the
mentor answered those.

### Endpoints

| Method | Path                                     | Token | Purpose                                            |
| ------ | ---------------------------------------- | ----- | -------------------------------------------------- |
| GET    | `/health`                                | no    | Liveness, and what has been prepared               |
| GET    | `/meta/options`                          | no    | Every option list the registration form needs      |
| POST   | `/auth/register`                         | no    | Register a mentor and first service, and price it   |
| POST   | `/auth/login`                            | no    | Exchange an address and password for a token        |
| GET    | `/auth/me`                               | yes   | Who the current token belongs to                   |
| GET    | `/mentors`                               | no    | The public directory of mentors                    |
| GET    | `/mentors/{id}/public`                   | no    | One mentor's public profile                        |
| POST   | `/preview`                               | no    | Price a part-filled form, storing nothing          |
| GET    | `/mentors/demo`                          | no    | The mentors seeded for the demonstration           |
| PATCH  | `/mentors/me`                            | yes   | Edit the mentor's own name and profile fields      |
| GET    | `/mentors/{id}`                          | yes   | A mentor's own record                              |
| GET    | `/mentors/{id}/dashboard`                | yes   | Advice, decisions and where the mentor sits        |
| GET    | `/mentors/{id}/activity`                 | yes   | The mentor's own activity, month by month          |
| POST   | `/mentors/{id}/services`                 | yes   | Add another service, and price it                  |
| GET    | `/services/{service_id}`                 | yes   | One of the mentor's own services                   |
| POST   | `/services/{service_id}/recommendations` | yes   | Price one of the mentor's services again           |
| GET    | `/services/{service_id}/comparables`     | yes   | What mentors like this one charge                  |
| GET    | `/services/{service_id}/history`         | yes   | Every price this service has had, and its answer   |
| GET    | `/recommendations/{id}`                  | yes   | Read back one advisory price, and its answer       |
| POST   | `/recommendations/{id}/decision`         | yes   | Answer one advisory price                           |

Every endpoint marked "yes" is scoped to the mentor the token belongs to. A
request for somebody else's record returns 404 rather than 403, because 403
would confirm that the other record exists.

### What anybody may read

Four endpoints answer without a token, and what they carry was chosen field by
field rather than trimmed from a record.

`GET /mentors` is the public directory: cards of `id`, display name, field
label, the name of the mentor's main service, what they charge, the group
size, the session label, whether they are verified, and how many reviews they
have. Nothing else: no address, no password hash, no demonstration flag and
none of the figures a model reads. It takes `field`, `group` (`one_to_one` or
`group`), `limit` (24 by default, 100 at most) and `offset`, lists the newest
mentor first, and reports the whole count beside the page. A mentor who
registered a minute ago is on it on the same terms as a seeded one, with their
verification shown as what it is, and their price null until they settle on
one: a mentor who has only been advised a price has not set it.

`GET /mentors/{id}/public` is the same card plus the skills they offer and the
three optional profile fields, each null where the mentor left it blank.

`POST /preview` prices a part-filled registration form: `field`, `max_mentees`
and `skills`, the same validation as registration, and the same core model, so
the number a mentor watches while they type is the number they are given when
they submit. It writes nothing at all, and it is limited to 60 calls a minute
per address, because it is the one endpoint with no account behind it and
every call scores a model.

`/mentors/demo` is the list someone picks a demonstration mentor from, so
requiring a token would be circular. It carries nothing that is not already on
a mentor's public profile, and it answers on a server with no models because
it names no price.

`GET /mentors/{id}` returns the mentor's services with what each one currently
charges, and, for a mentor who has a track record, a summary of it in mentor
language: whether they hold the top-rated badge, their review counts and
rating, their booked shares, how long since their last review and how long
they have been on the platform. `complete` on that summary says whether every
figure the more accurate model needs has a value, which is what decides how
they are priced.

`POST /mentors/{id}/services` asks the same questions as registration, with
the same validation and the same mapping. Adding a service moves the service
count the model is given, so the price it returns is not necessarily the price
the same answers would have had as a first service: see
`mapping.effective_services`.

`GET /mentors/{id}/activity` is the mentor's own activity over time, as four
parallel arrays of one entry per month plus one plain sentence about the
period. A null in `booked_share_by_month` or `price_by_month` means the
platform has no such measurement for that month, which is not the same as a
zero: a zero would say the mentor was booked for none of the time they
offered, or charged nothing. `reviews_by_month` is never null, because a month
inside the period a mentor has been on the platform with no reviews in it had
none. A mentor with nothing recorded yet, which is every mentor who has just
registered, gets `has_history: false` and four empty lists rather than an
error.

`PATCH /mentors/me` edits the mentor's name and their three optional profile
fields, and nothing else: the address they sign in with, their verification
and everything about a service are each settled somewhere with a reason of
their own. A field that was not sent is left alone and a field sent as null is
cleared. None of these fields reaches a model, so a price never moves because
of an edit here.

### Comparable mentors

`GET /services/{service_id}/comparables` answers "and what do mentors like me
charge". It takes `sort` (`price` or `rating`), `order` (`asc` or `desc`),
`limit` and `offset`, and returns three things:

- `summary`: the count, the median price, the quartiles either side of it, the
  median price per mentee, and how the match was made. Quantiles rather than a
  mean, because prices in any field have a long upper tail and a mean sits
  above most of the mentors it claims to describe.
- `histogram`: twelve bins over the session price, as edges and counts, so the
  frontend decides how the chart looks and the API decides only what it says.
- `items`: the matched mentors themselves, sorted as asked.

The match widens in steps and stops at the first level with at least
`MIN_MATCHES` mentors, which is 10:

| `match_level` | Who it covers                                         |
| ------------- | ----------------------------------------------------- |
| 0             | The mentor's own field, within one seat of their size |
| 1             | Their field, any group size                            |
| 2             | Any field, within one seat of their size              |

`match_description` says the same thing in words, for example "Technology and
software mentors with 3 to 5 mentees per session". `widened` is true when even
level 2 found fewer than 10 mentors, so the figures describe fewer mentors than
the system considers enough to generalise from. It is reported rather than
hidden: a median over six mentors is still the best answer available, and the
mentor is entitled to know that is what they are reading.

The same endpoint serves a mentor who registered a minute ago and one who has
been taking sessions for a year. The comparison is drawn from the field and the
group size, which both of them have.

A mentor seeded by `scripts/seed_demo_mentors.py` is left out of their own
comparison. `summary` and `histogram` always describe the whole match, so
paging through `items` never changes what the mentor is told about the market.

`items` carry no id of any kind, and neither does the order they arrive in: the
sort is settled by price, rating and price per mentee, never by the key.

### Decisions

`POST /recommendations/{id}/decision` takes `{action, final_price?}` and is the
endpoint the whole system is advisory for. Up to it nothing has set a price.

| `action`   | `final_price`                                                        |
| ---------- | -------------------------------------------------------------------- |
| `accepted` | Optional, and must equal the advised price if sent. Set to the advice |
| `modified` | Required, and must differ from the advised price                     |
| `rejected` | Optional: the mentor's own price, or none                            |

A price the mentor sets themselves is a whole number between 1 and 5,000 AUD.
Whatever they settle on becomes what the service charges, including a price
named while rejecting the advice. A bare rejection leaves the service charging
whatever it charged.

A modification is stored as `modified` and never as `accepted`, however close
to the advice it is: the share of advice that gets changed is the clearest
evidence the system will ever have about its own usefulness. A modification
equal to the advice is refused, with a message saying to accept it instead.

A recommendation is answered once, and a second attempt returns 409. To decide
again, ask for a fresh price and answer that one. The recommendation's `status`
moves from `pending` to the action.

`GET /services/{service_id}/history` returns every price the service has been
given, newest first, each with its decision or null. Every figure in it was
stored when the price was given, so it needs no models.

### The dashboard

`GET /mentors/{id}/dashboard` returns a mentor's own page in one request: per
service, the field and session labels, the group size, what they charge, the
latest advice, where their price sits against that range and among comparable
mentors, their decisions counted by action, how far their decisions have sat
from the advice on average, a timeline of advice against what they settled on,
and the comparables summary. Then the same counts across every service.

The timeline runs oldest first, the opposite of the history endpoint, because
it is plotted against time and a chart that starts at the right hand end reads
backwards.

**Nothing in this API reports earnings or income.** There are no bookings in
the system, so there is no volume to turn a price into a total, and a figure
presented as income would be invented. The dashboard reports what the system
knows: what the mentor charges, what was advised, how far apart those were, and
where their price falls among comparable mentors.

A server with no comparison table still answers. `comparables_available` says
so, and the two fields that need it are null.

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

How long a mentor has been mentoring is asked at registration, as a number of
years, and shown on their profile as the band it falls in. Both are optional
and neither affects the price: see the note below.

The form no longer asks how many services a mentor plans to offer. It was a
question about the future that a mentor had no way to answer accurately and
that moved their price today, and what the model is given instead is how many
services they have actually published: see `mapping.effective_services`.

Identity is one function. A mentor-scoped request carries a signed access
token, `get_current_mentor_id` in `src/mentor/dependencies.py` is the only
thing in the codebase that turns it into a mentor id, and every mentor-scoped
endpoint depends on it. Every query is filtered by that id, so a mentor can
only read their own records; a request for another mentor's row returns 404
rather than 403, which would confirm the row exists. That one function is what
made replacing the prototype's trusted header with a real token check a change
to one module and nothing else.

### Two models, one API

A newly registered mentor is priced from the eight core inputs: six that the
registration form collects, and two that `src/mentor/mapping.py` holds at a
constant and explains there. Those prices carry `low_confidence: true`: a
form alone is a weaker basis than a record of completed sessions. Once a
mentor has a track record, the same endpoints price them with a second model
that takes 28 further inputs and is measurably more accurate, and the flag
goes away.

### How an existing mentor differs from a new one

Same endpoints, same questions, same responses. Three things change, and all
three follow from the mentor having a `mentor_history` row rather than from
anything they do differently.

**Which model prices them.** A mentor with a complete track record is priced
by the full model, and the response says `model_used: "full"` with
`low_confidence: false`. A mentor with no row, or with a row that is missing
any of its figures, is priced by the core model and the flag stays. There is
no half-way case: the full model has no notion of a missing input, so a
partial record is worth no more than none at all.

**Where their tenure comes from.** A new mentor's time on the platform is the
constant `NEW_MENTOR_TENURE_YEARS`, because there is only one honest answer
for someone who has just joined. A mentor with a record has a real figure and
is priced on it. That is why `mentor_history` holds 29 quantities for a model
that takes 28 extra columns: the 29th is tenure, and it replaces a core
column rather than adding one.

**What their advice is shown against.** A service may record what the mentor
charges today, as `current_price`. When it does, every recommendation for that
service also reports `difference_vs_current_percent`, which is how far the
advice is from the current price as a percentage of it, and
`position_vs_range`, which is `"below"`, `"within"` or `"above"` depending on
where the current price falls relative to the advised range. Both ends of the
range count as `"within"`: a mentor charging exactly the low end is charging
something the system advised. All three are null together for a service with
no price set, rather than zero, which would read as a free session. They are
derived on read from the service's price as it stands now, not stored, because
the question they answer is what to charge instead of what is charged today.

The track record is written by the platform rather than by the mentor, and
there is no endpoint that creates one: it is computed from their activity.
Its columns carry mentor-facing names, and
`src/mentor/mapping.py` is the only place each one meets the model column it
translates to. The application checks at startup that those translated names
are exactly the columns the loaded model was fitted on, in order, and refuses
to serve a price if they are not: a model handed the right values under the
wrong headings answers with a plausible number rather than an error.

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
career length. The years of experience the form asks for are profile text:
they are stored, shown as a band on the mentor's profile, and never given to
the model. In the
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
├── data/            Data acquisition, loading, and the modelled population
├── preprocessing/   Data Preprocessing component
├── models/          ML Model component
├── mentor/          Mentor-facing pricing API
│   ├── mapping.py   The only translation between mentor terms and model inputs
│   ├── prediction.py  Loads both models, produces a price and its range
│   ├── comparables.py Who a price is compared against, and how they are found
│   ├── schemas.py   Request and response shapes
│   ├── security.py  Password hashing and the signed access tokens
│   ├── rate_limit.py  How often one caller may ask for a preview price
│   ├── dependencies.py  The one function that decides whose data a request sees
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

The tests for the demonstration seed script also need the processed dataset,
and are marked `dataset` as well. They skip with a message naming where the
dataset comes from:

```bash
pytest -m "not dataset"       # skip them explicitly
```

The comparable mentors are tested against a small synthetic table built in
`tests/conftest.py` rather than the real file, so what those tests assert is a
fact about the matching rules rather than about how many mentors happen to be
in one field of one dataset. A handful of end-to-end checks do read the real
file and skip with a message naming `scripts/build_comparables.py` when it has
not been built.

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
