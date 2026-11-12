"""
Tests for a mentor's activity over time, and for the script that builds it.

Two halves, and the second is the one that matters most.

The endpoint is simple: four parallel arrays, a flag and a sentence, for the
mentor's own activity and nobody else's. What is worth testing about it is the
difference between a null and a zero, because that distinction is the whole
claim the response makes: a month with no record of how busy the mentor was is
not a month in which they were not busy.

The script is where the care is. It joins mentors back to the raw files
through an opaque key, over a window of complete months, from two files that
cover different periods. So it is tested against small hand-written files
where every expected figure can be stated: that reviews are counted in the
right month, that a month before the mentor existed is left out while a quiet
month inside their span is a zero, that a booked share is computed where the
availability file covers the month and left empty where it does not, and that
running it twice leaves the same table.

Neither half needs the prepared models or the real dataset: the activity has
nothing to do with a price, and the lookup from a key to a raw identifier is
replaced with a two-row table so that what is being tested is the join rather
than the contents of one build of a dataset.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from sqlalchemy import select

from scripts import build_demo_activity as build
from src.db.mentor_models import Mentor, MentorActivity, Service
from src.mentor.app import TREND_MONTHS, activity_note, direction_of

from .conftest import headers

# Two seeded mentors and the raw identifiers they were built from. The keys
# are positions in a dataset and the identifiers are what the raw files are
# keyed by, which is exactly the join the script has to make.
FIRST_KEY, FIRST_ID = 11, 1001
SECOND_KEY, SECOND_ID = 22, 2002

# A third identifier, in the raw files and belonging to nobody, so a test can
# tell that the script writes one mentor's activity and not whatever it finds.
STRANGER_ID = 3003


@pytest.fixture
def lookup(monkeypatch):
    """
    The dataset lookup, as two rows rather than a hundred thousand.

    The script reads the processed dataset only to turn a source key into the
    identifier the raw files use. Replacing that with a two-row table keeps
    these tests about the join and the months, and lets them run without a
    git-ignored build output.
    """
    frame = pd.DataFrame(
        {
            build.KEY_COLUMN: [FIRST_KEY, SECOND_KEY],
            build.SOURCE_ID_COLUMN: [FIRST_ID, SECOND_ID],
        }
    )
    monkeypatch.setattr(build, "load_master", lambda: frame)
    return frame


@pytest.fixture
def seeded(db_session):
    """Two demonstration mentors, each with a service and a source record."""
    mentors = []
    for index, key in enumerate((FIRST_KEY, SECOND_KEY)):
        mentor = Mentor(
            full_name=f"Demo {index}",
            email=f"demo{index}@example.com",
            is_demo=True,
            source_key=key,
        )
        mentor.services.append(
            Service(
                session_label="one_to_one",
                field="technology_software",
                max_mentees=1,
                min_commitment=1,
                skills=[],
                profile_verified=True,
            )
        )
        db_session.add(mentor)
        mentors.append(mentor)
    db_session.commit()
    return mentors


def write_reviews(path, rows):
    """A reviews file: one row per review, with a date."""
    pd.DataFrame(rows, columns=["listing_id", "date"]).assign(
        id=range(len(rows)),
        reviewer_id=0,
        reviewer_name="",
        comments="",
    ).to_csv(path, index=False)
    return path


def write_calendar(path, rows, *, with_price=False):
    """An availability file: one row per day, open or taken."""
    frame = pd.DataFrame(rows, columns=["listing_id", "date", "available"])
    frame["minimum_nights"] = 1
    frame["maximum_nights"] = 10
    if with_price:
        frame["price"] = "$200.00"
    frame.to_csv(path, index=False)
    return path


def days(listing_id, month, count, available):
    """``count`` days of one month, all open or all taken."""
    return [
        (listing_id, f"{month}-{day:02d}", available) for day in range(1, count + 1)
    ]


# A year of reviews for the first mentor and three months for the second,
# ending in the middle of a month so the window has a part month to leave out.
REVIEW_ROWS = [
    (FIRST_ID, "2026-03-04"),
    (FIRST_ID, "2026-03-20"),
    (FIRST_ID, "2026-04-02"),
    # Nothing in May: a quiet month inside the mentor's own span.
    (FIRST_ID, "2026-06-11"),
    (FIRST_ID, "2026-06-12"),
    (FIRST_ID, "2026-06-30"),
    (SECOND_ID, "2026-05-09"),
    (STRANGER_ID, "2026-04-04"),
    (STRANGER_ID, "2026-06-01"),
    # The newest review in the file, which is the date the snapshot was taken.
    (FIRST_ID, "2026-07-14"),
]


@pytest.fixture
def raw_files(tmp_path):
    """The two raw files, written small enough to state every expectation."""
    reviews = write_reviews(tmp_path / "reviews.csv", REVIEW_ROWS)
    calendar = write_calendar(
        tmp_path / "calendar.csv",
        days(FIRST_ID, "2026-08", 10, "t") + days(SECOND_ID, "2026-08", 10, "f"),
    )
    return reviews, calendar


def activity_of(session, mentor_id):
    return list(
        session.scalars(
            select(MentorActivity)
            .where(MentorActivity.mentor_id == mentor_id)
            .order_by(MentorActivity.month)
        )
    )


# ---------------------------------------------------------------------------
# Building it
# ---------------------------------------------------------------------------
def test_the_window_is_the_last_complete_months(db_session, seeded, lookup, raw_files):
    """
    The month the snapshot was taken in is left out, because it is a part
    month: counting it beside whole ones would show every mentor falling off
    a cliff at the right hand edge of the chart.
    """
    reviews, calendar = raw_files

    report = build.build_activity(
        db_session, reviews_path=reviews, calendar_path=calendar, months=4
    )

    assert report.first_month == date(2026, 3, 1)
    assert report.last_month == date(2026, 6, 1)


def test_reviews_are_counted_in_the_month_they_were_left(
    db_session, seeded, lookup, raw_files
):
    reviews, calendar = raw_files

    build.build_activity(
        db_session, reviews_path=reviews, calendar_path=calendar, months=4
    )

    rows = activity_of(db_session, seeded[0].id)
    assert [(row.month, row.reviews_count) for row in rows] == [
        (date(2026, 3, 1), 2),
        (date(2026, 4, 1), 1),
        # A month inside the mentor's own span with no reviews in it had none.
        (date(2026, 5, 1), 0),
        (date(2026, 6, 1), 3),
    ]


def test_a_month_before_the_mentor_arrived_is_left_out(
    db_session, seeded, lookup, raw_files
):
    """
    The distinction the whole table rests on. The second mentor's first review
    is in May, so March and April are not quiet months for them: they are
    months the mentor was not there for, and a zero would be a figure about
    nothing.
    """
    reviews, calendar = raw_files

    build.build_activity(
        db_session, reviews_path=reviews, calendar_path=calendar, months=4
    )

    rows = activity_of(db_session, seeded[1].id)
    assert [row.month for row in rows] == [date(2026, 5, 1), date(2026, 6, 1)]
    assert [row.reviews_count for row in rows] == [1, 0]


def test_another_records_reviews_are_not_written_to_anybody(
    db_session, seeded, lookup, raw_files
):
    """
    The raw files hold rows for records nobody was seeded from. Counting them
    against a mentor would put somebody else's activity on their page.
    """
    reviews, calendar = raw_files

    build.build_activity(
        db_session, reviews_path=reviews, calendar_path=calendar, months=4
    )

    total = sum(
        row.reviews_count
        for mentor in seeded
        for row in activity_of(db_session, mentor.id)
    )
    assert total == 7


def test_a_booked_share_is_left_empty_when_the_file_cannot_say(
    db_session, seeded, lookup, raw_files
):
    """
    The availability file is a forward-looking snapshot. For a month that has
    already happened it has nothing, and nothing is reported as nothing
    rather than as a mentor who was booked for none of their time.
    """
    reviews, calendar = raw_files

    report = build.build_activity(
        db_session, reviews_path=reviews, calendar_path=calendar, months=4
    )

    rows = activity_of(db_session, seeded[0].id)
    assert all(row.booked_share is None for row in rows)
    assert any("forward-looking" in note for note in report.notes)
    assert any("does not overlap" in note for note in report.notes)


def test_a_booked_share_is_computed_where_the_file_does_cover_the_month(
    db_session, seeded, lookup, tmp_path
):
    """
    The same code on a file that overlaps the window, so the share itself is
    tested rather than only the refusal to invent one. Six of ten days taken
    is a booked share of 0.6.
    """
    reviews = write_reviews(
        tmp_path / "reviews.csv",
        [(FIRST_ID, "2026-05-02"), (FIRST_ID, "2026-06-20")],
    )
    calendar = write_calendar(
        tmp_path / "calendar.csv",
        days(FIRST_ID, "2026-05", 6, "f") + days(FIRST_ID, "2026-05", 4, "t"),
    )

    build.build_activity(
        db_session, reviews_path=reviews, calendar_path=calendar, months=1
    )

    (row,) = activity_of(db_session, seeded[0].id)
    assert row.month == date(2026, 5, 1)
    assert row.booked_share == pytest.approx(0.6)


def test_a_price_per_month_is_read_when_the_file_has_one(
    db_session, seeded, lookup, tmp_path
):
    """
    The export this project was built on has no price column, so the figure
    is absent. The code that would read one is still tested, because the
    column is the only thing standing between the chart and a price line.
    """
    reviews = write_reviews(
        tmp_path / "reviews.csv",
        [(FIRST_ID, "2026-05-02"), (FIRST_ID, "2026-06-20")],
    )
    calendar = write_calendar(
        tmp_path / "calendar.csv",
        days(FIRST_ID, "2026-05", 4, "f"),
        with_price=True,
    )

    build.build_activity(
        db_session, reviews_path=reviews, calendar_path=calendar, months=1
    )

    (row,) = activity_of(db_session, seeded[0].id)
    assert row.price == 200


def test_a_price_is_left_empty_when_the_file_has_no_price_column(
    db_session, seeded, lookup, raw_files
):
    reviews, calendar = raw_files

    report = build.build_activity(
        db_session, reviews_path=reviews, calendar_path=calendar, months=4
    )

    rows = activity_of(db_session, seeded[0].id)
    assert all(row.price is None for row in rows)
    assert any("no price column" in note for note in report.notes)


def test_building_twice_leaves_the_same_table(db_session, seeded, lookup, raw_files):
    """
    The normal mistake, and the normal thing to do after a reseed. The window
    is replaced rather than added to.
    """
    reviews, calendar = raw_files
    build.build_activity(
        db_session, reviews_path=reviews, calendar_path=calendar, months=4
    )
    before = [
        (row.mentor_id, row.month, row.reviews_count)
        for mentor in seeded
        for row in activity_of(db_session, mentor.id)
    ]

    build.build_activity(
        db_session, reviews_path=reviews, calendar_path=calendar, months=4
    )

    after = [
        (row.mentor_id, row.month, row.reviews_count)
        for mentor in seeded
        for row in activity_of(db_session, mentor.id)
    ]
    assert after == before


def test_a_key_that_is_not_in_the_dataset_stops_the_build(
    db_session, seeded, lookup, raw_files
):
    """
    A mentor seeded from a different build of the dataset. Their activity
    would be somebody else's, so the build stops and says what to do rather
    than writing it.
    """
    reviews, calendar = raw_files
    seeded[0].source_key = 9999
    db_session.commit()

    with pytest.raises(build.ActivityInputError) as error:
        build.build_activity(
            db_session, reviews_path=reviews, calendar_path=calendar, months=4
        )

    assert "source key" in str(error.value)
    assert "seed_demo_mentors" in str(error.value)


def test_a_database_with_no_demo_mentors_builds_nothing_and_says_so(
    db_session, lookup, raw_files
):
    reviews, calendar = raw_files

    report = build.build_activity(
        db_session, reviews_path=reviews, calendar_path=calendar, months=4
    )

    assert report.mentors == 0
    assert report.months_written == 0
    assert any("seed_demo_mentors" in note for note in report.notes)


def test_a_missing_raw_file_names_it(db_session, seeded, lookup, tmp_path):
    with pytest.raises(build.ActivityInputError) as error:
        build.build_activity(
            db_session,
            reviews_path=tmp_path / "absent.csv",
            calendar_path=tmp_path / "also-absent.csv",
        )

    assert "absent.csv" in str(error.value)
    assert "git-ignored" in str(error.value)


def test_the_file_paths_come_from_the_arguments_then_the_environment(monkeypatch):
    """
    Nothing here is tied to one machine's folders: an argument wins, then the
    environment, then a path inside the project.
    """
    monkeypatch.setenv(build.REVIEWS_VARIABLE, "from/the/environment.csv")

    from_argument = build.file_argument(
        "given/on/the/command/line.csv", build.REVIEWS_VARIABLE, build.DEFAULT_REVIEWS
    )
    from_environment = build.file_argument(
        None, build.REVIEWS_VARIABLE, build.DEFAULT_REVIEWS
    )

    assert from_argument.name == "line.csv"
    assert from_environment.name == "environment.csv"

    monkeypatch.delenv(build.REVIEWS_VARIABLE)
    assert build.file_argument(None, build.REVIEWS_VARIABLE, build.DEFAULT_REVIEWS) == (
        build.DEFAULT_REVIEWS
    )


def test_the_default_paths_are_inside_the_project(tmp_path):
    from src.config import PROJECT_ROOT

    for default in (build.DEFAULT_REVIEWS, build.DEFAULT_CALENDAR):
        assert default.is_relative_to(PROJECT_ROOT)


# ---------------------------------------------------------------------------
# The sentence
# ---------------------------------------------------------------------------
def test_a_mentor_with_nothing_recorded_is_told_what_will_appear():
    note = activity_note([])

    assert "nothing to show" in note
    assert "reviews" in note


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ([1, 1, 1, 1, 1, 1], "steady"),
        ([1, 1, 1, 5, 6, 7], "picking up"),
        ([7, 6, 5, 1, 1, 1], "slowing down"),
    ],
)
def test_the_sentence_describes_the_direction_of_the_reviews(counts, expected):
    rows = [
        MentorActivity(mentor_id=1, month=date(2026, index + 1, 1), reviews_count=count)
        for index, count in enumerate(counts)
    ]

    assert expected in activity_note(rows)


def test_the_sentence_describes_the_price_when_there_is_one():
    """
    The price is the more useful of the two when the platform has it, because
    it is the thing the mentor is being advised about.
    """
    rows = [
        MentorActivity(
            mentor_id=1,
            month=date(2026, index + 1, 1),
            reviews_count=2,
            price=price,
        )
        for index, price in enumerate([100, 100, 100, 200, 200, 200])
    ]

    note = activity_note(rows)

    assert "price" in note
    assert "gone up" in note


def test_the_sentence_never_claims_a_direction_from_one_month():
    rows = [MentorActivity(mentor_id=1, month=date(2026, 5, 1), reviews_count=3)]

    note = activity_note(rows)

    assert "3 reviews" in note
    assert "picking up" not in note
    assert "slowing down" not in note


def test_a_quiet_period_is_described_as_quiet_rather_than_as_a_trend():
    rows = [
        MentorActivity(mentor_id=1, month=date(2026, index + 1, 1), reviews_count=0)
        for index in range(6)
    ]

    assert "no reviews" in activity_note(rows)


def test_a_direction_needs_more_than_a_fluctuation():
    """
    These are small counts. A sentence claiming a rise on the strength of one
    extra review would be a sentence about noise.
    """
    assert direction_of([4.0, 4.0, 4.0, 4.0, 4.0, 5.0]) == "about the same"
    assert direction_of([4.0]) == "about the same"
    assert TREND_MONTHS == 3


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------
def give_activity(sessions, mentor_id, rows):
    with sessions() as session:
        for month, reviews, share, price in rows:
            session.add(
                MentorActivity(
                    mentor_id=mentor_id,
                    month=month,
                    reviews_count=reviews,
                    booked_share=share,
                    price=price,
                )
            )
        session.commit()


@pytest.mark.app_assets
def test_a_mentor_reads_their_own_activity_as_parallel_arrays(client, api_sessions):
    from .conftest import register

    mentor_id = register(client)["mentor"]["id"]
    give_activity(
        api_sessions,
        mentor_id,
        [
            (date(2026, 5, 1), 2, 0.5, 200),
            (date(2026, 6, 1), 4, None, None),
        ],
    )

    body = client.get(f"/mentors/{mentor_id}/activity", headers=headers(mentor_id))

    assert body.status_code == 200
    payload = body.json()
    assert payload["has_history"] is True
    assert payload["months"] == ["2026-05-01", "2026-06-01"]
    assert payload["reviews_by_month"] == [2, 4]
    # A null rather than a zero: the platform has no record of how busy they
    # were in June, which is not the same as them not being busy.
    assert payload["booked_share_by_month"] == [0.5, None]
    assert payload["price_by_month"] == [200, None]
    assert payload["currency"] == "AUD"
    assert payload["note"]


@pytest.mark.app_assets
def test_every_array_is_the_same_length(client, api_sessions):
    from .conftest import register

    mentor_id = register(client)["mentor"]["id"]
    give_activity(
        api_sessions,
        mentor_id,
        [(date(2026, month, 1), month, None, None) for month in range(1, 7)],
    )

    payload = client.get(
        f"/mentors/{mentor_id}/activity", headers=headers(mentor_id)
    ).json()

    lengths = {
        len(payload[name])
        for name in (
            "months",
            "reviews_by_month",
            "booked_share_by_month",
            "price_by_month",
        )
    }
    assert lengths == {6}


@pytest.mark.app_assets
def test_a_new_mentor_has_no_activity_and_is_not_an_error(client):
    from .conftest import register

    mentor_id = register(client)["mentor"]["id"]

    payload = client.get(
        f"/mentors/{mentor_id}/activity", headers=headers(mentor_id)
    ).json()

    assert payload["has_history"] is False
    assert payload["months"] == []
    assert payload["reviews_by_month"] == []
    assert payload["note"]


@pytest.mark.app_assets
def test_another_mentors_activity_is_not_found(client, api_sessions):
    from .conftest import register

    first = register(client)["mentor"]["id"]
    second = register(client, email="other@example.com")["mentor"]["id"]
    give_activity(api_sessions, second, [(date(2026, 5, 1), 9, None, None)])

    response = client.get(f"/mentors/{second}/activity", headers=headers(first))

    assert response.status_code == 404


@pytest.mark.app_assets
def test_reading_activity_needs_an_identity(client):
    from .conftest import register

    mentor_id = register(client)["mentor"]["id"]

    assert client.get(f"/mentors/{mentor_id}/activity").status_code == 401


@pytest.mark.app_assets
def test_activity_names_nothing_from_the_source_dataset(client, api_sessions):
    from .conftest import register

    mentor_id = register(client)["mentor"]["id"]
    give_activity(api_sessions, mentor_id, [(date(2026, 5, 1), 3, 0.4, 300)])

    text = client.get(
        f"/mentors/{mentor_id}/activity", headers=headers(mentor_id)
    ).text.lower()

    for leaked in ("listing", "host", "night", "occ_", "calendar", "airbnb"):
        assert leaked not in text
