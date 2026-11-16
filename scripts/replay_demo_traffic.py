"""
Fill the operations dashboard with traffic that actually happened.

An empty dashboard looks broken. The honest way to make one worth looking at
is not to write rows into the log table: it is to call the API, so that every
row in it is a model call the service really made, with a duration it really
took and a status it really answered with. That is what this script does, and
it is the whole reason it exists in this shape.

**It inserts nothing.** There is one database read in here, to find out which
addresses the demonstration mentors sign in with, and not a single write. Every
logged row is written by the API itself, through the same middleware that logs
a mentor's own request. If this script were pointed at a deployment on another
machine, the dashboard there would fill up the same way.

**What it sends.**

* **Previews**, with a field, a group size and a set of skills drawn at random
  from the options the API itself publishes. This is the live figure on the
  registration form, it needs no account, and it is the busiest path in the
  application.
* **Recalculations** for the seeded demonstration mentors: sign in as one and
  ask for a fresh price for one of their services. These are the calls that
  exercise the full model, because those mentors have a complete track record,
  so without them the dashboard would show a service that only ever used the
  core model.

**Pacing.** The preview endpoint allows 60 calls a minute from one address, so
the default here is 50 a minute and the gap between calls is worked out from
whatever rate is asked for. Going faster would start collecting 429s, which
are real traffic and would still be logged honestly, but a dashboard full of
refusals is not what anybody is trying to demonstrate.

**Nothing is invented.** The script reports what it got back, including
failures, and the figures it prints are measured from its own side of the
connection. A model it could not reach is a line in the summary saying so.

Run from the project root, with the API running:

    python scripts/replay_demo_traffic.py
    python scripts/replay_demo_traffic.py --count 200
    python scripts/replay_demo_traffic.py --previews-only
    python scripts/replay_demo_traffic.py --api http://127.0.0.1:8000 --rate 30

The demonstration mentors all sign in with the same password, read from
``DEMO_PASSWORD`` exactly as ``scripts/seed_demo_mentors.py`` reads it. With
no demonstration mentors seeded, or with the wrong password, the script says
so and sends previews only.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.seed_demo_mentors import demo_password  # noqa: E402
from src.db import Mentor, create_db_engine  # noqa: E402

DEFAULT_API = "http://127.0.0.1:8000"

# How many calls one run makes by default. Sixty at 50 a minute is about 72
# seconds, which fills every chart on the dashboard with something and is
# short enough to wait for.
DEFAULT_COUNT = 60

# Calls per minute. The preview endpoint allows 60 from one address, so this
# is deliberately under it: see the note on pacing above.
DEFAULT_RATE = 50
PREVIEW_RATE_LIMIT = 60

# One recalculation for every three previews, when there are demonstration
# mentors to make them as. Previews dominate because they do in the real
# application: the form calls one per edit and the dashboard calls one per
# click.
RECALCULATION_EVERY = 4

# Fixed so that two runs of the same command send the same traffic. A
# demonstration that cannot be repeated is hard to talk about.
DEFAULT_SEED = 42

# How many skills one made-up service covers. Both ends inclusive, and the
# low end is one rather than zero: a mentor who has chosen no skills at all
# is a real case, and it is already the quietest corner of the model's input
# range, so filling a chart with it would say less than nothing.
SKILLS_MIN = 1
SKILLS_MAX = 6

TIMEOUT_SECONDS = 30


class ReplayError(RuntimeError):
    """Something the operator has to fix before this can run."""


@dataclass
class Outcome:
    """One call, as this script measured it from the outside."""

    path: str
    status: int
    milliseconds: int
    model_used: str | None = None


@dataclass
class DemoAccount:
    """One seeded mentor this script can sign in as."""

    mentor_id: int
    email: str
    service_ids: list[int] = field(default_factory=list)
    token: str | None = None


# ---------------------------------------------------------------------------
# HTTP, with the standard library
# ---------------------------------------------------------------------------
# urllib rather than httpx or requests: this script sends four kinds of
# request and has no need of a session, a connection pool or a retry policy,
# and httpx is a development dependency rather than a runtime one. A script
# that ships with the application should not add to what a deployment has to
# install.
def call(
    api: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    token: str | None = None,
) -> tuple[int, Any, int]:
    """
    One request, as (status, parsed body, milliseconds).

    A 4xx or 5xx is returned rather than raised: a refusal is traffic, and
    this script is here to produce traffic and report what happened. A
    connection that cannot be made at all is different, and that raises.
    """
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(f"{api}{path}", data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")

    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        payload = error.read()
        status = error.code
    except urllib.error.URLError as error:
        raise ReplayError(
            f"the API at {api} is not answering ({error.reason}). Start it "
            f"with: uvicorn src.mentor.app:app --port 8000"
        ) from None
    elapsed = int(round((time.perf_counter() - started) * 1000))

    try:
        parsed = json.loads(payload) if payload else None
    except json.JSONDecodeError:
        parsed = None
    return status, parsed, elapsed


def check_api(api: str) -> None:
    """Stop with a sentence rather than with a wall of refused calls."""
    status, body, _ = call(api, "GET", "/health")
    if status != 200 or not isinstance(body, dict):
        raise ReplayError(f"the API at {api} answered /health with {status}")
    if not body.get("models_loaded"):
        raise ReplayError(
            "the API is running without its models, so it cannot price "
            "anything. Run: python scripts/prepare_app_assets.py"
        )


def read_options(api: str) -> tuple[list[str], list[str], int, int]:
    """
    The fields, the skills and the group size bounds, from the API itself.

    Read over HTTP rather than imported from the mapping module, so the
    traffic this sends is traffic the API accepts. A field this script knew
    about and the running API did not would produce a run of 422s.
    """
    status, body, _ = call(api, "GET", "/meta/options")
    if status != 200 or not isinstance(body, dict):
        raise ReplayError(f"/meta/options answered {status}")
    fields = [str(option["id"]) for option in body.get("fields", [])]
    skills = [str(option["id"]) for option in body.get("skills", [])]
    bounds = body.get("max_mentees") or {}
    if not fields or not skills:
        raise ReplayError("/meta/options published no fields or no skills")
    return fields, skills, int(bounds.get("min", 1)), int(bounds.get("max", 8))


# ---------------------------------------------------------------------------
# Who to send the signed-in calls as
# ---------------------------------------------------------------------------
def find_demo_accounts() -> list[DemoAccount]:
    """
    The seeded mentors and their services, read from the database.

    The one database read in this script, and it is a read: the addresses are
    not published by any endpoint, because the public list of demonstration
    mentors deliberately carries nothing a mentee could not already see. The
    alternative would be putting ten addresses in this file, which would then
    have to be kept in step with the seeding script by hand.
    """
    engine = create_db_engine()
    try:
        with Session(engine, expire_on_commit=False) as session:
            mentors = session.scalars(
                select(Mentor).where(Mentor.is_demo.is_(True)).order_by(Mentor.id)
            ).all()
            return [
                DemoAccount(
                    mentor_id=mentor.id,
                    email=mentor.email,
                    service_ids=[service.id for service in mentor.services],
                )
                for mentor in mentors
                if mentor.services
            ]
    finally:
        engine.dispose()


def sign_in(api: str, accounts: list[DemoAccount], password: str) -> list[DemoAccount]:
    """
    Sign in as each demonstration mentor, keeping the ones that worked.

    Signing in is not one of the logged paths: it scores no model, so it adds
    nothing to the dashboard and is not counted in the summary either.
    """
    signed: list[DemoAccount] = []
    for account in accounts:
        status, body, _ = call(
            api,
            "POST",
            "/auth/login",
            {"email": account.email, "password": password},
        )
        if status == 200 and isinstance(body, dict) and body.get("access_token"):
            account.token = str(body["access_token"])
            signed.append(account)
    return signed


# ---------------------------------------------------------------------------
# What to send
# ---------------------------------------------------------------------------
def preview_body(
    chance: random.Random,
    fields: list[str],
    skills: list[str],
    smallest: int,
    largest: int,
) -> dict[str, Any]:
    """
    One made-up registration form, varied across all three answers.

    Group size is drawn from the whole range the API allows rather than from
    a couple of favourites, because the point of the usage charts is to show
    the model being asked different questions.
    """
    count = chance.randint(SKILLS_MIN, min(SKILLS_MAX, len(skills)))
    return {
        "field": chance.choice(fields),
        "max_mentees": chance.randint(smallest, largest),
        "skills": chance.sample(skills, count),
    }


def send_preview(api: str, body: dict[str, Any]) -> Outcome:
    status, answer, elapsed = call(api, "POST", "/preview", body)
    # A preview reports its confidence rather than naming a model. The core
    # model is the only one it can use, because there is no account behind it
    # and so no track record to read.
    model = "core" if status == 200 and isinstance(answer, dict) else None
    return Outcome(
        path="preview", status=status, milliseconds=elapsed, model_used=model
    )


def send_recalculation(api: str, account: DemoAccount, service_id: int) -> Outcome:
    status, answer, elapsed = call(
        api,
        "POST",
        f"/services/{service_id}/recommendations",
        token=account.token,
    )
    model = (
        str(answer.get("model_used"))
        if status == 201 and isinstance(answer, dict) and answer.get("model_used")
        else None
    )
    return Outcome(
        path="recalculation", status=status, milliseconds=elapsed, model_used=model
    )


def pace(rate: int) -> float:
    """Seconds to leave between calls, to stay at ``rate`` a minute."""
    return 60.0 / max(1, rate)


def replay(
    api: str,
    count: int,
    rate: int,
    seed: int,
    accounts: list[DemoAccount],
) -> list[Outcome]:
    """
    Send ``count`` calls, paced, and return what each one answered.

    The gap between calls is measured from when the last one started rather
    than from when it finished, so a slow call does not push the whole run
    past the time it was asked to take. A call slower than the gap simply
    means the next one goes out immediately.
    """
    chance = random.Random(seed)
    fields, skills, smallest, largest = read_options(api)
    gap = pace(rate)
    outcomes: list[Outcome] = []
    turn = 0

    for index in range(count):
        started = time.monotonic()

        if accounts and (index + 1) % RECALCULATION_EVERY == 0:
            account = accounts[turn % len(accounts)]
            turn += 1
            service_id = chance.choice(account.service_ids)
            outcome = send_recalculation(api, account, service_id)
        else:
            outcome = send_preview(
                api, preview_body(chance, fields, skills, smallest, largest)
            )

        outcomes.append(outcome)
        print(
            f"  {index + 1:>4}/{count}  {outcome.path:<14} "
            f"{outcome.status}  {outcome.milliseconds:>5} ms"
        )

        if index + 1 < count:
            waited = time.monotonic() - started
            if waited < gap:
                time.sleep(gap - waited)

    return outcomes


# ---------------------------------------------------------------------------
# What happened
# ---------------------------------------------------------------------------
def summary(outcomes: list[Outcome], seconds: float, rate: int) -> str:
    """
    The run, in the terms the dashboard will show it in.

    Durations here are measured from this script's side of the connection, so
    they include the network and are a little longer than the figures the
    dashboard reports. That is said out loud rather than left for somebody to
    notice as a discrepancy.
    """
    if not outcomes:
        return "Nothing was sent."

    by_path = Counter(outcome.path for outcome in outcomes)
    by_status = Counter(outcome.status for outcome in outcomes)
    by_model = Counter(outcome.model_used or "none" for outcome in outcomes)
    durations = sorted(outcome.milliseconds for outcome in outcomes)
    succeeded = sum(1 for outcome in outcomes if 200 <= outcome.status < 300)

    middle = durations[len(durations) // 2]
    slowest = durations[-1]

    lines = [
        "",
        f"Sent {len(outcomes)} calls in {seconds:.1f}s, paced at {rate} a minute.",
        "",
        "  By path",
    ]
    for path, total in sorted(by_path.items()):
        lines.append(f"    {path:<16} {total}")
    lines.append("")
    lines.append("  By status")
    for status, total in sorted(by_status.items()):
        lines.append(f"    {status:<16} {total}")
    lines.append("")
    lines.append("  By model")
    for model, total in sorted(by_model.items()):
        lines.append(f"    {model:<16} {total}")
    lines.append("")
    lines.append(f"  Answered    {succeeded} of {len(outcomes)}")
    lines.append(f"  Median      {middle} ms")
    lines.append(f"  Slowest     {slowest} ms")
    lines.append("")
    lines.append(
        "  Measured from this script, so these include the network and read "
        "a little longer than the dashboard's own figures."
    )
    lines.append("")
    lines.append("  Every one of those calls is now a row the API wrote itself.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Call the running API so the operations dashboard has real "
            "traffic in it. Writes nothing to the database: every logged row "
            "is written by the API itself."
        )
    )
    parser.add_argument(
        "--count",
        type=int,
        default=DEFAULT_COUNT,
        help=f"how many calls to send (default {DEFAULT_COUNT})",
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=DEFAULT_RATE,
        help=(
            f"calls per minute (default {DEFAULT_RATE}); the preview endpoint "
            f"allows {PREVIEW_RATE_LIMIT} a minute from one address"
        ),
    )
    parser.add_argument(
        "--api",
        default=DEFAULT_API,
        help=f"where the API is answering (default {DEFAULT_API})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"the seed the varied answers are drawn with (default {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--previews-only",
        action="store_true",
        help=(
            "send only previews, and do not sign in as the demonstration "
            "mentors. The full model is then not exercised at all"
        ),
    )
    arguments = parser.parse_args(argv)

    if arguments.count < 1:
        print("FAILED: --count has to be at least 1.", file=sys.stderr)
        return 1
    if arguments.rate > PREVIEW_RATE_LIMIT:
        print(
            f"FAILED: --rate {arguments.rate} is over the {PREVIEW_RATE_LIMIT} "
            f"a minute the preview endpoint allows from one address, so most "
            f"of the run would be refusals. Pick something lower.",
            file=sys.stderr,
        )
        return 1

    api = arguments.api.rstrip("/")

    try:
        check_api(api)

        accounts: list[DemoAccount] = []
        if not arguments.previews_only:
            found = find_demo_accounts()
            if not found:
                print(
                    "No demonstration mentors are seeded, so this run sends "
                    "previews only and the full model is not exercised. Run: "
                    "python scripts/seed_demo_mentors.py"
                )
            else:
                accounts = sign_in(api, found, demo_password())
                if not accounts:
                    print(
                        "Could not sign in as any demonstration mentor, so "
                        "this run sends previews only. They all share one "
                        "password: set DEMO_PASSWORD to the one they were "
                        "seeded with."
                    )
                else:
                    print(
                        f"Signed in as {len(accounts)} of {len(found)} "
                        f"demonstration mentors."
                    )

        print(
            f"Sending {arguments.count} calls to {api} at "
            f"{arguments.rate} a minute."
        )
        started = time.monotonic()
        outcomes = replay(
            api, arguments.count, arguments.rate, arguments.seed, accounts
        )
        print(summary(outcomes, time.monotonic() - started, arguments.rate))
    except ReplayError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped. The calls already sent are logged.", file=sys.stderr)
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
