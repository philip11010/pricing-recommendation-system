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

# 4 means "four or more". The model's equivalent column saturates: beyond four
# the price stops moving, so there is nothing to gain from asking for more
# precision.
SERVICES_PLANNED_OPTIONS: tuple[int, ...] = (1, 2, 3, 4)
SERVICES_CAP = 4

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
# Part 2 fills the table from platform activity. For now the map exists so the
# table, the full model and the prediction service all agree on one spelling
# per quantity.
# ---------------------------------------------------------------------------
HISTORY_FIELDS: dict[str, str] = {
    "top_mentor": "host_is_superhost",
    "total_reviews": "number_of_reviews",
    "reviews_last_year": "number_of_reviews_ltm",
    "reviews_per_month": "reviews_per_month",
    "rating_overall": "review_scores_rating",
    "rating_accuracy": "review_scores_accuracy",
    "rating_preparation": "review_scores_cleanliness",
    "rating_punctuality": "review_scores_checkin",
    "rating_communication": "review_scores_communication",
    "rating_relevance": "review_scores_location",
    "rating_value": "review_scores_value",
    "open_slots_365d": "availability_365",
    "booked_rate_30d": "occ_30",
    "booked_rate_60d": "occ_60",
    "booked_rate_90d": "occ_90",
    "booked_rate_365d": "occ_365",
    "weekend_booked_rate_365d": "weekend_occ_365",
    "weekday_booked_rate_365d": "weekday_occ_365",
    "weekend_minus_weekday_booked_rate": "weekend_minus_weekday_occ",
    "availability_blocks_365d": "n_availability_blocks_365",
    "reviews_last_90d": "reviews_last_90d",
    "reviews_last_180d": "reviews_last_180d",
    "reviews_last_365d": "reviews_last_365d",
    "days_since_last_review": "days_since_last_review",
    "review_growth": "review_growth",
    "first_review_age_years": "first_review_age_years",
    "has_no_reviews": "has_no_reviews",
    "has_schedule_data": "has_calendar_data",
}

HISTORY_COLUMNS: tuple[str, ...] = tuple(HISTORY_FIELDS.values())
FULL_COLUMNS: tuple[str, ...] = CORE_COLUMNS + HISTORY_COLUMNS


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


def validate_services_planned(value: Any) -> int:
    """How many services the mentor intends to offer, asked at registration."""
    if isinstance(value, bool) or value not in SERVICES_PLANNED_OPTIONS:
        allowed = ", ".join(str(option) for option in SERVICES_PLANNED_OPTIONS)
        raise MentorInputError(
            "services_planned",
            f"Choose how many services the mentor plans to offer. The options "
            f"are {allowed}, where {SERVICES_CAP} means {SERVICES_CAP} or more.",
        )
    return int(value)


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


def effective_services(services_count: int, services_planned: int) -> int:
    """
    The service count the model is given.

    A mentor who said at registration that they plan four services but has
    published one is priced as someone with a four-service offering: the
    intention is the better description of the practice, and pricing the first
    service as though it were the only one they will ever have would
    under-price it. The larger of the two wins, then the cap applies.
    """
    return min(max(services_count, services_planned), SERVICES_CAP)


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
    services_planned: Any,
    services_count: Any = 0,
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
    planned = validate_services_planned(services_planned)
    count = validate_services_count(services_count)

    return {
        COLUMN_MAX_MENTEES: mentees,
        COLUMN_SESSION_FORMAT: SESSION_FORMAT_VALUE,
        COLUMN_FIELD: FIELDS[field_id]["column_value"],
        COLUMN_MIN_COMMITMENT: commitment,
        COLUMN_SKILLS: skills_to_column_value(chosen_skills),
        COLUMN_VERIFIED: int(verified),
        COLUMN_TENURE: float(NEW_MENTOR_TENURE_YEARS),
        COLUMN_SERVICES: effective_services(count, planned),
    }


def history_to_model_inputs(history: dict[str, Any]) -> dict[str, Any]:
    """
    Translate a mentor's track record into the twenty-eight extra columns.

    Takes the mentor-facing names used by the track-record table and returns
    model columns. Every field must be present: the full model has no notion
    of a missing column, and a mentor with an incomplete record should be
    priced by the core model instead.
    """
    missing = sorted(set(HISTORY_FIELDS) - set(history))
    if missing:
        raise MentorInputError(
            "history",
            f"The mentor's track record is incomplete, so a price cannot be "
            f"based on it. Missing: {', '.join(missing)}.",
        )
    unexpected = sorted(set(history) - set(HISTORY_FIELDS))
    if unexpected:
        raise MentorInputError(
            "history",
            f"The mentor's track record has entries the model does not use: "
            f"{', '.join(unexpected)}.",
        )
    return {column: history[name] for name, column in HISTORY_FIELDS.items()}


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
        "years_mentoring_bands": [
            {"id": key, "label": label} for key, label in YEARS_MENTORING_BANDS.items()
        ],
        "services_planned": [
            {
                "id": option,
                "label": (
                    f"{option} or more services"
                    if option == SERVICES_CAP
                    else (f"{option} service" if option == 1 else f"{option} services")
                ),
            }
            for option in SERVICES_PLANNED_OPTIONS
        ],
        "education_levels": [
            {"id": key, "label": label} for key, label in EDUCATION_LEVELS.items()
        ],
    }
