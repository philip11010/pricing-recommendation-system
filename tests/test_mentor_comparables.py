"""
Tests for the comparable mentors: the matching rules, and the endpoint.

The matching rules are tested against the small synthetic table in conftest
rather than the real one. A match level reached on six thousand real rows is a
fact about that dataset; the same level reached on twenty-nine rows written
out by hand is a fact about the rules, and the rules are what these tests are
about. One end-to-end check at the bottom runs against the real file and skips
when it has not been built.

The property that matters most here is the one the hard rules name: nothing in
a response identifies a source record. A mentor looking at who they are
compared with is looking at a distribution, not at other people's accounts.
That is checked on the response body, on the rendered JSON text, and on the
order the rows come back in, because an order that depended on the key would
leak it as surely as a field would.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.mentor import comparables as comparables_module
from src.mentor import mapping
from src.mentor.comparables import (
    MATCH_SAME_FIELD,
    MATCH_SAME_FIELD_AND_SIZE,
    MATCH_SAME_SIZE,
    MIN_MATCHES,
    ComparablesTable,
    ComparablesUnavailableError,
    load_comparables,
)

from .conftest import (
    SYNTHETIC_HISTORY,
    SYNTHETIC_PROFILE,
    headers,
    synthetic_comparables,
)
from .conftest import register as register_mentor
from .conftest import registration as registration_body


def registration(**overrides):
    """
    The shared registration body, with a group of two by default.

    A group rather than a one-to-one session, because the comparison this
    module is about is matched on group size and the synthetic table has
    twelve technology mentors around that size.
    """
    return registration_body(**{"max_mentees": 2, **overrides})


def register(client, **overrides):
    return register_mentor(client, **{"max_mentees": 2, **overrides})


@pytest.fixture
def table() -> ComparablesTable:
    return synthetic_comparables()


# ---------------------------------------------------------------------------
# Match levels
# ---------------------------------------------------------------------------
def test_a_well_represented_field_matches_on_field_and_group_size(table):
    """
    What a mentor actually asked for: mentors in my field running sessions
    about the size of mine.
    """
    found = table.match(field="technology_software", max_mentees=2)

    assert found.match_level == MATCH_SAME_FIELD_AND_SIZE
    assert found.count >= MIN_MATCHES
    assert found.widened is False
    assert set(found.rows["field"]) == {"technology_software"}
    assert found.rows["max_mentees"].between(1, 3).all()


def test_a_field_with_no_mentors_at_that_size_widens_to_the_whole_field(table):
    """
    Every engineering mentor in the table runs sessions of eight, so an
    engineering mentor running one-to-ones finds nobody at their own size and
    is compared with their field instead.
    """
    found = table.match(field="engineering", max_mentees=1)

    assert found.match_level == MATCH_SAME_FIELD
    assert found.count >= MIN_MATCHES
    assert found.widened is False
    assert set(found.rows["field"]) == {"engineering"}


def test_a_thin_field_widens_to_any_field_at_that_size(table):
    """
    Four law mentors is not a market. Rather than quote a median built on
    four, the match gives up on the field and keeps the group size, which is
    the weaker of the two claims to make.
    """
    found = table.match(field="law", max_mentees=1)

    assert found.match_level == MATCH_SAME_SIZE
    assert found.count >= MIN_MATCHES
    assert found.widened is False
    assert len(set(found.rows["field"])) > 1
    assert found.rows["max_mentees"].between(1, 2).all()


def test_the_levels_are_tried_in_order_and_the_first_sufficient_one_wins(table):
    """
    The narrowest match that clears the minimum, not the widest available.
    Engineering at eight clears it at level 0 by a single row, and that row is
    what keeps the comparison on the mentor's own field.
    """
    found = table.match(field="engineering", max_mentees=8)

    assert found.match_level == MATCH_SAME_FIELD_AND_SIZE
    assert found.count == MIN_MATCHES


def test_a_match_that_cannot_reach_the_minimum_says_it_widened(table):
    """
    Three mentors is the best answer available, and the response has to say
    that it is thin rather than present it as a market rate.
    """
    found = table.match(field="medicine_health", max_mentees=5)

    assert found.match_level == MATCH_SAME_SIZE
    assert found.count < MIN_MATCHES
    assert found.widened is True


def test_a_match_with_nobody_in_it_is_empty_rather_than_invented():
    """
    An empty table has no median, and reporting zero would read as mentors
    charging nothing.
    """
    rows = pd.DataFrame(
        [
            {
                "key": 1,
                "field": "law",
                "max_mentees": 8,
                "price": 500,
                "price_per_mentee": 63,
                "rating_overall": 4.5,
                "booked_share_365d": 0.5,
                "reviews_total": 20,
                **SYNTHETIC_PROFILE,
            }
        ]
    )
    found = ComparablesTable(rows).match(field="law", max_mentees=1)

    assert found.count == 0
    assert found.widened is True
    summary = comparables_module.summarise(found)
    assert summary["median_price"] is None
    assert summary["p25_price"] is None
    assert summary["p75_price"] is None
    assert comparables_module.histogram(found) == {"bin_edges": [], "counts": []}


# ---------------------------------------------------------------------------
# The mentor's own record
# ---------------------------------------------------------------------------
def test_a_mentors_own_record_is_left_out_of_their_comparison(table):
    """
    The reason the key exists. A mentor compared against themselves would be
    told their price is exactly typical, by a comparison they are a data point
    in.
    """
    everyone = table.match(field="technology_software", max_mentees=2)
    own_key = int(everyone.rows["key"].iloc[0])

    without = table.match(
        field="technology_software", max_mentees=2, exclude_key=own_key
    )

    assert without.count == everyone.count - 1
    assert own_key not in set(without.rows["key"])


def test_excluding_a_mentors_own_record_can_widen_the_match(table):
    """
    Engineering at eight clears the minimum by one row. If that row is the
    mentor's own, it cannot count, and the match has to widen rather than
    quote a median over nine.
    """
    included = table.match(field="engineering", max_mentees=8)
    own_key = int(included.rows["key"].iloc[0])

    without = table.match(field="engineering", max_mentees=8, exclude_key=own_key)

    assert included.match_level == MATCH_SAME_FIELD_AND_SIZE
    assert without.match_level != MATCH_SAME_FIELD_AND_SIZE
    assert own_key not in set(without.rows["key"])


def test_a_key_that_is_in_no_match_changes_nothing(table):
    """
    A mentor who registered has no source record, so there is nothing to
    exclude and the comparison is the same either way.
    """
    everyone = table.match(field="technology_software", max_mentees=2)
    unknown = table.match(
        field="technology_software", max_mentees=2, exclude_key=999_999
    )

    assert unknown.count == everyone.count


# ---------------------------------------------------------------------------
# What the summary says
# ---------------------------------------------------------------------------
def test_the_summary_reports_quantiles_rather_than_a_mean(table):
    found = table.match(field="technology_software", max_mentees=2)
    summary = comparables_module.summarise(found)

    prices = sorted(found.rows["price"])
    assert summary["count"] == len(prices)
    assert summary["p25_price"] <= summary["median_price"] <= summary["p75_price"]
    assert summary["median_price"] >= prices[0]
    assert summary["median_price"] <= prices[-1]
    assert summary["currency"] == "AUD"


def test_the_match_description_is_written_in_mentor_language(table):
    found = table.match(field="technology_software", max_mentees=4)

    assert found.description == "Technology and software mentors, any group size"
    for leaked in ("neighbourhood", "accommodates", "room_type", "listing", "host"):
        assert leaked not in found.description.lower()


@pytest.mark.parametrize(
    ("match_level", "expected"),
    [
        (
            MATCH_SAME_FIELD_AND_SIZE,
            "Technology and software mentors with 3 to 5 mentees per session",
        ),
        (MATCH_SAME_FIELD, "Technology and software mentors, any group size"),
        (MATCH_SAME_SIZE, "Mentors in any field with 3 to 5 mentees per session"),
    ],
)
def test_each_level_describes_itself(match_level, expected):
    assert (
        comparables_module.describe_match(match_level, "technology_software", 4)
        == expected
    )


@pytest.mark.parametrize(
    ("max_mentees", "window"),
    [(1, (1, 2)), (2, (1, 3)), (4, (3, 5)), (8, (7, 8))],
)
def test_the_group_size_window_stays_inside_the_range_the_form_offers(
    max_mentees, window
):
    assert comparables_module.group_size_window(max_mentees) == window


def test_the_histogram_covers_the_matched_prices_in_twelve_bins(table):
    found = table.match(field="technology_software", max_mentees=2)

    drawn = comparables_module.histogram(found)

    assert len(drawn["counts"]) == comparables_module.HISTOGRAM_BINS
    assert len(drawn["bin_edges"]) == comparables_module.HISTOGRAM_BINS + 1
    assert sum(drawn["counts"]) == found.count
    assert drawn["bin_edges"] == sorted(drawn["bin_edges"])
    assert drawn["bin_edges"][0] == float(found.rows["price"].min())
    assert drawn["bin_edges"][-1] == float(found.rows["price"].max())


def test_a_single_price_is_one_bin_rather_than_an_invented_spread():
    """
    numpy would widen a single value by half a unit either side, which draws a
    spread that is not there.
    """
    rows = pd.DataFrame(
        [
            {
                "key": index,
                "field": "law",
                "max_mentees": 2,
                "price": 500,
                "price_per_mentee": 250,
                "rating_overall": 4.5,
                "booked_share_365d": 0.5,
                "reviews_total": 20,
                **SYNTHETIC_PROFILE,
            }
            for index in range(3)
        ]
    )
    found = ComparablesTable(rows).match(field="law", max_mentees=2)

    assert comparables_module.histogram(found) == {
        "bin_edges": [500.0, 500.0],
        "counts": [3],
    }


@pytest.mark.parametrize(
    ("price", "expected"), [(100, 25.0), (200, 50.0), (400, 100.0), (50, 0.0)]
)
def test_a_percentile_is_the_share_of_mentors_charging_that_much_or_less(
    price, expected
):
    rows = pd.DataFrame(
        [
            {
                "key": index,
                "field": "law",
                "max_mentees": 2,
                "price": value,
                "price_per_mentee": value // 2,
                "rating_overall": 4.5,
                "booked_share_365d": 0.5,
                "reviews_total": 20,
                **SYNTHETIC_PROFILE,
            }
            for index, value in enumerate([100, 200, 300, 400])
        ]
    )
    found = ComparablesTable(rows).match(field="law", max_mentees=2)

    assert comparables_module.price_percentile(found, price) == expected


def test_a_percentile_without_a_price_or_without_mentors_is_null(table):
    found = table.match(field="technology_software", max_mentees=2)
    empty = table.match(field="community_social_work", max_mentees=1)

    assert comparables_module.price_percentile(found, None) is None
    assert comparables_module.price_percentile(found, 0) is None
    assert comparables_module.price_percentile(empty, 300) == (
        None if empty.count == 0 else pytest.approx(0.0, abs=100)
    )


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("sort", ["price", "rating"])
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_the_mentors_come_back_in_the_order_asked_for(table, sort, order):
    found = table.match(field="technology_software", max_mentees=2)

    ordered = comparables_module.sorted_items(found, sort, order)

    column = comparables_module.SORT_COLUMNS[sort]
    values = list(ordered[column])
    assert values == sorted(values, reverse=order == "desc")


def test_the_order_does_not_depend_on_the_key(table):
    """
    An order settled by the key would leak it: the same rows in the same
    sequence are the key's sequence, whether or not the column is returned.
    """
    found = table.match(field="engineering", max_mentees=8)
    shuffled = ComparablesTable(found.rows.iloc[::-1].reset_index(drop=True)).match(
        field="engineering", max_mentees=8
    )

    one = comparables_module.sorted_items(found, "price", "asc")
    other = comparables_module.sorted_items(shuffled, "price", "asc")

    assert list(one["price"]) == list(other["price"])


@pytest.mark.parametrize("sort", ["cheapest", "", "key", "reviews_total"])
def test_an_unknown_sort_is_refused_in_mentor_language(sort):
    with pytest.raises(mapping.MentorInputError) as error:
        comparables_module.validate_sort(sort)

    assert error.value.field == "sort"
    assert "price" in error.value.message


@pytest.mark.parametrize("order", ["ascending", "up", ""])
def test_an_unknown_order_is_refused(order):
    with pytest.raises(mapping.MentorInputError) as error:
        comparables_module.validate_order(order)

    assert error.value.field == "order"


# ---------------------------------------------------------------------------
# One mentor, as the frontend is given them
# ---------------------------------------------------------------------------
def test_one_comparable_mentor_carries_no_identifier(table):
    found = table.match(field="technology_software", max_mentees=2)

    item = comparables_module.as_item(found.rows.iloc[0])

    assert "key" not in item
    assert not any("id" == name or name.endswith("_id") for name in item)
    assert set(item) == {
        "field_label",
        "session_label",
        "max_mentees",
        "price",
        "price_per_mentee",
        "rating_overall",
        "booked_share_percent",
        "reviews_total",
    }


def test_one_comparable_mentor_reads_in_mentor_language(table):
    found = table.match(field="technology_software", max_mentees=1)
    item = comparables_module.as_item(
        found.rows[found.rows["max_mentees"] == 1].iloc[0]
    )

    assert item["field_label"] == "Technology and software"
    assert item["session_label"] == "One to one"
    assert 0 <= item["booked_share_percent"] <= 100


def test_a_group_session_is_labelled_a_group(table):
    found = table.match(field="engineering", max_mentees=8)

    item = comparables_module.as_item(found.rows.iloc[0])

    assert item["session_label"] == "Group"
    assert item["max_mentees"] == 8


# ---------------------------------------------------------------------------
# Loading the file
# ---------------------------------------------------------------------------
def test_a_missing_file_names_the_script_that_builds_it(tmp_path):
    with pytest.raises(ComparablesUnavailableError) as error:
        load_comparables(tmp_path)

    assert "build_comparables" in str(error.value)


def test_an_empty_file_is_refused_rather_than_served(tmp_path):
    (tmp_path / "comparables.parquet").write_bytes(b"")

    with pytest.raises(ComparablesUnavailableError):
        load_comparables(tmp_path)


def test_a_table_missing_a_column_is_refused_with_its_name():
    rows = pd.DataFrame([{"key": 1, "field": "law", "max_mentees": 2, "price": 500}])

    with pytest.raises(ComparablesUnavailableError) as error:
        ComparablesTable(rows)

    assert "rating_overall" in str(error.value)


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------
pytestmark_assets = pytest.mark.app_assets


@pytest.mark.app_assets
def test_a_service_can_be_compared_with_mentors_like_it(client):
    body = register(client)
    mentor_id = body["mentor"]["id"]

    response = client.get(
        f"/services/{body['service']['id']}/comparables", headers=headers(mentor_id)
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"]["count"] >= MIN_MATCHES
    assert payload["summary"]["match_level"] == MATCH_SAME_FIELD_AND_SIZE
    assert payload["summary"]["widened"] is False
    assert payload["items"]
    assert len(payload["histogram"]["counts"]) == comparables_module.HISTOGRAM_BINS


@pytest.mark.app_assets
def test_the_comparables_response_carries_no_ids(client):
    """
    The hard rule, checked on the rendered text rather than on the parsed
    body, so a key nested anywhere in the payload would still be caught.
    """
    body = register(client)
    mentor_id = body["mentor"]["id"]

    response = client.get(
        f"/services/{body['service']['id']}/comparables", headers=headers(mentor_id)
    )

    text = response.text.lower()
    assert '"key"' not in text
    assert "host_id" not in text
    assert "listing" not in text
    for item in response.json()["items"]:
        assert not any(name.endswith("id") for name in item)


@pytest.mark.app_assets
def test_a_new_mentor_and_an_established_one_are_compared_the_same_way(
    client, api_sessions
):
    """
    The comparison is drawn from the field and the group size, which both of
    them have, so a track record changes the price and not who it is measured
    against.
    """
    first = register(client)
    second = register(client, email="other@example.com")
    with api_sessions() as session:
        from src.db.mentor_models import MentorHistory

        session.add(
            MentorHistory(mentor_id=second["mentor"]["id"], **SYNTHETIC_HISTORY)
        )
        session.commit()

    new = client.get(
        f"/services/{first['service']['id']}/comparables",
        headers=headers(first["mentor"]["id"]),
    ).json()
    established = client.get(
        f"/services/{second['service']['id']}/comparables",
        headers=headers(second["mentor"]["id"]),
    ).json()

    assert new["summary"] == established["summary"]


@pytest.mark.app_assets
@pytest.mark.parametrize(
    ("field", "max_mentees", "expected_level"),
    [
        ("technology_software", 2, MATCH_SAME_FIELD_AND_SIZE),
        ("engineering", 1, MATCH_SAME_FIELD),
        ("law", 1, MATCH_SAME_SIZE),
    ],
)
def test_each_match_level_is_reachable_over_http(
    client, field, max_mentees, expected_level
):
    body = register(client, field=field, max_mentees=max_mentees)
    mentor_id = body["mentor"]["id"]

    payload = client.get(
        f"/services/{body['service']['id']}/comparables", headers=headers(mentor_id)
    ).json()

    assert payload["summary"]["match_level"] == expected_level


@pytest.mark.app_assets
def test_a_thin_match_is_reported_as_widened_over_http(client):
    body = register(client, field="medicine_health", max_mentees=5)
    mentor_id = body["mentor"]["id"]

    summary = client.get(
        f"/services/{body['service']['id']}/comparables", headers=headers(mentor_id)
    ).json()["summary"]

    assert summary["widened"] is True
    assert summary["count"] < MIN_MATCHES


@pytest.mark.app_assets
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_the_endpoint_sorts_as_asked(client, order):
    body = register(client)
    mentor_id = body["mentor"]["id"]

    items = client.get(
        f"/services/{body['service']['id']}/comparables"
        f"?sort=price&order={order}&limit=50",
        headers=headers(mentor_id),
    ).json()["items"]

    prices = [item["price"] for item in items]
    assert prices == sorted(prices, reverse=order == "desc")


@pytest.mark.app_assets
def test_the_endpoint_sorts_by_rating_as_well(client):
    body = register(client)
    mentor_id = body["mentor"]["id"]

    items = client.get(
        f"/services/{body['service']['id']}/comparables?sort=rating&order=desc",
        headers=headers(mentor_id),
    ).json()["items"]

    ratings = [item["rating_overall"] for item in items]
    assert ratings == sorted(ratings, reverse=True)


@pytest.mark.app_assets
def test_paging_moves_through_the_mentors_without_changing_the_summary(client):
    """
    The summary and the histogram describe the whole match, so the figures a
    mentor reads stay put while they scroll.
    """
    body = register(client)
    mentor_id = body["mentor"]["id"]
    path = f"/services/{body['service']['id']}/comparables?sort=price&order=asc"

    first = client.get(f"{path}&limit=4&offset=0", headers=headers(mentor_id)).json()
    second = client.get(f"{path}&limit=4&offset=4", headers=headers(mentor_id)).json()

    assert first["summary"] == second["summary"]
    assert first["histogram"] == second["histogram"]
    assert len(first["items"]) == 4
    assert first["items"] != second["items"]
    assert first["offset"] == 0 and second["offset"] == 4


@pytest.mark.app_assets
def test_an_offset_past_the_end_returns_no_mentors_rather_than_failing(client):
    body = register(client)
    mentor_id = body["mentor"]["id"]

    payload = client.get(
        f"/services/{body['service']['id']}/comparables?offset=10000",
        headers=headers(mentor_id),
    ).json()

    assert payload["items"] == []
    assert payload["summary"]["count"] > 0


@pytest.mark.app_assets
@pytest.mark.parametrize(
    "query", ["sort=cheapest", "order=sideways", "limit=0", "limit=10000", "offset=-1"]
)
def test_an_invalid_query_is_refused(client, query):
    body = register(client)
    mentor_id = body["mentor"]["id"]

    response = client.get(
        f"/services/{body['service']['id']}/comparables?{query}",
        headers=headers(mentor_id),
    )

    assert response.status_code == 422


@pytest.mark.app_assets
def test_another_mentors_service_cannot_be_compared(client):
    first = register(client)
    second = register(client, email="other@example.com")

    response = client.get(
        f"/services/{second['service']['id']}/comparables",
        headers=headers(first["mentor"]["id"]),
    )

    assert response.status_code == 404


@pytest.mark.app_assets
def test_comparing_needs_an_identity(client):
    body = register(client)

    response = client.get(f"/services/{body['service']['id']}/comparables")

    assert response.status_code == 401


@pytest.mark.app_assets
def test_a_server_without_the_table_says_what_to_build(comparableless_client):
    """
    The table is a separate build output from the models, so a server can
    price everything and still not have it. That has to be its own message.
    """
    body = register(comparableless_client)
    mentor_id = body["mentor"]["id"]

    response = comparableless_client.get(
        f"/services/{body['service']['id']}/comparables", headers=headers(mentor_id)
    )

    assert response.status_code == 503
    assert "build_comparables" in response.json()["detail"]
    for leaked in ("listing", "airbnb", "host"):
        assert leaked not in response.json()["detail"].lower()


@pytest.mark.app_assets
def test_health_reports_the_table_when_it_is_there(client):
    body = client.get("/health").json()

    assert body["models_loaded"] is True
    assert body["comparables_loaded"] is True
    assert body["detail"] is None


# Not combined with the test above, and the two cannot be: both fixtures wrap
# the one application object and set its state, so asking for both in one test
# would leave only whichever was built last.
@pytest.mark.app_assets
def test_health_reports_the_table_separately_from_the_models(comparableless_client):
    """
    A server can price every service and still have no comparison table. The
    two are separate build outputs, so health says which one is missing.
    """
    body = comparableless_client.get("/health").json()

    assert body["models_loaded"] is True
    assert body["comparables_loaded"] is False
    assert "build_comparables" in body["detail"]


# ---------------------------------------------------------------------------
# Against the real file
# ---------------------------------------------------------------------------
@pytest.mark.app_assets
def test_the_built_table_has_exactly_the_columns_the_application_reads(
    real_comparables,
):
    assert list(real_comparables.rows.columns) == list(
        comparables_module.COMPARABLES_COLUMNS
    )
    assert real_comparables.count > 0


@pytest.mark.app_assets
def test_the_built_table_holds_no_identifier_but_the_opaque_key(real_comparables):
    """
    Eight columns, seven of which are quantities a mentor would recognise
    about themselves. Nothing that could be joined back to a source record
    without the dataset, which is git-ignored and never published.
    """
    names = set(real_comparables.rows.columns)

    assert names == set(comparables_module.COMPARABLES_COLUMNS)
    assert not {name for name in names if name.endswith("_id") or name == "id"}
    for leaked in ("host", "listing", "neighbourhood", "room", "night"):
        assert not any(leaked in name for name in names)


@pytest.mark.app_assets
def test_every_field_in_the_built_table_is_one_a_mentor_can_choose(
    real_comparables,
):
    assert set(real_comparables.rows["field"]) <= set(mapping.FIELDS)


@pytest.mark.app_assets
def test_the_built_table_stays_inside_the_range_the_models_support(
    real_comparables, pricing
):
    rows = real_comparables.rows

    assert rows["price"].min() >= pricing.price_floor
    assert rows["price"].max() <= pricing.price_ceiling
    assert (
        rows["max_mentees"]
        .between(mapping.MAX_MENTEES_MIN, mapping.MAX_MENTEES_MAX)
        .all()
    )
    assert rows["rating_overall"].between(0, mapping.RATING_MAX).all()
    assert rows["booked_share_365d"].between(0, 1).all()
    assert (rows["reviews_total"] >= 5).all()


@pytest.mark.app_assets
def test_a_real_match_is_summarised_and_binned(real_comparables):
    """
    The bins cover every mentor the chart is drawn from, and no others.

    This used to assert the bins covered the whole match. They cover the
    spread now, which is the set the summary beside them is also read from:
    the point of the change was that one screen stopped describing two
    different populations at once.
    """
    found = real_comparables.match(field="technology_software", max_mentees=2)
    summary = comparables_module.summarise(found)
    drawn = comparables_module.spread(found)

    assert found.count >= MIN_MATCHES
    assert summary["p25_price"] <= summary["median_price"] <= summary["p75_price"]
    assert sum(comparables_module.histogram(found)["counts"]) == len(drawn)


# ---------------------------------------------------------------------------
# One screen, one set of mentors
#
# The fault these exist for: the frontend drew its points from a page of a
# cheapest-first sort and its band from the whole match, so the points showed
# the bottom of the market, the band showed the middle of it, and the mentor's
# own price sat far to the right of every point. Both now come out of
# comparables.spread, and these are the tests that keep them there.
# ---------------------------------------------------------------------------
@pytest.mark.app_assets
def test_the_band_is_the_quartiles_of_the_mentors_actually_drawn(real_comparables):
    """
    The band edges are the quartiles of the point values, to the unit.

    Not approximately, and not of some other set of mentors: the same
    function reduces the match once and both figures are read off the result.
    """
    for field, mentees in (
        ("technology_software", 2),
        ("investment_finance", 4),
        ("community_social_work", 6),
    ):
        found = real_comparables.match(field=field, max_mentees=mentees)
        summary = comparables_module.summarise(found)
        drawn = [
            item["price"] for item in comparables_module.distribution(found)["items"]
        ]

        assert summary["p25_price"] == int(round(float(np.percentile(drawn, 25))))
        assert summary["median_price"] == int(round(float(np.percentile(drawn, 50))))
        assert summary["p75_price"] == int(round(float(np.percentile(drawn, 75))))


@pytest.mark.app_assets
def test_the_drawn_mentors_span_the_whole_match(real_comparables):
    """
    The cheapest and the dearest are kept, so the sample is not a trimmed
    market. A mentor at the top of their field has to be able to see that the
    chart reaches them.
    """
    found = real_comparables.match(field="technology_software", max_mentees=2)
    drawn = [item["price"] for item in comparables_module.distribution(found)["items"]]
    every = found.rows["price"].astype(int).tolist()

    assert min(drawn) == min(every)
    assert max(drawn) == max(every)


@pytest.mark.app_assets
def test_a_large_match_is_reported_as_sampled_and_says_how_many(real_comparables):
    found = real_comparables.match(field="technology_software", max_mentees=2)
    drawn = comparables_module.distribution(found)

    assert found.count > comparables_module.SPREAD_POINTS
    assert drawn["total"] == found.count
    assert drawn["shown"] == comparables_module.SPREAD_POINTS
    assert drawn["sampled"] is True
    assert len(drawn["items"]) == drawn["shown"]


def test_a_small_match_is_described_whole(comparables):
    """
    Nothing is sampled away from a thinly represented field: the sample is
    the match, and the frontend is told so, so it does not write a sentence
    about a spread that was never taken.
    """
    found = comparables.match(field="technology_software", max_mentees=4)
    drawn = comparables_module.distribution(found)

    assert found.count <= comparables_module.SPREAD_POINTS
    assert drawn["sampled"] is False
    assert drawn["shown"] == found.count
    assert drawn["total"] == found.count


def test_every_drawn_mentor_carries_the_session_price_and_the_seat_price(
    comparables,
):
    """
    One unit everywhere, with the per-seat figure beside it rather than
    instead of it. The price a mentor is compared on is what the session
    costs, because that is what they charge.
    """
    found = comparables.match(field="technology_software", max_mentees=4)

    for item in comparables_module.distribution(found)["items"]:
        assert item["price"] > 0
        assert item["price_per_mentee"] == round(item["price"] / item["max_mentees"])


@pytest.mark.app_assets
def test_a_mentors_own_price_lands_among_the_mentors_drawn_beside_it(
    real_comparables, pricing
):
    """
    The symptom the fault was reported as, stated as a test.

    A suggested price for a group of two, against the mentors a group of two
    is compared with. It has to land on the same scale as the points: inside
    their range, or at worst close to one end of it. Before the fix the
    points were the cheapest sixty of a thousand and a perfectly ordinary
    suggestion sat a hundred units to the right of all of them.
    """
    inputs = mapping.to_model_inputs(
        field="technology_software",
        max_mentees=2,
        min_commitment=mapping.MIN_COMMITMENT_DEFAULT,
        skills=list(mapping.SKILLS)[:6],
        profile_verified=False,
        services_count=1,
    )
    suggested = pricing.predict(inputs).recommended_price

    found = real_comparables.match(field="technology_software", max_mentees=2)
    drawn = [item["price"] for item in comparables_module.distribution(found)["items"]]
    summary = comparables_module.summarise(found)

    assert min(drawn) <= suggested <= max(drawn)
    # And not merely inside a very wide range. The suggestion sits in the
    # body of the market rather than out in either tail, which is the claim
    # the mentor is actually being shown.
    assert 5 <= comparables_module.price_percentile(found, suggested) <= 95
    assert summary["p25_price"] <= suggested <= max(drawn)


@pytest.mark.app_assets
def test_where_a_price_sits_is_measured_against_the_mentors_drawn(real_comparables):
    """
    The percentile and the band answer the same question about the same
    mentors, so a price on the lower quartile reads as about a quarter of the
    way up rather than as some unrelated number.
    """
    found = real_comparables.match(field="technology_software", max_mentees=2)
    summary = comparables_module.summarise(found)

    at_quarter = comparables_module.price_percentile(found, summary["p25_price"])
    at_three_quarters = comparables_module.price_percentile(found, summary["p75_price"])

    assert 20 <= at_quarter <= 30
    assert 70 <= at_three_quarters <= 80
