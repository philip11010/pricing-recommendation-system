# The mentor-facing web application

The interface a mentor uses to get a suggested session price, see what
comparable mentors charge, and accept, change or decline the suggestion.

Next.js (App Router), TypeScript in strict mode, Tailwind CSS and Recharts.
Every dependency is pinned to an exact version. All prices are in AUD.

The suggestion is advice. Nothing in this application sets a mentor's price.

The visual design is specified in `DESIGN.md`, and `design/mockups.html` is the
clickable reference for all eight screens. The product name is written once, in
the `BRAND` constant in `src/lib/copy.ts`, and nowhere else.

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
python scripts/seed_demo_mentors.py     # 4. mentors with a track record
python scripts/build_demo_activity.py   # 5. their months of reviews
uvicorn src.mentor.app:app --reload --port 8000
```

Steps 1 and 2 are build outputs of a local training run and are git-ignored;
see the root `README.md` for what they need. Steps 4 and 5 are what make the
"mentor with a history" half of the interface work: on a fresh database every
mentor is a new mentor, so there is nothing to compare with and no months to
chart.

Check it with `curl http://127.0.0.1:8000/health`. Both `models_loaded` and
`comparables_loaded` should be `true`.

## Running the web app

```bash
cd web
npm install
npm run dev                    # http://localhost:3000
```

Configuration is read from the environment, and `.env.local` is git-ignored
and must never be committed. The values below are placeholders: fill in your
own.

| Variable                   | Example                     | What it is                                                 |
| -------------------------- | --------------------------- | ---------------------------------------------------------- |
| `NEXT_PUBLIC_API_URL`      | `http://127.0.0.1:8000`     | Where the browser reaches the pricing API                  |
| `PLAYWRIGHT_DEMO_EMAIL`    | `<a seeded mentor address>` | The seeded account the history end to end test signs in as |
| `PLAYWRIGHT_DEMO_PASSWORD` | `<that account's password>` | Its password, never written into a test file               |

`NEXT_PUBLIC_API_URL` defaults to `http://127.0.0.1:8000`, so a local run needs
nothing set. The two Playwright variables have no default: the test that needs
them skips itself with a line saying so when they are not set. The seeding
script prints the addresses it wrote and the password it used.

The API has to allow this origin. It reads `ALLOWED_ORIGINS` as a
comma-separated list and defaults to `http://localhost:3000` and
`http://127.0.0.1:3000`, so a local run needs nothing set there either.

## Scripts

| Command             | What it does                                             |
| ------------------- | -------------------------------------------------------- |
| `npm run dev`       | Development server on port 3000                          |
| `npm run build`     | Production build                                         |
| `npm run start`     | Serve the production build on port 3000                  |
| `npm run lint`      | ESLint                                                   |
| `npm run typecheck` | `tsc --noEmit`                                           |
| `npm run test`      | Unit tests (Vitest)                                      |
| `npm run e2e`       | End to end tests (Playwright). The API has to be running |
| `npm run format`    | Prettier                                                 |
| `npm run check`     | Lint, type check and unit tests in one go                |

The same targets exist from the repository root as `make web-dev`,
`make web-build`, `make web-lint`, `make web-test` and `make web-e2e`.

## Tests

### Unit tests

```bash
npm run test
```

What is tested in isolation is the decisions rather than the wiring: how money
is written, how a session is named from the number of people who can join it,
how the API's refusal becomes a message beside the right field, where a marker
sits on the price ladder, how the dots are stacked when mentors charge about
the same, how the reviews statistics are worked out, how the access token is
kept and discarded, and that every skill the API publishes has a heading on
the form.

### End to end tests

```bash
npm run e2e:install    # once, to fetch the browser
npm run e2e
```

Playwright starts the development server itself and reuses one that is already
running. It does **not** start the API: that has to be running, with the
demonstration mentors seeded, or each test stops with a line naming the command
that was not run.

What they cover:

| Spec                          | What it checks                                                                                   |
| ----------------------------- | ------------------------------------------------------------------------------------------------ |
| `register-and-accept.spec.ts` | Registering, the preview moving with the group size, accepting, and the empty dashboard          |
| `decisions.spec.ts`           | Changing a price, declining one, the refusals, and another mentor's price screen being not found |
| `directory.spec.ts`           | A new mentor appearing in the directory as not yet verified, and the field filter                |
| `demo-mentor.spec.ts`         | A seeded mentor's reviews chart, its sentence and its data table                                 |
| `skills-and-services.spec.ts` | Every skill the running API publishes being on the form, and adding a second service             |
| `narrow-screen.spec.ts`       | The landing, register and price screens at 390 pixels, with no sideways scroll and 44px buttons  |
| `keyboard-login.spec.ts`      | Logging in with the keyboard alone, and how a refusal is announced                               |

They write to the API's database: mentors registered by a test stay there. So
run them against a database kept for that, rather than the one you develop
against. From the repository root, with `DATABASE_URL` set for every command
that follows it:

```bash
export DATABASE_URL=sqlite:///./e2e.db     # PowerShell: $env:DATABASE_URL = "sqlite:///./e2e.db"
alembic upgrade head
python scripts/seed_demo_mentors.py
python scripts/build_demo_activity.py
uvicorn src.mentor.app:app --host 127.0.0.1 --port 8000
```

`e2e.db` is git-ignored, like every other `*.db`. To start it over, delete the
file and run `alembic upgrade head` and the seed scripts again, or reset just
the demonstration mentors with `python scripts/seed_demo_mentors.py --reset`.

Run against an already running web server with
`E2E_WEB_URL=http://127.0.0.1:3000 npm run e2e`.

## Routes

Each screen is in one of two visual registers, which `DESIGN.md` defines: bold
is the full bleed gradient, calm is white with a slim gradient banner.

| Route                    | Register             | What it is                                                        |
| ------------------------ | -------------------- | ----------------------------------------------------------------- |
| `/`                      | Bold                 | What the platform is, an example suggestion, and three mentors    |
| `/login`                 | Bold                 | Email and password, on the gradient                               |
| `/register`              | Calm                 | Four parts, with the live price preview beside them               |
| `/recommendation/[id]`   | Bold hero, then calm | One suggested price, the two comparisons, and the decision        |
| `/similar/[serviceId]`   | Calm                 | Every comparable mentor, narrowed by field or group size          |
| `/mentors`               | Calm                 | The public directory, filtered by field and paged                 |
| `/mentors/[id]`          | Calm                 | One mentor's public profile                                       |
| `/dashboard`             | Calm                 | The mentor's own page: statistics, comparison, reviews, decisions |
| `/dashboard/add-service` | Calm                 | Another service, with the same preview as registration            |

## How it is put together

```
src/
├── app/                   One directory per route, all client components
├── components/
│   ├── ui.tsx             Buttons, cards, chips, notes, loading and error states
│   ├── form.tsx           Labelled fields, the stepper, the skill pills, the error summary
│   ├── site-header.tsx    Dark on bold screens, white on calm ones
│   ├── site-footer.tsx    One line, on every page
│   ├── logo.tsx           The brand mark, inline so it takes its colour from its surface
│   ├── mentor-card.tsx    One mentor, as the landing page and the directory show them
│   ├── price-ladder.tsx   Where one price sits against the middle of the group
│   ├── dot-strip.tsx      One dot per comparable mentor, with this mentor ringed
│   ├── reviews-chart.tsx  Reviews per month, one bar series
│   ├── data-disclosure.tsx The same figures as the chart, as a real table
│   ├── price-preview.tsx  The live price beside the two forms
│   ├── decision-panel.tsx Accept, change, decline
│   └── require-auth.tsx   A page only a signed in mentor may read
└── lib/
    ├── api-client.ts      The only place this application calls the API
    ├── api-types.ts       The shapes the API sends and accepts
    ├── token.ts           The access token, and being signed out by the server
    ├── session.ts         Who is signed in, as a page asks it
    ├── charts.ts          The arithmetic behind the three charts
    ├── errors.ts          The API's refusal, turned into messages
    ├── format.ts          Money, percentages, dates
    ├── session-label.ts   What a session is called, from the API's rule
    ├── copy.ts            The product name, the sentences, and the skill headings
    ├── use-async.ts       One request, and the three states a page shows
    └── use-debounced.ts   A value that settles before the preview asks for a price
```

Three things are worth knowing before changing anything else.

**`lib/api-client.ts` is the only place a request is made.** It is the single
place that attaches the access token, the single place that turns a refusal
into an error carrying the API's own field messages, the single place that
notices the API is not answering, and the single place that reacts to a 401.

**`lib/token.ts` is the only place the token is read or written.** It is kept
in `localStorage` under one key, every read and write is wrapped because
storage throws in a private window, and a 401 from anywhere discards it and
sends the mentor to log in with one short sentence.

**No component writes a colour.** Every value in `tailwind.config.ts` points at
a custom property in `src/app/globals.css`, including the three gradient
recipes and the chart colours, so a chart and a button are the same indigo and
a raw hex in a component is a defect.

## Accessibility and layout

- Mobile first. Usable at 320 pixels wide, with no sideways scrolling, and
  every target at least 44 pixels high on a phone.
- Every input has a real label above it, with its helper text between the label
  and the field so it is read before the field is answered. A placeholder is
  never a label.
- Messages are tied to their field with `aria-describedby`, carry `role="alert"`
  so they are read when they appear, and the field is marked `aria-invalid`. A
  failed submit also renders a focusable summary at the top, which complements
  the inline messages rather than replacing them.
- Both forms carry `noValidate`. The browser's own validation would refuse the
  submission before `onSubmit` ran and show a tooltip worded by the browser,
  tied to nothing and gone on the next click.
- Every chart opens with a plain language sentence, carries `role="img"` with a
  label that states the answer rather than the chart type, and is followed by a
  disclosure holding the same figures as a real table with a caption. Nothing is
  revealed on hover that is not revealed on focus.
- The price ladder identifies its band by a fill, two edge rules and a text
  label together, and its two markers differ in shape as well as in colour, so
  it survives in greyscale.
- Animation respects `prefers-reduced-motion`, and the chart animation is off
  outright. The gradient never moves.
- Every request has a loading, an empty and an error state, and submit buttons
  are disabled while sending, so a price cannot be answered twice by a double
  click.
