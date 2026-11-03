"""
Tests for the mapping layer.

The mapping layer is the one place a mentor's answers become model inputs, so
these tests are the contract for that translation: every option a mentor can
pick maps to a known model value, and every answer a mentor cannot pick is
refused with a message written for them.

The expected model values are spelled out here rather than imported from the
mapping module. Importing them would make the test pass for any mapping at
all, including one that quietly changes which market segment a field is priced
against, which would move prices without anything failing.
"""

from __future__ import annotations

import pytest

from src.mentor import mapping
from src.mentor.mapping import MentorInputError

# The one value the session format column is held at. Spelled out rather
# than imported, so a change to it has to be made here as well and cannot
# move every price in the system silently.
EXPECTED_SESSION_FORMAT = "Entire home/apt"

# What a new mentor's tenure is fixed at. Also spelled out: this is the
# number that replaced the experience band, and it is the whole of change 2.
EXPECTED_NEW_MENTOR_TENURE = 0.5

EXPECTED_FIELDS = {
    "executive_leadership": "Pittwater",
    "management_consulting": "Manly",
    "law": "Woollahra",
    "investment_finance": "Waverley",
    "banking_accounting": "North Sydney",
    "medicine_health": "Randwick",
    "engineering": "Sutherland Shire",
    "technology_software": "Sydney",
    "marketing_communications": "Ryde",
    "creative_arts_design": "Leichhardt",
    "education_teaching": "Hornsby",
    "community_social_work": "Blacktown",
}

EXPECTED_BANDS = (
    "under_1",
    "1_to_2",
    "3_to_5",
    "6_to_10",
    "over_10",
)

VALID_ANSWERS = {
    "field": "technology_software",
    "max_mentees": 1,
    "min_commitment": 1,
    "skills": ["cv_review", "interview_preparation"],
    "profile_verified": True,
    "services_planned": 1,
    "services_count": 1,
}


def answers(**overrides):
    return {**VALID_ANSWERS, **overrides}


# ---------------------------------------------------------------------------
# Option coverage
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mentees", [1, 2, 8])
def test_the_session_format_is_held_at_one_value_whatever_the_group_size(mentees):
    """
    The format is no longer asked, and no answer may move it.

    It is held at the value the training data supports well. The other value
    was thin enough that prices built on it did not rise with the size of the
    group, which is the problem this replaced.
    """
    inputs = mapping.to_model_inputs(**answers(max_mentees=mentees))
    assert inputs[mapping.COLUMN_SESSION_FORMAT] == EXPECTED_SESSION_FORMAT


def test_the_mapping_takes_no_session_format_answer():
    """Not merely ignored: there is no parameter to pass it in."""
    with pytest.raises(TypeError):
        mapping.to_model_inputs(**answers(service_type="one_to_one"))


@pytest.mark.parametrize(("option", "expected"), EXPECTED_FIELDS.items())
def test_every_field_maps_to_its_model_value(option, expected):
    inputs = mapping.to_model_inputs(**answers(field=option))
    assert inputs[mapping.COLUMN_FIELD] == expected


def test_there_are_twelve_fields_and_no_others():
    assert set(mapping.FIELDS) == set(EXPECTED_FIELDS)
    assert len(mapping.FIELDS) == 12


def test_each_field_gets_its_own_market_segment():
    """
    Two fields sharing a segment would be priced identically, which is the one
    thing the twelve-way split exists to avoid.
    """
    values = [spec["column_value"] for spec in mapping.FIELDS.values()]
    assert len(set(values)) == len(values)


def test_a_new_mentor_is_given_the_fixed_tenure():
    """
    A new mentor has no time on the platform, whatever their career length,
    so the tenure column is a constant on this path.
    """
    inputs = mapping.to_model_inputs(**answers())

    assert mapping.NEW_MENTOR_TENURE_YEARS == pytest.approx(EXPECTED_NEW_MENTOR_TENURE)
    assert inputs[mapping.COLUMN_TENURE] == pytest.approx(EXPECTED_NEW_MENTOR_TENURE)


def test_the_mapping_takes_no_experience_answer():
    """
    The experience band is profile text now. There is no parameter for it, so
    it cannot reach the model by being passed to the wrong place.
    """
    with pytest.raises(TypeError):
        mapping.to_model_inputs(**answers(years_mentoring_band="over_10"))


@pytest.mark.parametrize("band", EXPECTED_BANDS)
def test_no_experience_band_carries_a_model_value(band):
    """
    The bands are labels and nothing else.

    They used to carry a tenure value each. Keeping one would leave a way for
    the answer to reach the model again, so the test is that there is no
    value to find.
    """
    assert isinstance(mapping.YEARS_MENTORING_BANDS[band], str)
    assert mapping.validate_years_mentoring(band) == band


def test_the_experience_bands_are_exactly_the_five_offered():
    assert tuple(mapping.YEARS_MENTORING_BANDS) == EXPECTED_BANDS


@pytest.mark.parametrize("option", mapping.MIN_COMMITMENT_OPTIONS)
def test_every_commitment_option_passes_through_unchanged(option):
    inputs = mapping.to_model_inputs(**answers(min_commitment=option))
    assert inputs[mapping.COLUMN_MIN_COMMITMENT] == option


@pytest.mark.parametrize("mentees", range(1, 9))
def test_every_group_size_passes_through_unchanged(mentees):
    inputs = mapping.to_model_inputs(**answers(max_mentees=mentees))
    assert inputs[mapping.COLUMN_MAX_MENTEES] == mentees


@pytest.mark.parametrize(
    ("mentees", "expected"),
    [
        (1, "one_to_one"),
        (2, "group"),
        (3, "group"),
        (8, "group"),
    ],
)
def test_the_session_label_follows_from_the_group_size(mentees, expected):
    assert mapping.session_label(mentees) == expected


def test_the_session_label_is_not_a_model_input():
    """
    It is a name for the mentor, derived from an answer the model already
    has. Feeding it as well would say the same thing twice.
    """
    inputs = mapping.to_model_inputs(**answers(max_mentees=4))

    assert "group" not in inputs.values()
    assert "one_to_one" not in inputs.values()


def test_a_group_size_the_form_rejects_has_no_label():
    with pytest.raises(MentorInputError) as error:
        mapping.session_label(0)
    assert error.value.field == "max_mentees"


def test_the_group_size_can_be_read_back_from_stored_inputs():
    """
    What each mentee pays is the session price divided by the seats, and that
    has to be recoverable from a stored price months later.
    """
    inputs = mapping.to_model_inputs(**answers(max_mentees=6))

    assert mapping.max_mentees_from_inputs(inputs) == 6


def test_stored_inputs_without_a_group_size_are_refused_in_mentor_language():
    with pytest.raises(MentorInputError) as error:
        mapping.max_mentees_from_inputs({})
    assert error.value.field == "max_mentees"
    assert "mentees" in error.value.message


@pytest.mark.parametrize("verified", [True, False])
def test_verification_maps_to_one_or_zero(verified):
    inputs = mapping.to_model_inputs(**answers(profile_verified=verified))
    assert inputs[mapping.COLUMN_VERIFIED] == int(verified)


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------
def test_there_are_exactly_thirty_skills():
    assert len(mapping.SKILLS) == 30
    assert len(set(mapping.SKILLS)) == 30


def test_every_skill_id_is_snake_case():
    assert all(
        skill == skill.lower() and " " not in skill and "-" not in skill
        for skill in mapping.SKILLS
    )


@pytest.mark.parametrize("count", [0, 1, 2, 5, 30])
def test_the_skill_count_is_doubled(count):
    chosen = list(mapping.SKILLS)[:count]
    inputs = mapping.to_model_inputs(**answers(skills=chosen))
    assert inputs[mapping.COLUMN_SKILLS] == count * 2


def test_every_skill_id_is_accepted():
    inputs = mapping.to_model_inputs(**answers(skills=list(mapping.SKILLS)))
    assert inputs[mapping.COLUMN_SKILLS] == 60


def test_a_skill_outside_the_list_is_refused():
    with pytest.raises(MentorInputError) as error:
        mapping.to_model_inputs(**answers(skills=["cv_review", "juggling"]))
    assert error.value.field == "skills"
    assert "juggling" in error.value.message


def test_the_same_skill_twice_is_refused():
    with pytest.raises(MentorInputError) as error:
        mapping.to_model_inputs(**answers(skills=["cv_review", "cv_review"]))
    assert "only be chosen once" in error.value.message


def test_a_bare_string_is_not_a_list_of_skills():
    with pytest.raises(MentorInputError):
        mapping.to_model_inputs(**answers(skills="cv_review"))


# ---------------------------------------------------------------------------
# Service count
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("count", "planned", "expected"),
    [
        (0, 1, 1),
        (1, 1, 1),
        (1, 3, 3),
        (3, 1, 3),
        (2, 2, 2),
        (4, 4, 4),
        # Above the cap on either side, and on both.
        (9, 1, 4),
        (1, 4, 4),
        (12, 4, 4),
    ],
)
def test_the_service_count_is_the_larger_of_the_two_capped_at_four(
    count, planned, expected
):
    inputs = mapping.to_model_inputs(
        **answers(services_count=count, services_planned=planned)
    )
    assert inputs[mapping.COLUMN_SERVICES] == expected


def test_the_service_count_never_exceeds_the_cap():
    assert mapping.effective_services(500, 4) == mapping.SERVICES_CAP


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("override", "expected_field"),
    [
        ({"field": "astrophysics"}, "field"),
        ({"field": ""}, "field"),
        ({"max_mentees": 0}, "max_mentees"),
        ({"max_mentees": 17}, "max_mentees"),
        ({"max_mentees": "two"}, "max_mentees"),
        ({"max_mentees": 2.5}, "max_mentees"),
        # True is an int equal to 1 in Python, so a checkbox posted into a
        # numeric answer has to be refused explicitly.
        ({"max_mentees": True}, "max_mentees"),
        ({"min_commitment": 4}, "min_commitment"),
        ({"min_commitment": 0}, "min_commitment"),
        ({"min_commitment": 100}, "min_commitment"),
        ({"profile_verified": "yes"}, "profile_verified"),
        ({"profile_verified": 1}, "profile_verified"),
        ({"services_planned": 0}, "services_planned"),
        ({"services_planned": 5}, "services_planned"),
        ({"services_count": -1}, "services_count"),
    ],
)
def test_an_answer_outside_the_options_is_refused(override, expected_field):
    with pytest.raises(MentorInputError) as error:
        mapping.to_model_inputs(**answers(**override))
    assert error.value.field == expected_field
    assert error.value.message


@pytest.mark.parametrize("mentees", [0, 9, 16])
def test_a_group_size_outside_the_range_is_refused_in_mentor_language(mentees):
    """
    The two ends a mentor is most likely to type. The message has to name the
    range in the words the form uses.
    """
    with pytest.raises(MentorInputError) as error:
        mapping.to_model_inputs(**answers(max_mentees=mentees))

    assert error.value.field == "max_mentees"
    message = error.value.message.lower()
    assert "mentees" in message
    assert "1" in message and "8" in message


@pytest.mark.parametrize("band", EXPECTED_BANDS)
def test_the_experience_band_does_not_change_a_single_model_input(band):
    """
    Change 2, stated as directly as it can be: whatever the mentor answers
    about their experience, the row the model is given is the same row.
    """
    baseline = mapping.to_model_inputs(**answers())

    assert mapping.validate_years_mentoring(band) == band
    assert mapping.to_model_inputs(**answers()) == baseline


def test_a_refusal_is_written_for_the_mentor():
    """
    The message a mentor reads must not name a model column or a dataset term.

    This is the one test guarding the vocabulary boundary from the inside: the
    whole point of the mapping layer is that nothing outside it sees those
    words.
    """
    with pytest.raises(MentorInputError) as error:
        mapping.to_model_inputs(**answers(max_mentees=99))
    message = error.value.message.lower()
    assert "mentees" in message
    for leaked in ("accommodates", "room_type", "neighbourhood", "host", "night"):
        assert leaked not in message


# ---------------------------------------------------------------------------
# Model columns
# ---------------------------------------------------------------------------
def test_the_core_mapping_produces_eight_columns():
    inputs = mapping.to_model_inputs(**answers())
    assert len(inputs) == 8
    assert set(inputs) == set(mapping.CORE_COLUMNS)


def test_the_track_record_mapping_produces_twenty_eight_columns():
    history = dict.fromkeys(mapping.HISTORY_FIELDS, 0)
    columns = mapping.history_to_model_inputs(history)
    assert len(columns) == 28
    assert set(columns) == set(mapping.HISTORY_COLUMNS)


def test_the_full_column_set_is_the_core_set_plus_the_track_record():
    assert len(mapping.FULL_COLUMNS) == 36
    assert mapping.FULL_COLUMNS[:8] == mapping.CORE_COLUMNS


def test_an_incomplete_track_record_is_refused_by_name():
    history = dict.fromkeys(mapping.HISTORY_FIELDS, 0)
    del history["rating_overall"]
    with pytest.raises(MentorInputError) as error:
        mapping.history_to_model_inputs(history)
    assert "rating_overall" in error.value.message


def test_an_unknown_track_record_entry_is_refused():
    history = dict.fromkeys(mapping.HISTORY_FIELDS, 0)
    history["favourite_colour"] = "blue"
    with pytest.raises(MentorInputError) as error:
        mapping.history_to_model_inputs(history)
    assert "favourite_colour" in error.value.message


# ---------------------------------------------------------------------------
# Form options
# ---------------------------------------------------------------------------
def test_the_form_options_cover_every_choice_on_the_form():
    options = mapping.get_form_options()
    assert set(options) == {
        "currency",
        "fields",
        "skills",
        "max_mentees",
        "session_label_rule",
        "min_commitment",
        "years_mentoring_bands",
        "services_planned",
        "education_levels",
    }
    assert options["currency"] == "AUD"


def test_the_form_no_longer_offers_a_session_format_to_choose():
    assert "service_types" not in mapping.get_form_options()


def test_the_form_publishes_the_group_size_range_and_the_label_rule():
    """
    The group size is the only question about the shape of a session, and the
    label follows from it. The frontend needs both the range and the rule.
    """
    options = mapping.get_form_options()

    assert options["max_mentees"] == {"min": 1, "max": 8}
    rule = options["session_label_rule"]
    assert rule["one_to_one"]["id"] == "one_to_one"
    assert rule["one_to_one"]["max_mentees"] == 1
    assert rule["group"]["id"] == "group"
    assert rule["group"]["max_mentees_from"] == 2
    assert rule["one_to_one"]["label"] and rule["group"]["label"]


@pytest.mark.parametrize("mentees", range(1, 9))
def test_the_published_rule_is_the_rule_the_mapping_applies(mentees):
    """
    A frontend labelling a session from the published rule must arrive at the
    label the API stores, or a mentor sees one word on the form and another
    on their profile.
    """
    rule = mapping.get_form_options()["session_label_rule"]
    from_rule = (
        rule["group"]["id"]
        if mentees >= rule["group"]["max_mentees_from"]
        else rule["one_to_one"]["id"]
    )

    assert from_rule == mapping.session_label(mentees)


@pytest.mark.parametrize(
    "key",
    [
        "fields",
        "skills",
        "min_commitment",
        "years_mentoring_bands",
        "services_planned",
        "education_levels",
    ],
)
def test_every_option_carries_an_id_and_a_label(key):
    for option in mapping.get_form_options()[key]:
        assert set(option) == {"id", "label"}
        assert option["label"]


def test_the_option_ids_are_the_ids_the_mapping_accepts():
    options = mapping.get_form_options()
    assert [o["id"] for o in options["fields"]] == list(mapping.FIELDS)
    assert [o["id"] for o in options["skills"]] == list(mapping.SKILLS)
    assert [o["id"] for o in options["min_commitment"]] == list(
        mapping.MIN_COMMITMENT_OPTIONS
    )
    assert [o["id"] for o in options["years_mentoring_bands"]] == list(
        mapping.YEARS_MENTORING_BANDS
    )


def test_the_options_a_mentor_reads_use_mentor_language():
    """
    No label may carry a word from the source dataset.

    The options endpoint is the most exposed surface in the system: whatever
    it returns is rendered straight onto the form.
    """
    options = mapping.get_form_options()
    labels = " ".join(
        [
            str(option["label"])
            for value in options.values()
            if isinstance(value, list)
            for option in value
        ]
        + [str(spec["label"]) for spec in options["session_label_rule"].values()]
    ).lower()
    for leaked in (
        "airbnb",
        "listing",
        "host",
        "night",
        "room",
        "guest",
        "property",
        "usd",
    ):
        assert leaked not in labels


def test_four_or_more_services_is_labelled_as_a_minimum():
    options = mapping.get_form_options()["services_planned"]
    top = next(option for option in options if option["id"] == mapping.SERVICES_CAP)
    assert "or more" in top["label"]
