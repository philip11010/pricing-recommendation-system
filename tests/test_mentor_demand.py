"""
Demand for a mentor's time, beside the mentors they are compared with.

This is the one comparison on the dashboard that is not about money. Every
other figure there is what somebody charges or what they offer; this one is
how much of the time a mentor put up was taken, against the same measure for
comparable mentors. It exists because responsiveness to demand is the claim
the whole system makes, and a mentor who can see their price against the
market but not their demand against it has been shown half the argument.

Three things are tested, and the order matters.

**It is only shown when it was measured.** A new mentor has no share, and a
zero in its place would say their time went untaken rather than unrecorded.
So the absence is asserted as hard as the presence.

**It compares like with like.** The mentor's own share and the typical share
come from the same kind of measurement, and the typical one is read from the
mentors the rest of the page is already drawing.

**It advises and never instructs.** A mentor booked more than the mentors
beside them may have every reason to stay where they are. The sentence says
what the two figures look like and that there is room to consider something,
which is a different act from telling somebody to raise their price.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.db.mentor_models import MentorHistory
from src.mentor.comparables import ComparablesTable, typical_booked_share

from .conftest import (
    SYNTHETIC_HISTORY,
    SYNTHETIC_PROFILE,
    headers,
    register,
    synthetic_comparables,
)

pytestmark = pytest.mark.app_assets


def give_history(sessions, mentor_id: int, **overrides) -> None:
    """Write a mentor a complete track record, the way the platform would."""
    with sessions() as session:
        session.add(
            MentorHistory(mentor_id=mentor_id, **{**SYNTHETIC_HISTORY, **overrides})
        )
        session.commit()


def dashboard(client, mentor_id: int) -> dict:
    response = client.get(f"/mentors/{mentor_id}/dashboard", headers=headers(mentor_id))
    assert response.status_code == 200
    return response.json()


def table_booked(share: float) -> ComparablesTable:
    """The hand-built table with one known share on every comparable mentor."""
    rows = synthetic_comparables().rows.copy()
    rows["booked_share_365d"] = share
    return ComparablesTable(rows)


# ---------------------------------------------------------------------------
# Whether the card appears at all
# ---------------------------------------------------------------------------
def test_a_new_mentor_is_shown_no_demand_card(client):
    """
    Nothing was measured, so there is nothing to compare.

    The field is null rather than a card reading zero per cent, which would
    be a claim about a mentor the platform has never watched.
    """
    mentor = register(client)

    assert dashboard(client, mentor["mentor"]["id"])["demand"] is None


def test_a_mentor_with_a_record_is_shown_the_card(client, api_sessions):
    mentor = register(client)
    mentor_id = mentor["mentor"]["id"]
    give_history(api_sessions, mentor_id)

    demand = dashboard(client, mentor_id)["demand"]

    assert demand is not None
    assert demand["position"] in {"above", "below", "similar"}
    assert demand["compared_with"] > 0
    assert demand["sentence"]


def test_a_record_without_a_measured_share_shows_nothing(client, api_sessions):
    """
    A track record is not the same thing as a measurement of demand.

    The one field this card needs may be absent from an otherwise complete
    record, and when it is, the card goes rather than falling back to a
    number from somewhere else.
    """
    mentor = register(client)
    mentor_id = mentor["mentor"]["id"]
    give_history(api_sessions, mentor_id, booked_share_365d=None)

    assert dashboard(client, mentor_id)["demand"] is None


# ---------------------------------------------------------------------------
# What it says
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("theirs", "position", "says"),
    [
        (0.20, "above", "booked more than most similar mentors"),
        (0.90, "below", "booked less than most similar mentors"),
        (0.60, "similar", "booked about as much as most similar mentors"),
    ],
)
def test_the_sentence_follows_the_two_figures(
    client, api_sessions, theirs, position, says
):
    """
    Which of the three sentences a mentor reads is decided by the figures.

    The mentor is held at sixty per cent throughout and the mentors beside
    them are moved, so the only thing that changes between these three cases
    is the comparison itself.
    """
    mentor = register(client)
    mentor_id = mentor["mentor"]["id"]
    give_history(api_sessions, mentor_id, booked_share_365d=0.6)
    client.app.state.comparables = table_booked(theirs)

    demand = dashboard(client, mentor_id)["demand"]

    assert demand["position"] == position
    assert says in demand["sentence"]
    assert demand["booked_percent"] == 60.0
    assert demand["typical_booked_percent"] == round(theirs * 100, 1)


def test_the_difference_is_signed_towards_the_mentor(client, api_sessions):
    """A positive difference means this mentor is the busier of the two."""
    mentor = register(client)
    mentor_id = mentor["mentor"]["id"]
    give_history(api_sessions, mentor_id, booked_share_365d=0.75)
    client.app.state.comparables = table_booked(0.25)

    demand = dashboard(client, mentor_id)["demand"]

    assert demand["difference_points"] == pytest.approx(50.0)
    assert demand["booked_percent"] > demand["typical_booked_percent"]


def test_a_small_gap_is_not_reported_as_a_difference(client, api_sessions):
    """
    Two mentors a couple of points apart are as booked as each other.

    Reported as a difference, a gap that small would have a mentor moving
    their price on noise.
    """
    mentor = register(client)
    mentor_id = mentor["mentor"]["id"]
    give_history(api_sessions, mentor_id, booked_share_365d=0.62)
    client.app.state.comparables = table_booked(0.60)

    assert dashboard(client, mentor_id)["demand"]["position"] == "similar"


def test_the_card_advises_and_never_instructs(client, api_sessions):
    """
    No sentence here tells a mentor what to do.

    A mentor busier than the mentors beside them may have good reason to stay
    where they are, and the card is not in a position to know. It says what
    the figures look like and leaves the decision where it belongs.
    """
    banned = ("you should", "you must", "raise your price", "lower your price")
    for index, share in enumerate((0.2, 0.6, 0.9)):
        mentor = register(client, email=f"demand{index}@example.com")
        mentor_id = mentor["mentor"]["id"]
        give_history(api_sessions, mentor_id, booked_share_365d=0.6)
        client.app.state.comparables = table_booked(share)

        said = dashboard(client, mentor_id)["demand"]["sentence"].lower()

        assert not any(phrase in said for phrase in banned), said
        assert "consider" in said or "nothing here pointing" in said


# ---------------------------------------------------------------------------
# Where the typical figure comes from
# ---------------------------------------------------------------------------
def test_the_typical_share_is_the_median_of_the_compared_mentors():
    """Read off the sample, so the card and the chart describe the same group."""
    rows = pd.DataFrame(
        [
            {
                **SYNTHETIC_PROFILE,
                "key": index,
                "field": "law",
                "max_mentees": 2,
                "price": 300,
                "price_per_mentee": 150,
                "rating_overall": 4.5,
                "reviews_total": 20,
                "booked_share_365d": share,
            }
            for index, share in enumerate([0.1, 0.3, 0.5, 0.7, 0.9])
        ]
    )
    found = ComparablesTable(rows).match(field="law", max_mentees=2)

    assert typical_booked_share(found) == pytest.approx(0.5)


def test_with_nobody_comparable_there_is_no_typical_share():
    """A median of nothing is not zero, and a card built on one would lie."""
    rows = pd.DataFrame(
        [
            {
                **SYNTHETIC_PROFILE,
                "key": 1,
                "field": "law",
                "max_mentees": 2,
                "price": 300,
                "price_per_mentee": 150,
                "rating_overall": 4.5,
                "reviews_total": 20,
                "booked_share_365d": 0.5,
            }
        ]
    ).iloc[0:0]

    found = ComparablesTable(rows).match(field="law", max_mentees=2)

    assert typical_booked_share(found) is None
