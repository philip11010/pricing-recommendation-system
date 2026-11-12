"""
The only place mentor terms are translated into model input columns.

The model was trained on a proxy dataset, so its column names describe that
dataset rather than mentorship. Letting those names leak outwards would put
source-dataset vocabulary into API responses, error messages and the form the
mentor fills in. So the translation lives here, once, behind mentor-facing
names, and nothing outside this module knows a model column name.

That gives two properties worth having. The vocabulary a mentor sees is
decided in one file, and when the platform's own dataset arrives and the model
is retrained on real columns, this is the module that changes: callers keep
working against the same mentor-facing inputs.

Every option list is also the source of :func:`get_form_options`, so the
frontend renders the form from the same constants the validator checks
against and the two cannot drift apart.

Two inputs are decided here rather than asked, and both are deliberate:

* **Session format is held at one value.** The model's format column has one
  value the training data supports well and one it barely supports. Prices
  built on the thin one did not move sensibly with the size of the group, so
  every mentor is priced on the well-supported value and the size of the
  group is what distinguishes one session from another.
* **A new mentor's tenure is a fixed constant.** How long someone has been
  mentoring is asked, stored and shown on their profile, but it is not given
  to the model: a new mentor has no time on the platform, whatever their
  career length. Tenure for a mentor who does have a record comes from that
  record, which is a later step.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

CURRENCY = "AUD"

# ---------------------------------------------------------------------------
# Model column names
#
# Named once here so no other line in the file repeats a string that belongs
# to the proxy dataset.
# ---------------------------------------------------------------------------
COLUMN_SESSION_FORMAT = "room_type"
COLUMN_FIELD = "neighbourhood_cleansed"
COLUMN_MAX_MENTEES = "accommodates"
COLUMN_MIN_COMMITMENT = "minimum_nights"
COLUMN_SKILLS = "amenities_count"
COLUMN_SERVICES = "calculated_host_listings_count"
COLUMN_TENURE = "host_tenure_years"
COLUMN_VERIFIED = "host_identity_verified"

# The eight core columns, in the order the core pipeline was fitted on. The
# prediction service checks this against the loaded pipeline at startup.
CORE_COLUMNS: tuple[str, ...] = (
    COLUMN_MAX_MENTEES,
    COLUMN_SESSION_FORMAT,
    COLUMN_FIELD,
    COLUMN_MIN_COMMITMENT,
    COLUMN_SKILLS,
    COLUMN_VERIFIED,
    COLUMN_TENURE,
    COLUMN_SERVICES,
)

# ---------------------------------------------------------------------------
# Session format
#
# One constant for every mentor, rather than a question. The model's format
# column takes two values, and the training data supports them very
# unevenly: the value used here covers most of the rows, while the other is
# thin enough that prices built on it moved erratically with the size of the
# group. Group size is asked on its own and is what carries the capacity
# effect, so holding the format steady removes the noisy half of the column
# without losing anything a mentor would recognise.
# ---------------------------------------------------------------------------
SESSION_FORMAT_VALUE = "Entire home/apt"

# ---------------------------------------------------------------------------
# Session label
#
# What a session is called, derived from how many mentees can join it rather
# than asked as a separate question. It is shown to the mentor and stored on
# the service; it never reaches the model, which is given the group size
# itself.
# ---------------------------------------------------------------------------
LABEL_ONE_TO_ONE = "one_to_one"
LABEL_GROUP = "group"

# The smallest group. One seat is a one-to-one session; this many or more is
# a group.
GROUP_FROM_MENTEES = 2

SESSION_LABELS: dict[str, str] = {
    LABEL_ONE_TO_ONE: "One to one",
    LABEL_GROUP: "Group",
}

# ---------------------------------------------------------------------------
# Field of mentorship
#
# Twelve fields. The model learned price differences between twelve market
# segments of the proxy dataset, and each field is bound to one of them. The
# binding is arbitrary in the sense that no field "is" its segment; what it
# buys is that the model can price twelve distinguishable fields at all, which
# a single shared value would not.
# ---------------------------------------------------------------------------
FIELDS: dict[str, dict[str, str]] = {
    "executive_leadership": {
        "label": "Executive leadership",
        "column_value": "Pittwater",
    },
    "management_consulting": {
        "label": "Management consulting",
        "column_value": "Manly",
    },
    "law": {"label": "Law", "column_value": "Woollahra"},
    "investment_finance": {
        "label": "Investment and finance",
        "column_value": "Waverley",
    },
    "banking_accounting": {
        "label": "Banking and accounting",
        "column_value": "North Sydney",
    },
    "medicine_health": {"label": "Medicine and health", "column_value": "Randwick"},
    "engineering": {"label": "Engineering", "column_value": "Sutherland Shire"},
    "technology_software": {
        "label": "Technology and software",
        "column_value": "Sydney",
    },
    "marketing_communications": {
        "label": "Marketing and communications",
        "column_value": "Ryde",
    },
    "creative_arts_design": {
        "label": "Creative arts and design",
        "column_value": "Leichhardt",
    },
    "education_teaching": {
        "label": "Education and teaching",
        "column_value": "Hornsby",
    },
    "community_social_work": {
        "label": "Community and social work",
        "column_value": "Blacktown",
    },
}

# ---------------------------------------------------------------------------
# Skills
#
# A fixed list of thirty. Fixed because the count feeds the model: a mentor
# who ticks ten skills must mean the same thing next month as this month, and
# a list that grows would silently shift every price.
# ---------------------------------------------------------------------------
SKILL_LABELS: tuple[str, ...] = (
    "CV review",
    "Cover letter writing",
    "Interview preparation",
    "Career planning",
    "Career change",
    "Salary negotiation",
    "Networking",
    "Personal branding",
    "LinkedIn profile review",
    "Leadership",
    "Public speaking",
    "Time management",
    "Project management",
    "Portfolio review",
    "Graduate applications",
    "Job search strategy",
    "Workplace communication",
    "Conflict resolution",
    "Mentoring skills",
    "Presentation skills",
    "Data analysis",
    "Technical skills coaching",
    "Entrepreneurship",
    "Work-life balance",
    "Goal setting",
    "Performance reviews",
    "Promotion planning",
    "Remote work",
    "Further studies guidance",
    "Professional ethics",
)


def _skill_id(label: str) -> str:
    """The snake_case id for a skill label."""
    return (
        label.lower()
        .replace("-", " ")
        .replace("/", " ")
        .replace("  ", " ")
        .strip()
        .replace(" ", "_")
    )


SKILLS: dict[str, str] = {_skill_id(label): label for label in SKILL_LABELS}
SKILL_COUNT = len(SKILLS)

# Each ticked skill counts twice towards the model's breadth-of-offering
# column. The factor is what maps the thirty-skill list onto the range of that
# column in the training data, so a mentor who ticks everything sits near the
# top of it rather than at the bottom.
SKILL_WEIGHT = 2

# ---------------------------------------------------------------------------
# Remaining inputs
# ---------------------------------------------------------------------------
MAX_MENTEES_MIN = 1

# Eight is the 95th percentile of group size in the training data, and has
# plenty of rows behind it. Above it the data thins out and the prices stop
# behaving: the per-mentee figure stops falling as the group grows, which is
# the opposite of what a larger group means. So nine and up are outside the
# range the model can be trusted on, and the form does not offer them.
MAX_MENTEES_MAX = 8

# Sessions a mentee must commit to. Not free-form: the model saw a long tail
# of commitment lengths, and offering five fixed choices keeps every mentor on
# a value the model has seen plenty of.
MIN_COMMITMENT_OPTIONS: tuple[int, ...] = (1, 2, 3, 5, 7)

# What a service commits a mentee to when nobody said. One session: the
# smallest thing the platform offers and the one that asks least of a mentee,
# so a mentor who never answered the question has not had a commitment set on
# their behalf that a mentee has to meet.
MIN_COMMITMENT_DEFAULT = MIN_COMMITMENT_OPTIONS[0]

# How many services the model is told a mentor runs, at most. Its equivalent
# column saturates: beyond four the price stops moving, so a mentor with nine
# services is priced as one with four.
#
# The number itself is no longer asked. The registration form used to ask how
# many services a mentor planned to offer, which was a question about the
# future that a mentor had no way to answer accurately and that moved their
# price. What the model is given now is what the platform can see: how many
# services the mentor has actually published. See effective_services.
SERVICES_CAP = 4

# ---------------------------------------------------------------------------
# A price the mentor sets themselves
#
# When a mentor changes the advice or rejects it and says what they charge
# instead, that figure is theirs rather than the model's, so it is not held to
# the model's fences. It is still bounded, because the box it is typed into is
# the one place a typo becomes a stored price: a missing decimal point or an
# extra zero would otherwise be recorded as what a mentor charges and then
# shown back to them as fact.
#
# Whole units, like every other price in the system. The models round to whole
# AUD before anything is shown, and a mentor's own price sitting beside them
# with cents on it would imply a precision the comparison does not have.
# ---------------------------------------------------------------------------
FINAL_PRICE_MIN = 1
FINAL_PRICE_MAX = 5_000

# Time on the platform, for a mentor who has just joined. Not asked, because
# there is only one honest answer to it: a new mentor has no history here,
# however long their career has been. A mentor who does have a record is
# given the tenure from that record instead, which is a later step.
NEW_MENTOR_TENURE_YEARS = 0.5

# How long the mentor has been mentoring. Profile only: it is stored, shown
# on their profile and never given to the model. In the training data a
# longer tenure goes with a lower price, which describes that dataset rather
# than anything true about mentoring, and routing a mentor's experience into
# that column would advise the most experienced of them to charge the least.
#
# Asked as a number of years, which is what a mentor knows about themselves,
# and banded for display. Optional: a mentor who would rather not say leaves
# it out, and nothing about their price changes either way.
YEARS_EXPERIENCE_MIN = 0

# Sixty years of mentoring is longer than any career. The ceiling is a typing
# guard rather than a claim: it catches a year typed into a years box.
YEARS_EXPERIENCE_MAX = 60

YEARS_MENTORING_BANDS: dict[str, str] = {
    "under_1": "Under 1 year",
    "1_to_2": "1 to 2 years",
    "3_to_5": "3 to 5 years",
    "6_to_10": "6 to 10 years",
    "over_10": "Over 10 years",
}

# Profile only. Collected for the mentor's public profile and never given to
# the model, because the training dataset has no equivalent field to learn
# from. Listed here so the frontend reads it from the API like every other
# option list.
EDUCATION_LEVELS: dict[str, str] = {
    "secondary": "Secondary school",
    "certificate": "Certificate",
    "diploma": "Diploma",
    "bachelors": "Bachelor's degree",
    "postgraduate_diploma": "Postgraduate diploma",
    "masters": "Master's degree",
    "doctorate": "Doctorate",
    "other": "Other",
}

# ---------------------------------------------------------------------------
# Track record
#
# The twenty-eight extra columns the full model takes on top of the eight
# core ones, each behind a mentor-facing name. The table that stores them uses
# these names; the translation to model columns happens here.
#
# The order is the order the full model was fitted in, which is the core
# columns followed by these. :func:`check_model_columns` holds that claim
# against the metadata the application loads, so a retrained model that
# reorders or renames a column is caught at startup rather than priced on.
# ---------------------------------------------------------------------------
HISTORY_FIELDS: dict[str, str] = {
    "top_rated_mentor": "host_is_superhost",
    "reviews_total": "number_of_reviews",
    "reviews_last_12_months": "number_of_reviews_ltm",
    "reviews_per_month": "reviews_per_month",
    "rating_overall": "review_scores_rating",
    "rating_accuracy": "review_scores_accuracy",
    "rating_preparedness": "review_scores_cleanliness",
    "rating_onboarding": "review_scores_checkin",
    "rating_communication": "review_scores_communication",
    "rating_accessibility": "review_scores_location",
    "rating_value": "review_scores_value",
    "open_slots_next_year": "availability_365",
    "booked_share_30d": "occ_30",
    "booked_share_60d": "occ_60",
    "booked_share_90d": "occ_90",
    "booked_share_365d": "occ_365",
    "booked_share_weekend_365d": "weekend_occ_365",
    "booked_share_weekday_365d": "weekday_occ_365",
    "booked_share_weekend_minus_weekday": "weekend_minus_weekday_occ",
    "availability_blocks_365d": "n_availability_blocks_365",
    "reviews_90d": "reviews_last_90d",
    "reviews_180d": "reviews_last_180d",
    "reviews_365d": "reviews_last_365d",
    "days_since_last_review": "days_since_last_review",
    "review_growth": "review_growth",
    "years_since_first_review": "first_review_age_years",
    "has_no_reviews": "has_no_reviews",
    "has_booking_data": "has_calendar_data",
}

HISTORY_COLUMNS: tuple[str, ...] = tuple(HISTORY_FIELDS.values())
FULL_COLUMNS: tuple[str, ...] = CORE_COLUMNS + HISTORY_COLUMNS

# Tenure is the twenty-ninth quantity the track-record table stores and not a
# twenty-ninth column: it carries the tenure the core mapping holds at
# NEW_MENTOR_TENURE_YEARS for someone who has just joined. A mentor with a
# record has a real figure, so the record supplies it and the constant is only
# ever used for a mentor who has none.
HISTORY_TENURE_FIELD = "tenure_years"

# Everything the track-record table holds, which is one more name than the
# full model has extra columns.
HISTORY_STORED_FIELDS: tuple[str, ...] = (*HISTORY_FIELDS, HISTORY_TENURE_FIELD)

# ---------------------------------------------------------------------------
# What a track-record value may be
#
# The table is written by the platform rather than typed by a mentor, so these
# bounds are not form validation: they are the assertion that a row which
# reaches the full model describes something possible. A rating of 9 or a
# booked share of 4 would still produce a price, and a plausible-looking one,
# which is exactly why it is refused here instead.
# ---------------------------------------------------------------------------
RATING_MAX = 5.0

# Stored as true or false, given to the model as 1 or 0.
HISTORY_FLAG_FIELDS: tuple[str, ...] = (
    "top_rated_mentor",
    "has_no_reviews",
    "has_booking_data",
)

# Each out of five.
HISTORY_RATING_FIELDS: tuple[str, ...] = (
    "rating_overall",
    "rating_accuracy",
    "rating_preparedness",
    "rating_onboarding",
    "rating_communication",
    "rating_accessibility",
    "rating_value",
)

# A proportion of the mentor's offered time, so zero to one.
HISTORY_SHARE_FIELDS: tuple[str, ...] = (
    "booked_share_30d",
    "booked_share_60d",
    "booked_share_90d",
    "booked_share_365d",
    "booked_share_weekend_365d",
    "booked_share_weekday_365d",
)

# One share minus another, so either side of zero.
HISTORY_DIFFERENCE_FIELDS: tuple[str, ...] = ("booked_share_weekend_minus_weekday",)

# Whole things that have happened or are open, so zero or more.
HISTORY_COUNT_FIELDS: tuple[str, ...] = (
    "reviews_total",
    "reviews_last_12_months",
    "reviews_90d",
    "reviews_180d",
    "reviews_365d",
    "open_slots_next_year",
    "availability_blocks_365d",
    "days_since_last_review",
)

# Measured quantities that are not whole, and cannot be negative.
HISTORY_MEASURE_FIELDS: tuple[str, ...] = (
    "reviews_per_month",
    "review_growth",
    "years_since_first_review",
    HISTORY_TENURE_FIELD,
)

# ---------------------------------------------------------------------------
# What an explanation of a price is allowed to name
#
# A price is worked out from model columns and explained in a mentor's own
# words, so the join between the two belongs here with every other join of
# that kind. The explanation code reads these and never a column name.
#
# Three kinds of input, and the difference between them is what a mentor can
# do about them.
#
# **Fixed.** Held at one value for everybody, or held at a starting value for
# somebody who has just joined. A mentor did not choose them and cannot change
# them, so they are folded into the starting point a price is explained from
# rather than listed as something that moved it. Listing them would be
# offering a mentor a lever that is not connected to anything.
#
# **Choices.** The answers on the form. These are what the explanation is
# for.
#
# **Record.** What the platform has measured about a mentor who has been here
# a while. Twenty-nine quantities is not an explanation, so they are read as
# four themes, and each theme carries a caution: a price moving with a theme
# is an association among mentors who charge alike, not a claim that one
# causes the other.
# ---------------------------------------------------------------------------
EXPLANATION_FIXED_COLUMNS: tuple[str, ...] = (COLUMN_SESSION_FORMAT,)

CHOICE_FIELD = "field"
CHOICE_GROUP_SIZE = "group_size"
CHOICE_SKILLS = "skills"
CHOICE_VERIFIED = "verified"
CHOICE_SERVICES = "services"
CHOICE_COMMITMENT = "commitment"

# The order is the order a mentor answered them in, which is the order they
# are tie-broken in when two effects are the same size.
EXPLANATION_CHOICES: dict[str, dict[str, Any]] = {
    CHOICE_FIELD: {"column": COLUMN_FIELD, "label": "Your field"},
    CHOICE_GROUP_SIZE: {"column": COLUMN_MAX_MENTEES, "label": "Your group size"},
    CHOICE_SKILLS: {"column": COLUMN_SKILLS, "label": "The skills you cover"},
    CHOICE_VERIFIED: {"column": COLUMN_VERIFIED, "label": "Your verified profile"},
    CHOICE_SERVICES: {"column": COLUMN_SERVICES, "label": "The services you offer"},
    CHOICE_COMMITMENT: {
        "column": COLUMN_MIN_COMMITMENT,
        "label": "Your minimum commitment",
    },
}

CHOICE_COLUMNS: tuple[str, ...] = tuple(
    choice["column"] for choice in EXPLANATION_CHOICES.values()
)

THEME_REVIEWS = "reviews"
THEME_RATINGS = "ratings"
THEME_BOOKINGS = "bookings"
THEME_STANDING = "standing"

# Four themes over every quantity the track-record table holds. The grouping
# is by what a mentor would recognise as one thing about themselves: how the
# reviews have come in, what mentees rate them, how much of their offered
# time gets taken, and how long they have been here with what standing.
EXPLANATION_THEMES: dict[str, dict[str, Any]] = {
    THEME_REVIEWS: {
        "label": "How your reviews have come in",
        "fields": (
            "reviews_total",
            "reviews_last_12_months",
            "reviews_per_month",
            "reviews_90d",
            "reviews_180d",
            "reviews_365d",
            "days_since_last_review",
            "review_growth",
            "years_since_first_review",
            "has_no_reviews",
        ),
    },
    THEME_RATINGS: {
        "label": "What mentees rate you",
        "fields": HISTORY_RATING_FIELDS,
    },
    THEME_BOOKINGS: {
        "label": "How much of your time is booked",
        "fields": (
            "open_slots_next_year",
            "booked_share_30d",
            "booked_share_60d",
            "booked_share_90d",
            "booked_share_365d",
            "booked_share_weekend_365d",
            "booked_share_weekday_365d",
            "booked_share_weekend_minus_weekday",
            "availability_blocks_365d",
            "has_booking_data",
        ),
    },
    THEME_STANDING: {
        "label": "Your standing and time on the platform",
        "fields": ("top_rated_mentor",),
    },
}


def explanation_theme_columns() -> dict[str, tuple[str, ...]]:
    """
    Each theme as the model columns behind it.

    Tenure joins the standing theme for a mentor who has a record, because
    for them it is a measurement rather than the starting value the form path
    holds it at. For a mentor without one it is fixed, and the caller folds it
    into the baseline instead.
    """
    grouped = {
        name: tuple(HISTORY_FIELDS[field] for field in theme["fields"])
        for name, theme in EXPLANATION_THEMES.items()
    }
    grouped[THEME_STANDING] = (*grouped[THEME_STANDING], COLUMN_TENURE)
    return grouped


def explanation_theme_label(name: str) -> str:
    return str(EXPLANATION_THEMES[name]["label"])


class ModelColumnsMismatchError(RuntimeError):
    """
    The loaded models do not take the columns this module produces.

    A build fault rather than a mentor's mistake, so it is not a
    :class:`MentorInputError`: nothing a mentor could type would cause it and
    no answer they could change would fix it.
    """


class MentorInputError(ValueError):
    """
    One of the mentor's answers cannot be used.

    The message is written for the mentor, not for a developer: it names the
    answer in the words the form uses and says what is accepted.
    """

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


def validate_field(value: Any) -> str:
    """The field id, or a mentor-facing error."""
    if value not in FIELDS:
        raise MentorInputError(
            "field",
            "Choose the field you mentor in from the list of options.",
        )
    return str(value)


def validate_max_mentees(value: Any) -> int:
    """
    The seats in one session.

    Booleans are rejected explicitly: in Python ``True`` is an ``int`` equal
    to 1, so a checkbox posted into this box would otherwise pass as a group
    of one.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise MentorInputError(
            "max_mentees",
            f"Enter how many mentees can join one session, as a whole number "
            f"between {MAX_MENTEES_MIN} and {MAX_MENTEES_MAX}.",
        )
    if not MAX_MENTEES_MIN <= value <= MAX_MENTEES_MAX:
        raise MentorInputError(
            "max_mentees",
            f"The number of mentees in one session must be between "
            f"{MAX_MENTEES_MIN} and {MAX_MENTEES_MAX}.",
        )
    return value


def validate_min_commitment(value: Any) -> int:
    """The number of sessions a mentee must commit to."""
    if isinstance(value, bool) or value not in MIN_COMMITMENT_OPTIONS:
        allowed = ", ".join(str(option) for option in MIN_COMMITMENT_OPTIONS)
        raise MentorInputError(
            "min_commitment",
            f"Choose the smallest number of sessions a mentee can book. The "
            f"options are {allowed}.",
        )
    return int(value)


def validate_skills(value: Any) -> list[str]:
    """
    The skill ids the mentor offers.

    An empty list is accepted: a mentor may publish a service before choosing
    what to put in it. Duplicates are not, because the count is what reaches
    the model and a repeated skill would inflate it.
    """
    if isinstance(value, str) or not isinstance(value, list | tuple):
        raise MentorInputError(
            "skills", "Send the skills you offer as a list of skill ids."
        )
    skills = [str(item) for item in value]
    unknown = [skill for skill in skills if skill not in SKILLS]
    if unknown:
        raise MentorInputError(
            "skills",
            f"These are not skills on the list: {', '.join(sorted(set(unknown)))}. "
            f"Choose from the {SKILL_COUNT} skills the options endpoint returns.",
        )
    if len(set(skills)) != len(skills):
        raise MentorInputError("skills", "Each skill can only be chosen once.")
    return skills


def validate_profile_verified(value: Any) -> bool:
    """Whether the mentor has completed identity verification."""
    if not isinstance(value, bool):
        raise MentorInputError(
            "profile_verified",
            "Say whether the mentor's profile is verified, as true or false.",
        )
    return value


def validate_years_mentoring(value: Any) -> str:
    """
    The experience band id. Profile only, never a model input.

    Still validated, because it is stored and shown on the mentor's profile
    and a band outside the list would render as nothing at all.
    """
    if value not in YEARS_MENTORING_BANDS:
        raise MentorInputError(
            "years_mentoring_band",
            "Choose how long the mentor has been mentoring from the list of "
            "options.",
        )
    return str(value)


def validate_years_experience(value: Any) -> int:
    """
    How many years the mentor has been mentoring. Profile only.

    Optional on the form, so ``None`` is handled by the caller rather than
    here: this is the rule for a number that was given. Booleans are rejected
    explicitly, as everywhere else a whole number is read.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise MentorInputError(
            "years_experience",
            f"Enter how many years you have been mentoring as a whole number "
            f"between {YEARS_EXPERIENCE_MIN} and {YEARS_EXPERIENCE_MAX}, or "
            f"leave it blank.",
        )
    if not YEARS_EXPERIENCE_MIN <= value <= YEARS_EXPERIENCE_MAX:
        raise MentorInputError(
            "years_experience",
            f"The number of years you have been mentoring has to be between "
            f"{YEARS_EXPERIENCE_MIN} and {YEARS_EXPERIENCE_MAX}.",
        )
    return value


def validate_services_count(value: Any) -> int:
    """How many services the mentor currently has. Zero is valid at signup."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MentorInputError(
            "services_count",
            "The number of services the mentor already offers must be zero or "
            "a positive whole number.",
        )
    return value


def validate_education_level(value: Any) -> str:
    """The education level id. Profile only, never a model input."""
    if value not in EDUCATION_LEVELS:
        raise MentorInputError(
            "education_level",
            "Choose the mentor's highest level of education from the list of "
            "options.",
        )
    return str(value)


def validate_final_price(value: Any, *, field: str = "final_price") -> int:
    """
    A price the mentor set themselves, in whole currency units.

    Booleans are rejected explicitly, as everywhere else a whole number is
    read: ``True`` is an ``int`` equal to 1 in Python, so a checkbox posted
    into this box would otherwise be stored as a one dollar session.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise MentorInputError(
            field,
            f"Enter the price you charge as a whole number of "
            f"{CURRENCY}, between {FINAL_PRICE_MIN:,} and {FINAL_PRICE_MAX:,}.",
        )
    if not FINAL_PRICE_MIN <= value <= FINAL_PRICE_MAX:
        raise MentorInputError(
            field,
            f"The price you charge has to be between {FINAL_PRICE_MIN:,} and "
            f"{FINAL_PRICE_MAX:,} {CURRENCY}.",
        )
    return value


def effective_services(services_count: int) -> int:
    """
    The service count the model is given: what the mentor has published.

    At least one, because this is only ever asked while pricing a service and
    a mentor being priced has one, and at most :data:`SERVICES_CAP`, where the
    model's equivalent column stops moving.

    It used to be the larger of what the mentor had published and what they
    said at registration they planned to offer. That question is no longer
    asked: it was a guess about the future that moved the mentor's price
    today, and a mentor who over-estimated their plans was quoted a price
    built on services that did not exist. What the platform can see is what it
    uses.
    """
    return min(max(services_count, 1), SERVICES_CAP)


def session_label(max_mentees: Any) -> str:
    """
    What to call a session of this size.

    Derived rather than asked, so the name a mentee reads and the number of
    seats the mentor set can never disagree.
    """
    mentees = validate_max_mentees(max_mentees)
    return LABEL_ONE_TO_ONE if mentees < GROUP_FROM_MENTEES else LABEL_GROUP


def max_mentees_from_inputs(inputs: dict[str, Any]) -> int:
    """
    The group size recorded in a stored set of model inputs.

    A price is divided by the number of mentees to show what each of them
    pays, and that has to be possible months later from the stored row alone.
    Reading it here keeps the caller from naming a model column.
    """
    try:
        return int(inputs[COLUMN_MAX_MENTEES])
    except (KeyError, TypeError, ValueError) as error:
        raise MentorInputError(
            "max_mentees",
            "The stored inputs behind this price do not say how many mentees "
            "the session was for.",
        ) from error


def skills_count_from_inputs(inputs: dict[str, Any]) -> int:
    """How many skills a stored set of model inputs stands for."""
    try:
        counted = round(float(inputs[COLUMN_SKILLS]) / SKILL_WEIGHT)
    except (KeyError, TypeError, ValueError) as error:
        raise MentorInputError(
            "skills",
            "The stored inputs behind this price do not say how many skills "
            "the service covers.",
        ) from error
    return int(min(max(counted, 0), SKILL_COUNT))


def answers_from_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """
    The mentor's own answers, read back out of a stored set of model inputs.

    The one direction this module had been missing. A price is stored as the
    row it was worked out from, and anything that wants to talk about that
    price in a mentor's words would otherwise have to name the columns
    itself, which is the boundary this module exists to hold.
    """
    try:
        return {
            CHOICE_FIELD: field_from_column_value(inputs[COLUMN_FIELD]),
            CHOICE_GROUP_SIZE: int(inputs[COLUMN_MAX_MENTEES]),
            CHOICE_SKILLS: skills_count_from_inputs(inputs),
            CHOICE_VERIFIED: bool(int(inputs[COLUMN_VERIFIED])),
            CHOICE_SERVICES: int(inputs[COLUMN_SERVICES]),
            CHOICE_COMMITMENT: int(inputs[COLUMN_MIN_COMMITMENT]),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise MentorInputError(
            "inputs",
            "The stored answers behind this price are incomplete, so it "
            "cannot be explained.",
        ) from error


def skills_to_column_value(skills: list[str]) -> int:
    """The breadth-of-offering value for a set of skills."""
    return len(skills) * SKILL_WEIGHT


def to_model_inputs(
    *,
    field: Any,
    max_mentees: Any,
    min_commitment: Any,
    skills: Any,
    profile_verified: Any,
    services_count: Any = 1,
) -> dict[str, Any]:
    """
    Translate one new mentor's answers into the eight core model columns.

    Every answer is validated first, so a caller either gets a complete row
    the model can score or a :class:`MentorInputError` naming the one answer
    that has to change. There is no partial result.

    Two of the eight columns are not answers. The session format is the
    constant explained at the top of this module, and tenure is
    :data:`NEW_MENTOR_TENURE_YEARS`, because this is the path for a mentor
    who has just joined. Neither is a parameter, so neither can be set by
    accident from somewhere else.
    """
    field_id = validate_field(field)
    mentees = validate_max_mentees(max_mentees)
    commitment = validate_min_commitment(min_commitment)
    chosen_skills = validate_skills(skills)
    verified = validate_profile_verified(profile_verified)
    count = validate_services_count(services_count)

    return {
        COLUMN_MAX_MENTEES: mentees,
        COLUMN_SESSION_FORMAT: SESSION_FORMAT_VALUE,
        COLUMN_FIELD: FIELDS[field_id]["column_value"],
        COLUMN_MIN_COMMITMENT: commitment,
        COLUMN_SKILLS: skills_to_column_value(chosen_skills),
        COLUMN_VERIFIED: int(verified),
        COLUMN_TENURE: float(NEW_MENTOR_TENURE_YEARS),
        COLUMN_SERVICES: effective_services(count),
    }


def _history_number(name: str, value: Any) -> float:
    """One track-record value as a finite number, or a message naming it."""
    if isinstance(value, bool):
        raise MentorInputError(
            name, f"{name} is a number in the mentor's track record, not a flag."
        )
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise MentorInputError(
            name, f"{name} has to be a number in the mentor's track record."
        ) from error
    if not math.isfinite(number):
        raise MentorInputError(
            name, f"{name} has to be a number in the mentor's track record."
        )
    return number


def _history_between(name: str, value: Any, low: float, high: float) -> float:
    number = _history_number(name, value)
    if not low <= number <= high:
        raise MentorInputError(
            name,
            f"{name} has to be between {low:g} and {high:g} in the mentor's "
            f"track record.",
        )
    return number


def _history_flag(name: str, value: Any) -> bool:
    """
    A stored flag as a boolean, whichever way the database handed it over.

    Zero and one are accepted as well as the booleans, because a driver may
    return either for a boolean column. The model was trained on 1 and 0 and
    is given those by :func:`history_to_model_inputs`; everything on the
    mentor-facing side of the translation deals in true and false.
    """
    if isinstance(value, bool):
        return value
    number = _history_number(name, value)
    if number not in (0.0, 1.0):
        raise MentorInputError(
            name,
            f"{name} is either true or false in the mentor's track record.",
        )
    return bool(number)


def _history_count(name: str, value: Any) -> int:
    number = _history_number(name, value)
    if number < 0 or number != int(number):
        raise MentorInputError(
            name,
            f"{name} has to be a whole number of zero or more in the mentor's "
            f"track record.",
        )
    return int(number)


def validate_history_value(name: str, value: Any) -> Any:
    """
    One track-record value, checked against what that quantity can be.

    The name decides the rule, so a field added to :data:`HISTORY_FIELDS`
    without being listed in one of the groups above fails loudly here rather
    than passing unchecked.
    """
    if name in HISTORY_FLAG_FIELDS:
        return _history_flag(name, value)
    if name in HISTORY_RATING_FIELDS:
        return _history_between(name, value, 0.0, RATING_MAX)
    if name in HISTORY_SHARE_FIELDS:
        return _history_between(name, value, 0.0, 1.0)
    if name in HISTORY_DIFFERENCE_FIELDS:
        return _history_between(name, value, -1.0, 1.0)
    if name in HISTORY_COUNT_FIELDS:
        return _history_count(name, value)
    if name in HISTORY_MEASURE_FIELDS:
        return _history_between(name, value, 0.0, float("inf"))
    raise MentorInputError(name, f"{name} is not part of the mentor's track record.")


def history_to_model_inputs(history: dict[str, Any]) -> dict[str, Any]:
    """
    Translate a mentor's track record into the columns the full model adds.

    Takes the mentor-facing names used by the track-record table and returns
    model columns: the twenty-eight extra ones, plus the core tenure column,
    because a mentor with a record is priced on the tenure in it rather than
    on the new-mentor constant. Merging the result over a core row is
    therefore the whole of the difference between the two paths.

    Every field must be present. The full model has no notion of a missing
    column, so a mentor with an incomplete record is priced by the core model
    instead, and that decision belongs to the caller that reads the row rather
    than to a silent default here.
    """
    expected = set(HISTORY_STORED_FIELDS)
    missing = sorted(expected - set(history))
    if missing:
        raise MentorInputError(
            "history",
            f"The mentor's track record is incomplete, so a price cannot be "
            f"based on it. Missing: {', '.join(missing)}.",
        )
    unexpected = sorted(set(history) - expected)
    if unexpected:
        raise MentorInputError(
            "history",
            f"The mentor's track record has entries the model does not use: "
            f"{', '.join(unexpected)}.",
        )

    # The flags are the one place the two vocabularies disagree on a type:
    # the table stores true and false, and the model was trained on 1 and 0.
    values: dict[str, Any] = {}
    for name, column in HISTORY_FIELDS.items():
        checked = validate_history_value(name, history[name])
        values[column] = int(checked) if name in HISTORY_FLAG_FIELDS else checked
    values[COLUMN_TENURE] = float(
        validate_history_value(HISTORY_TENURE_FIELD, history[HISTORY_TENURE_FIELD])
    )
    return values


def model_inputs_to_history(values: dict[str, Any]) -> dict[str, Any]:
    """
    The inverse: model columns back to the names the table stores.

    Needed by anything holding a row of model columns that has to write it as
    a mentor's track record. Without it a caller would have to know the column
    spellings, which is the one thing this module exists to prevent.
    """
    needed = (*HISTORY_COLUMNS, COLUMN_TENURE)
    missing = [column for column in needed if column not in values]
    if missing:
        raise MentorInputError(
            "history",
            f"These columns are needed to build a track record and were not "
            f"supplied: {', '.join(missing)}.",
        )
    history = {
        name: validate_history_value(name, values[column])
        for name, column in HISTORY_FIELDS.items()
    }
    history[HISTORY_TENURE_FIELD] = validate_history_value(
        HISTORY_TENURE_FIELD, values[COLUMN_TENURE]
    )
    return history


def check_model_columns(core: Sequence[str], full: Sequence[str]) -> None:
    """
    Hold the loaded models' column lists against this module's, or fail.

    Both lists have to match name for name and in order. The translation above
    assembles a row from these names, so a retrained model that renames or
    reorders a column would otherwise be handed values under the wrong
    headings: every input present, every one of them wrong, and a plausible
    price out the other end. Checked once at startup for that reason.
    """
    for what, declared, expected in (
        ("core", tuple(str(column) for column in core), CORE_COLUMNS),
        ("full", tuple(str(column) for column in full), FULL_COLUMNS),
    ):
        if declared == expected:
            continue
        extra = [column for column in declared if column not in expected]
        absent = [column for column in expected if column not in declared]
        detail = []
        if extra:
            detail.append(f"columns this application cannot supply: {extra}")
        if absent:
            detail.append(f"columns it supplies and the model does not take: {absent}")
        if not detail:
            detail.append("the same columns in a different order")
        raise ModelColumnsMismatchError(
            f"the {what} model takes {len(declared)} columns and "
            f"src/mentor/mapping.py describes {len(expected)}: " + "; ".join(detail)
        )


def field_from_column_value(value: Any) -> str:
    """
    The field id bound to one value of the model's market column.

    The inverse of the ``column_value`` entries in :data:`FIELDS`, for a
    caller holding a row of model columns that has to describe it as a
    mentor's field.
    """
    for field_id, spec in FIELDS.items():
        if spec["column_value"] == value:
            return field_id
    raise MentorInputError(
        "field", "That market segment is not bound to one of the twelve fields."
    )


def field_label(field_id: Any) -> str:
    """The label a mentor reads for a field id."""
    return FIELDS[validate_field(field_id)]["label"]


def service_name(field_id: Any, max_mentees: Any) -> str:
    """
    What to call one service, in a line a mentee could read on a card.

    Derived rather than asked, for the same reason the session label is: a
    mentor describes a service by choosing a field and a group size, and a
    name typed separately would be a third description of the same thing that
    could disagree with both. The field label keeps its capital, because it is
    a proper label rather than a word in the sentence.
    """
    label = field_label(field_id)
    mentees = validate_max_mentees(max_mentees)
    if mentees < GROUP_FROM_MENTEES:
        return f"{label}: one-to-one mentoring"
    return f"{label}: group mentoring"


def years_mentoring_band_for_experience(years: Any) -> str:
    """
    The band a number of years of mentoring falls in.

    The form asks for the number, which is what a mentor knows about
    themselves, and their profile shows the band, which is what a mentee needs
    to read. Both are profile text and neither reaches a model.
    """
    return years_mentoring_band_for_tenure(validate_years_experience(years))


def skills_count_from_column_value(value: Any) -> int:
    """
    How many skills a breadth-of-offering value stands for.

    The inverse of :func:`skills_to_column_value`, rounded because the column
    is not always an even number, and held between one and the length of the
    list: a mentor offers at least one skill and cannot offer more than the
    list holds.
    """
    count = round(_history_number("skills", value) / SKILL_WEIGHT)
    return int(min(max(count, 1), SKILL_COUNT))


def nearest_min_commitment(value: Any) -> int:
    """
    The offered commitment option closest to ``value``.

    The form offers five fixed choices, and anything translated into one of
    them has to land on a choice rather than near it. Ties go to the smaller
    option, which is the one that asks less of a mentee.
    """
    number = _history_number("min_commitment", value)
    return min(
        MIN_COMMITMENT_OPTIONS, key=lambda option: (abs(option - number), option)
    )


def years_mentoring_band_for_tenure(tenure_years: Any) -> str:
    """
    The experience band a length of time falls in.

    Profile text, like the band the form asks for. It is derived here only so
    that a mentor whose record carries a tenure is shown a band consistent
    with it rather than one picked at random.
    """
    years = _history_number(HISTORY_TENURE_FIELD, tenure_years)
    if years < 1:
        return "under_1"
    if years < 3:
        return "1_to_2"
    if years < 6:
        return "3_to_5"
    if years < 11:
        return "6_to_10"
    return "over_10"


def get_form_options() -> dict[str, Any]:
    """
    Every option list the registration form needs, with ids and labels.

    The frontend renders from this rather than from its own copies, so adding
    a field or a skill is a change in this module alone. ``id`` is what the
    API expects back; ``label`` is what the mentor reads.
    """
    return {
        "currency": CURRENCY,
        "fields": [{"id": key, "label": spec["label"]} for key, spec in FIELDS.items()],
        "skills": [{"id": key, "label": label} for key, label in SKILLS.items()],
        "max_mentees": {"min": MAX_MENTEES_MIN, "max": MAX_MENTEES_MAX},
        # Not a question. The form asks for the number of mentees and the
        # label follows from it, so the rule is published rather than a list
        # the mentor picks from.
        "session_label_rule": {
            "one_to_one": {
                "id": LABEL_ONE_TO_ONE,
                "label": SESSION_LABELS[LABEL_ONE_TO_ONE],
                "max_mentees": 1,
            },
            "group": {
                "id": LABEL_GROUP,
                "label": SESSION_LABELS[LABEL_GROUP],
                "max_mentees_from": GROUP_FROM_MENTEES,
            },
        },
        "min_commitment": [
            {
                "id": option,
                "label": f"{option} session" if option == 1 else f"{option} sessions",
            }
            for option in MIN_COMMITMENT_OPTIONS
        ],
        "min_commitment_default": MIN_COMMITMENT_DEFAULT,
        "years_mentoring_bands": [
            {"id": key, "label": label} for key, label in YEARS_MENTORING_BANDS.items()
        ],
        # A number of years rather than a list to pick from, and optional.
        # The bands above are how it is shown, not how it is asked.
        "years_experience": {
            "min": YEARS_EXPERIENCE_MIN,
            "max": YEARS_EXPERIENCE_MAX,
        },
        "education_levels": [
            {"id": key, "label": label} for key, label in EDUCATION_LEVELS.items()
        ],
    }
