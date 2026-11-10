# Career Mentor: the mentor-facing web application

The interface a mentor uses to get a suggested session price, see what
comparable mentors charge, and accept, change or decline the suggestion.

Next.js (App Router), TypeScript in strict mode, Tailwind CSS and Recharts.
Every dependency is pinned to an exact version. All prices are in AUD.

The suggestion is advice. Nothing in this application sets a mentor's price.

---

## What you need running

This application has no backend of its own. It calls the pricing API in
`../src/mentor` from the browser, so that API has to be running, and for the
whole interface to be demonstrable it needs its two build outputs and the
demonstration mentors.

From the repository root, in a Python environment with the project installed:

```bash
python scripts/prepare_app_assets.py    # 1. the models and their metadata
python scripts/build_comparables.py     # 2. the mentors a price is compared with
alembic upgrade head                    # 3. the database schema
python scripts/seed_demo_mentors.py     # 4. five mentors with a track record
uvicorn src.mentor.app:app --reload --port 8000
```

Steps 1 and 2 are build outputs of a local training run and are git-ignored;
see the root `README.md` for what they need. Step 4 is what makes the
"I am already a mentor" half of the interface work: on a fresh database every
mentor is a new mentor, so there is nobody to show.

Check it with `curl http://127.0.0.1:8000/health`. Both `models_loaded` and
`comparables_loaded` should be `true`.

## Running this application

```bash
cd web
cp .env.example .env.local     # optional: the default already points at :8000
npm install
npm run dev                    # http://localhost:3000
```

`.env.local` is git-ignored and must never be committed.

| Variable              | Default                 | What it is                        |
| --------------------- | ----------------------- | --------------------------------- |
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` | Where the browser reaches the API |

The API has to allow this origin. It reads `ALLOWED_ORIGINS` as a
comma-separated list and defaults to `http://localhost:3000` and
`http://127.0.0.1:3000`, so a local run needs nothing set.

## Scripts

| Command             | What it does                                             |
| ------------------- | -------------------------------------------------------- |
| `npm run dev`       | Development server on port 3000                          |
| `npm run build`     | Production build                                         |
| `npm run start`     | Serve the production build on port 3000                  |
| `npm run lint`      | ESLint                                                   |
| `npm run typecheck` | `tsc --noEmit`                                           |
| `npm run test`      | Unit tests (Vitest)                                      |
| `npm run e2e`       | End-to-end tests (Playwright). The API has to be running |
| `npm run format`    | Prettier                                                 |
| `npm run check`     | Lint, type check and unit tests in one go                |

The same targets exist from the repository root as `make web-dev`,
`make web-build`, `make web-lint`, `make web-test` and `make web-e2e`.

## Tests

### Unit tests

```bash
npm run test
```

Three things that are worth testing in isolation because they are decisions
rather than wiring: how money is written, how a session is named from the
number of mentees who can join it, and how the API's refusal becomes a
message beside the right field.

### End-to-end tests

```bash
npm run e2e:install    # once, to fetch the browser
npm run e2e
```

Playwright starts the development server itself and reuses one that is
already running. It does **not** start the API: that has to be running, with
the demonstration mentors seeded, or each test stops with a line naming the
command that was not run.

What they cover:

| Spec                               | What it checks                                                                               |
| ---------------------------------- | -------------------------------------------------------------------------------------------- |
| `register-and-accept.spec.ts`      | A new mentor registers, is shown a first estimate and the comparison, and accepts it         |
| `existing-mentor-modifies.spec.ts` | A mentor with a record reviews their price, modifies it, and their record says Modified      |
| `decline-then-own-price.spec.ts`   | Declining, then naming a price anyway; declining and deciding later; answering a price twice |
| `invalid-registration.spec.ts`     | Field errors are shown, tied to their fields, and nothing is submitted                       |
| `narrow-screen.spec.ts`            | Registration, the suggestion and the landing page at 375 pixels, with no sideways scroll     |

They write to the API's database: mentors registered by a test stay there, and
a test that modifies a demonstration mentor's price leaves it modified. So run
them against a database kept for that, rather than the one you develop
against. From the repository root, with `DATABASE_URL` set for every command
that follows it:

```bash
export DATABASE_URL=sqlite:///./e2e.db     # PowerShell: $env:DATABASE_URL = "sqlite:///./e2e.db"
alembic upgrade head
python scripts/seed_demo_mentors.py
uvicorn src.mentor.app:app --host 127.0.0.1 --port 8000
```

`e2e.db` is git-ignored, like every other `*.db`. To start it over, delete the
file and run `alembic upgrade head` and the seed script again, or reset just
the demonstration mentors with `python scripts/seed_demo_mentors.py --reset`.

Run against an already running web server with
`E2E_WEB_URL=http://127.0.0.1:3000 npm run e2e`.

## Routes

| Route                    | What it is                                                                 |
| ------------------------ | -------------------------------------------------------------------------- |
| `/`                      | What the platform is, who it is for, and the three steps of the suggestion |
| `/register`              | Registration: account, profile, service. Ends on the first suggestion      |
| `/mentors`               | The demonstration mentors, to pick an identity from                        |
| `/recommendation/[id]`   | One suggested price, the comparison, and the decision                      |
| `/similar/[serviceId]`   | Every comparable mentor, sortable and paged                                |
| `/dashboard`             | The mentor's own page: prices, suggestions, decisions, timeline, history   |
| `/dashboard/add-service` | Another service, asked with the same questions as registration             |

## How it is put together

```
src/
├── app/                  One directory per route, all client components
├── components/
│   ├── ui.tsx            Buttons, cards, callouts, loading and error states
│   ├── form.tsx          Labelled inputs, the mentee stepper, the skill checklist
│   ├── service-fields.tsx  The questions that set the price, asked in two places
│   ├── site-header.tsx   Who you are signed in as, and the way out
│   ├── require-mentor.tsx  A page that needs an identity, and what to do without one
│   ├── comparables.tsx   The summary line and the rows of comparable mentors
│   ├── price-histogram.tsx The spread of prices, with markers
│   ├── timeline-chart.tsx  Suggested against chosen, over time
│   └── decision-panel.tsx  Accept, modify, decline
└── lib/
    ├── api-client.ts     The only place this application calls the API
    ├── api-types.ts      The shapes the API sends and accepts
    ├── errors.ts         The API's refusal, turned into messages
    ├── format.ts         Money, percentages, dates
    ├── session-label.ts  What a session is called, from the API's rule
    ├── mentor-session.ts Which mentor this browser is acting as
    ├── copy.ts           The sentences this application says about a price
    └── use-async.ts      One request, and the three states a page shows
```

Two things are worth knowing before changing anything else.

**`lib/api-client.ts` is the only place a request is made.** It is the single
place that adds the `X-Mentor-Id` header, the single place that turns a
refusal into an error carrying the API's own field messages, and the single
place that notices the API is not answering.

**`lib/mentor-session.ts` is the only place identity is read or written.**
There is no authentication: the mentor's id is kept in browser storage and
sent on every mentor-scoped request. Replacing that with a real sign-in is a
change to that file and to the header that reads it.

## Accessibility and layout

- Mobile first. Usable at 360 pixels wide, with no sideways scrolling, and
  every target at least 44 pixels high.
- Every input has a real label. Messages are tied to their field with
  `aria-describedby`, carry `role="alert"` so they are read when they appear,
  and the field is marked `aria-invalid`, so they are read out rather than
  only drawn in red.
- The registration form carries `noValidate`. The browser's own validation
  would refuse the submission before the form's `onSubmit` ran and show a
  tooltip that is worded by the browser, tied to nothing and gone on the next
  click. With it off, this application's messages are the only ones a mentor
  sees.
- The mentee stepper is a `spinbutton` and takes the arrow keys, Home and End.
  The skill checklist is ordinary checkboxes.
- Both charts carry a text summary for a screen reader and the same figures as
  a table for anyone who would rather read them.
- Animation respects `prefers-reduced-motion`.
- Every request has a loading, an empty and an error state, and submit buttons
  are disabled while sending, so a price cannot be answered twice by a double
  click.
