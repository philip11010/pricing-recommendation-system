"""
Tests for the script that fills the dashboard with real traffic.

The claim this script makes is that every row the dashboard shows is a model
call the API really made, so the test that matters most is the one that checks
it writes nothing itself: its source contains no insert, no session add and no
reference to the log table at all.

The rest is the arithmetic and the refusals, which are worth testing because
they are the parts a run would get wrong silently: a pace that is too fast
would produce a dashboard full of 429s, and a summary that averaged the
durations it was given rather than reporting them would print a figure nobody
measured.

Nothing here starts a server. The HTTP layer is one function, ``call``, and
the tests that exercise the run replace it, so what is checked is the shape of
the traffic rather than urllib.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import replay_demo_traffic as replay
from src.db.mentor_models import RequestLog


# ---------------------------------------------------------------------------
# It writes nothing
# ---------------------------------------------------------------------------
def test_the_script_never_writes_to_the_database():
    """
    The claim the whole script rests on, checked against its own source.

    Fabricated analytics would be dishonest, so this is not left to a code
    review: the script may read the demonstration mentors and may call the
    API, and it may not write anything anywhere.
    """
    source = Path(replay.__file__).read_text(encoding="utf-8")

    for banned in (
        "session.add",
        "session.commit",
        "session.merge",
        "session.execute",
        "RequestLog",
        "request_logs",
        "INSERT INTO",
        # The one insert the file is allowed is sys.path.insert, which puts
        # the project root on the import path and touches no database.
        "sa.insert",
        "sqlalchemy.insert",
    ):
        assert banned not in source, f"{banned} appears in the replay script"

    assert source.count("insert(") == source.count("sys.path.insert(")


def test_the_script_does_not_import_the_log_table():
    """It cannot write to a table it has no handle on."""
    assert not hasattr(replay, "RequestLog")
    assert RequestLog.__tablename__ == "request_logs"


# ---------------------------------------------------------------------------
# Pacing
# ---------------------------------------------------------------------------
def test_the_default_rate_is_under_the_endpoints_limit():
    """
    A faster run would collect 429s, which are honest and useless.

    They would be logged as what they are, so the dashboard would not lie;
    it would just be a dashboard of refusals.
    """
    assert replay.DEFAULT_RATE < replay.PREVIEW_RATE_LIMIT


def test_the_gap_between_calls_follows_the_rate():
    assert replay.pace(60) == pytest.approx(1.0)
    assert replay.pace(30) == pytest.approx(2.0)
    # Never a division by zero, however the argument was given.
    assert replay.pace(0) == pytest.approx(60.0)


def test_a_rate_over_the_limit_is_refused(capsys):
    assert replay.main(["--rate", "120"]) == 1

    assert "over the 60 a minute" in capsys.readouterr().err


def test_a_count_below_one_is_refused(capsys):
    assert replay.main(["--count", "0"]) == 1

    assert "at least 1" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# What it sends
# ---------------------------------------------------------------------------
OPTIONS = {
    "fields": [{"id": "technology_software"}, {"id": "law"}, {"id": "engineering"}],
    "skills": [
        {"id": "cv_review"},
        {"id": "interview_preparation"},
        {"id": "career_planning"},
        {"id": "networking"},
    ],
    "max_mentees": {"min": 1, "max": 8},
}


@pytest.fixture
def recorded(monkeypatch) -> list[tuple[str, str, dict | None, str | None]]:
    """
    Every call the script would have made, with the HTTP replaced.

    The replacement answers the way the API does, so the script's own
    handling of a status and a body is exercised; what is dropped is urllib
    and the sleep between calls.
    """
    sent: list[tuple[str, str, dict | None, str | None]] = []

    def fake_call(api, method, path, body=None, token=None):
        sent.append((method, path, body, token))
        if path == "/health":
            return 200, {"models_loaded": True, "comparables_loaded": True}, 3
        if path == "/meta/options":
            return 200, OPTIONS, 4
        if path == "/preview":
            return 200, {"session_price": 210, "range_low": 160, "range_high": 280}, 12
        if path == "/auth/login":
            return 200, {"access_token": "a-token"}, 20
        if path.endswith("/recommendations"):
            return 201, {"id": 1, "model_used": "full"}, 25
        raise AssertionError(f"unexpected call to {path}")

    monkeypatch.setattr(replay, "call", fake_call)
    monkeypatch.setattr(replay.time, "sleep", lambda _seconds: None)
    return sent


def test_previews_vary_across_all_three_answers(recorded):
    outcomes = replay.replay("http://api", count=12, rate=60, seed=1, accounts=[])

    previews = [body for method, path, body, _ in recorded if path == "/preview"]
    assert len(previews) == 12
    assert len({body["field"] for body in previews}) > 1
    assert len({body["max_mentees"] for body in previews}) > 1
    assert len({tuple(sorted(body["skills"])) for body in previews}) > 1
    assert all(outcome.status == 200 for outcome in outcomes)


def test_every_preview_is_one_the_api_published_the_answers_for(recorded):
    """
    The options come from the API, so the traffic is traffic it accepts.

    A field this script knew about and the running API did not would produce
    a run of 422s, which would fill the dashboard with validation failures.
    """
    replay.replay("http://api", count=20, rate=60, seed=3, accounts=[])

    allowed_fields = {option["id"] for option in OPTIONS["fields"]}
    allowed_skills = {option["id"] for option in OPTIONS["skills"]}
    for method, path, body, _ in recorded:
        if path != "/preview":
            continue
        assert body["field"] in allowed_fields
        assert set(body["skills"]) <= allowed_skills
        assert 1 <= body["max_mentees"] <= 8


def test_the_run_is_repeatable(recorded):
    """Two runs of the same command send the same traffic."""
    replay.replay("http://api", count=8, rate=60, seed=7, accounts=[])
    first = [body for _, path, body, _ in recorded if path == "/preview"]
    recorded.clear()
    replay.replay("http://api", count=8, rate=60, seed=7, accounts=[])
    second = [body for _, path, body, _ in recorded if path == "/preview"]

    assert first == second


def test_demonstration_mentors_get_recalculations_with_their_own_token(recorded):
    """
    The calls that exercise the full model, which previews never can.

    A preview has no account behind it, so it can only ever use the core
    model. Without these the dashboard would show a service that has never
    used the second one.
    """
    accounts = [
        replay.DemoAccount(mentor_id=3, email="a@example.com", service_ids=[11]),
        replay.DemoAccount(mentor_id=4, email="b@example.com", service_ids=[22, 23]),
    ]
    signed = replay.sign_in("http://api", accounts, "a-password")
    recorded.clear()

    outcomes = replay.replay("http://api", count=8, rate=60, seed=5, accounts=signed)

    recalculations = [
        (path, token)
        for _, path, _, token in recorded
        if path.endswith("/recommendations")
    ]
    assert len(recalculations) == 2
    assert all(token == "a-token" for _, token in recalculations)
    assert {outcome.model_used for outcome in outcomes} == {"core", "full"}


def test_the_mentors_are_taken_in_turn(recorded):
    """
    Round robin rather than at random, so every seeded mentor is used.

    A random pick would leave one of ten mentors with nothing against them on
    a short run, which is the opposite of what the demonstration is for.
    """
    accounts = [
        replay.DemoAccount(
            mentor_id=index, email=f"{index}@example.com", service_ids=[index * 10]
        )
        for index in range(1, 4)
    ]
    for account in accounts:
        account.token = "a-token"

    replay.replay("http://api", count=12, rate=60, seed=11, accounts=accounts)

    used = [path for _, path, _, _ in recorded if path.endswith("/recommendations")]
    assert used == [
        "/services/10/recommendations",
        "/services/20/recommendations",
        "/services/30/recommendations",
    ]


def test_previews_only_sends_no_signed_in_calls(recorded):
    replay.replay("http://api", count=8, rate=60, seed=5, accounts=[])

    assert all(token is None for _, _, _, token in recorded)


# ---------------------------------------------------------------------------
# What it reports
# ---------------------------------------------------------------------------
def test_the_summary_reports_what_came_back(recorded):
    outcomes = [
        replay.Outcome("preview", 200, 10, "core"),
        replay.Outcome("preview", 429, 2, None),
        replay.Outcome("recalculation", 201, 30, "full"),
    ]

    printed = replay.summary(outcomes, seconds=3.6, rate=50)

    assert "Sent 3 calls" in printed
    assert "paced at 50 a minute" in printed
    assert "Answered    2 of 3" in printed
    # The median is one of the measurements, not an average of them.
    assert "Median      10 ms" in printed
    assert "Slowest     30 ms" in printed
    assert "429" in printed
    assert "full" in printed
    # The difference between this script's figures and the dashboard's is
    # stated rather than left to be discovered as a discrepancy.
    assert "include the network" in printed


def test_the_summary_says_so_when_nothing_was_sent():
    assert replay.summary([], seconds=0.0, rate=50) == "Nothing was sent."


def test_a_refused_call_is_reported_and_not_raised(monkeypatch):
    """
    A refusal is traffic. The script reports it and keeps going.

    A run that stopped on the first 429 would stop exactly when the pacing
    needed to be looked at.
    """

    def refusing_call(api, method, path, body=None, token=None):
        if path == "/meta/options":
            return 200, OPTIONS, 4
        return 429, {"detail": "too many"}, 1

    monkeypatch.setattr(replay, "call", refusing_call)
    monkeypatch.setattr(replay.time, "sleep", lambda _seconds: None)

    outcomes = replay.replay("http://api", count=3, rate=60, seed=1, accounts=[])

    assert [outcome.status for outcome in outcomes] == [429, 429, 429]
    assert all(outcome.model_used is None for outcome in outcomes)


# ---------------------------------------------------------------------------
# Refusing to start
# ---------------------------------------------------------------------------
def test_it_stops_when_the_api_has_no_models(monkeypatch, capsys):
    monkeypatch.setattr(
        replay,
        "call",
        lambda *args, **kwargs: (200, {"models_loaded": False}, 2),
    )

    assert replay.main(["--count", "1"]) == 1

    assert "without its models" in capsys.readouterr().err


def test_it_stops_when_the_api_is_not_answering(monkeypatch, capsys):
    def unreachable(*_args, **_kwargs):
        raise replay.ReplayError("the API at http://api is not answering (refused)")

    monkeypatch.setattr(replay, "call", unreachable)

    assert replay.main(["--count", "1"]) == 1

    assert "not answering" in capsys.readouterr().err


def test_it_stops_when_the_options_list_is_empty(monkeypatch):
    monkeypatch.setattr(
        replay,
        "call",
        lambda *args, **kwargs: (200, {"fields": [], "skills": []}, 2),
    )

    with pytest.raises(replay.ReplayError, match="no fields"):
        replay.read_options("http://api")
