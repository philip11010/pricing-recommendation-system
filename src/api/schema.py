"""
Input description and validation for the serving layer.

One source of truth for three jobs that must never disagree: which fields the
form renders, what counts as valid input, and which columns the pipeline is
handed. The field list is derived from the category lists in ``src.config``,
and the allowed categories and numeric bounds are read from the metadata the
training run wrote, so nothing here restates a fact that lives elsewhere.

The request model is built at runtime with ``pydantic.create_model`` rather
than written out as a class. A static class would have to repeat 25 field
names and hard-code bounds that properly belong to the training data, and it
would silently fall out of step the moment the feature list changed.

Numeric bounds are the observed training range. Rejecting input outside it is
deliberate: beyond the range the model has no evidence, and a confident number
from an unsupported input is worse than a refusal that says why.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    create_model,
    field_validator,
)

from src import config
from src.models.predict import LoadedModel

# Review columns are optional: blank means "no reviews yet", which is the
# state that src/preprocessing/reviews.py exists to represent. The pipeline
# derives has_no_reviews from number_of_reviews and fills these itself, so a
# blank is meaningful input rather than missing input.
OPTIONAL_REVIEW_COLUMNS: frozenset[str] = frozenset(
    {
        "review_scores_rating",
        "review_scores_accuracy",
        "review_scores_communication",
        "review_scores_value",
        "reviews_per_month",
    }
)

# Columns that only take whole numbers, so the form offers an integer spinner.
INTEGER_COLUMNS: frozenset[str] = frozenset(
    {
        "hosts_time_as_host_years",
        "hosts_time_as_host_months",
        "host_listings_count",
        "accommodates",
        "bedrooms",
        "beds",
        "number_of_reviews",
        "availability_30",
        "availability_90",
        "availability_365",
        "number_of_reviews_ltm",
        "number_of_reviews_l30d",
    }
)

# Human labels. A column with no entry falls back to its name with
# underscores replaced, which is readable enough for the rarer fields.
FIELD_LABELS: dict[str, str] = {
    "hosts_time_as_host_years": "Years as host",
    "hosts_time_as_host_months": "Additional months as host",
    "host_identity_verified": "Identity verified",
    "host_has_profile_pic": "Has profile picture",
    "host_listings_count": "Listings held by this host",
    "room_type": "Room type",
    "accommodates": "Accommodates (guests)",
    "bedrooms": "Bedrooms",
    "bathrooms": "Bathrooms",
    "beds": "Beds",
    "review_scores_rating": "Review score: overall",
    "review_scores_accuracy": "Review score: accuracy",
    "review_scores_communication": "Review score: communication",
    "review_scores_value": "Review score: value",
    "number_of_reviews": "Number of reviews (all time)",
    "host_is_superhost": "Superhost",
    "availability_30": "Nights available in 30 days",
    "availability_90": "Nights available in 90 days",
    "availability_365": "Nights available in 365 days",
    "number_of_reviews_ltm": "Reviews in the last 12 months",
    "number_of_reviews_l30d": "Reviews in the last 30 days",
    "reviews_per_month": "Reviews per month",
    "neighbourhood_cleansed": "Neighbourhood",
    "latitude": "Latitude",
    "longitude": "Longitude",
}

# Labels for the decision form, which is not derived from the feature list.
DECISION_LABELS: dict[str, str] = {
    "recommendation_id": "Recommendation",
    "decision": "Decision",
    "final_price": "New price",
}

# What each proxy column stands in for on the mentor platform. The dataset is
# Airbnb listings, so without this the form reads as a holiday-let form; the
# helper line is what makes the structural analogy visible at the point of
# entry rather than only in the write-up.
FIELD_HELP: dict[str, str] = {
    "hosts_time_as_host_years": "Host tenure stands in for mentor experience",
    "hosts_time_as_host_months": "Extra months of tenure, on top of the years",
    "host_identity_verified": "Identity check stands in for a verified credential",
    "host_has_profile_pic": "Profile completeness signal",
    "host_listings_count": "Portfolio size stands in for a mentor's session load",
    "room_type": "Listing type stands in for mentorship specialisation",
    "accommodates": "Capacity stands in for group session size",
    "bedrooms": "Scale of the offering",
    "bathrooms": "Scale of the offering",
    "beds": "Scale of the offering",
    "review_scores_rating": "Overall review score stands in for session rating",
    "review_scores_accuracy": "Accuracy score stands in for expectation matching",
    "review_scores_communication": "Communication score, as for a mentor",
    "review_scores_value": "Value score stands in for perceived value for money",
    "number_of_reviews": "Review count stands in for total sessions reviewed",
    "host_is_superhost": "Superhost status stands in for top-mentor status",
    "availability_30": "Open nights stand in for open booking slots",
    "availability_90": "Open nights stand in for open booking slots",
    "availability_365": "Open nights stand in for open booking slots",
    "number_of_reviews_ltm": "Recent reviews stand in for booking requests",
    "number_of_reviews_l30d": "Last 30 days, a short-run demand signal",
    "reviews_per_month": "Review velocity stands in for booking demand",
    "neighbourhood_cleansed": "Neighbourhood average stands in for the market benchmark",
    "latitude": "Location, part of the market benchmark",
    "longitude": "Location, part of the market benchmark",
}

# Columns the form always shows first, whatever the importances say.
# room_type carries the coarsest price signal in the data, and the
# neighbourhood is the market benchmark, so a demo that hid either would be
# missing the two inputs a reviewer will reach for first.
REQUIRED_PRIMARY_COLUMNS: tuple[str, ...] = ("room_type", "neighbourhood_cleansed")

# How many inputs to show before the "More details" section.
PRIMARY_FIELD_COUNT = 8

# The four input variable categories of the conceptual framework, in the
# order they are presented on the form.
CATEGORY_LISTS: tuple[tuple[str, list[str]], ...] = (
    ("Mentor profile", config.MENTOR_PROFILE_FEATURES),
    ("Mentor performance", config.MENTOR_PERFORMANCE_FEATURES),
    ("Demand indicators", config.DEMAND_INDICATOR_FEATURES),
    ("Market variables", config.MARKET_FEATURES),
)


@dataclass(frozen=True)
class FieldSpec:
    """Everything the template needs to render one input control."""

    name: str
    label: str
    category: str
    kind: str  # "number" or "choice"
    required: bool
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    step: str = "any"
    help_text: str = ""
    is_primary: bool = True

    @property
    def range_hint(self) -> str:
        """
        The accepted range, as "1 to 16", or "" when there is no bound.

        Shown beside the control rather than only as a placeholder, because a
        placeholder disappears as soon as the field has a value, which is
        exactly when the user is choosing a number and needs to know the
        limit. Input outside the range is refused, so the limit has to be
        visible before submitting rather than explained afterwards.
        """
        if self.kind != "number" or self.minimum is None or self.maximum is None:
            return ""
        return f"{_trim(self.minimum)} to {_trim(self.maximum)}"

    @property
    def placeholder(self) -> str:
        return self.range_hint


def _trim(value: float | None) -> str:
    """Format a bound without a trailing ``.0`` on whole numbers."""
    if value is None:
        return ""
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def primary_input_columns(
    model: LoadedModel,
    ranking: list[str] | None = None,
    count: int = PRIMARY_FIELD_COUNT,
) -> list[str]:
    """
    Choose the columns to show above the "More details" section.

    ``ranking`` is the importance order from
    :func:`src.models.report.raw_feature_ranking`. Selection order:

    1. :data:`REQUIRED_PRIMARY_COLUMNS`, always.
    2. The highest-ranked column of each of the four input categories, so
       every heading on the form has at least one field under it. A category
       with nothing visible would imply the model ignores it, which is not
       what an empty section means.
    3. The rest of the ranking, until ``count`` is reached.

    With no ranking available, the first ``count`` input columns are used, so
    the form still works on a checkout with no reports.
    """
    wanted = model.input_columns
    ranking = [column for column in (ranking or []) if column in wanted]

    chosen: list[str] = [c for c in REQUIRED_PRIMARY_COLUMNS if c in wanted]

    category_of = {
        column: category for category, columns in CATEGORY_LISTS for column in columns
    }
    represented = {category_of.get(column) for column in chosen}
    for category, _ in CATEGORY_LISTS:
        if category in represented:
            continue
        best = next(
            (c for c in ranking if category_of.get(c) == category),
            next((c for c in wanted if category_of.get(c) == category), None),
        )
        if best is not None:
            chosen.append(best)
            represented.add(category)

    for column in ranking or wanted:
        if len(chosen) >= count:
            break
        if column not in chosen:
            chosen.append(column)

    return chosen


def field_specs(
    model: LoadedModel, primary_columns: list[str] | None = None
) -> list[FieldSpec]:
    """
    Describe every input control, grouped by input variable category.

    Only columns the pipeline actually asks for are included, so a derived
    feature such as ``has_no_reviews`` never appears on the form.

    Args:
        model: The loaded model, which supplies the columns, categories and
            ranges.
        primary_columns: Columns to mark as primary. Every column is primary
            when this is None, which is the behaviour a caller that does not
            split the form wants.
    """
    wanted = model.input_columns
    choices = model.categorical_choices
    ranges = model.numeric_ranges

    specs: list[FieldSpec] = []
    for category, columns in CATEGORY_LISTS:
        for column in columns:
            if column not in wanted:
                continue
            label = FIELD_LABELS.get(column, column.replace("_", " ").capitalize())
            is_primary = primary_columns is None or column in primary_columns
            shared = {
                "name": column,
                "label": label,
                "category": category,
                "help_text": FIELD_HELP.get(column, ""),
                "is_primary": is_primary,
            }
            if column in choices:
                specs.append(
                    FieldSpec(
                        kind="choice",
                        required=True,
                        choices=tuple(choices[column]),
                        **shared,
                    )
                )
                continue
            bounds = ranges.get(column, {})
            specs.append(
                FieldSpec(
                    kind="number",
                    required=column not in OPTIONAL_REVIEW_COLUMNS,
                    minimum=bounds.get("min"),
                    maximum=bounds.get("max"),
                    step="1" if column in INTEGER_COLUMNS else "any",
                    **shared,
                )
            )
    return specs


def _group(specs: list[FieldSpec]) -> list[tuple[str, list[FieldSpec]]]:
    """Specs as ``[(category, [spec, ...]), ...]``, skipping empty categories."""
    return [
        (category, [spec for spec in specs if spec.category == category])
        for category, _ in CATEGORY_LISTS
        if any(spec.category == category for spec in specs)
    ]


def grouped_field_specs(
    model: LoadedModel, primary_columns: list[str] | None = None
) -> list[tuple[str, list[FieldSpec]]]:
    """Every field spec as ``[(category, [spec, ...]), ...]``."""
    return _group(field_specs(model, primary_columns))


def form_sections(
    model: LoadedModel, ranking: list[str] | None = None
) -> dict[str, list[tuple[str, list[FieldSpec]]]]:
    """
    The form split into the fields shown up front and the rest.

    Both halves keep the four category headings, so collapsing the remainder
    does not change what anything is called. Every column appears in exactly
    one half, so the rendered form still submits the complete input.

    Returns:
        ``{"primary": [(category, specs)], "more": [(category, specs)]}``
    """
    primary = primary_input_columns(model, ranking)
    specs = field_specs(model, primary)
    return {
        "primary": _group([spec for spec in specs if spec.is_primary]),
        "more": _group([spec for spec in specs if not spec.is_primary]),
    }


def build_request_model(model: LoadedModel) -> type[BaseModel]:
    """
    Build the Pydantic model that validates one prediction request.

    Categorical fields become ``Literal`` of the categories seen in training,
    so an unknown category is rejected by name rather than silently encoded as
    the reference level. Numeric fields carry the training range as ``ge`` and
    ``le``. Extra fields are forbidden, so a misspelled field name is an error
    rather than a silently ignored default.
    """
    fields: dict[str, Any] = {}
    for spec in field_specs(model):
        if spec.kind == "choice":
            annotation = Literal[spec.choices]  # type: ignore[valid-type]
            fields[spec.name] = (annotation, Field(description=spec.label))
            continue

        constraints: dict[str, Any] = {"description": spec.label}
        if spec.minimum is not None:
            constraints["ge"] = spec.minimum
        if spec.maximum is not None:
            constraints["le"] = spec.maximum

        number = Annotated[float, Field(**constraints)]
        if spec.required:
            fields[spec.name] = (number, ...)
        else:
            fields[spec.name] = (number | None, None)

    return create_model(
        "RecommendationRequest",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def clean_form_values(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Normalise raw form input before validation.

    An HTML form submits an empty text input as ``""``. Dropping those keys
    makes a blank required field report "Field required" and lets a blank
    optional field fall back to its ``None`` default, which is what a blank
    review score means.
    """
    return {
        key: value
        for key, value in raw.items()
        if not (isinstance(value, str) and value.strip() == "")
    }


def readable_errors(error: ValidationError) -> list[dict[str, str]]:
    """
    Flatten a ValidationError into ``[{"field": ..., "message": ...}]``.

    Labels rather than column names, so the message points at the control the
    user can see.
    """
    messages = []
    for item in error.errors():
        location = item["loc"]
        name = str(location[0]) if location else ""
        messages.append(
            {
                "field": name,
                "label": FIELD_LABELS.get(name, DECISION_LABELS.get(name, name))
                or "input",
                "message": item["msg"],
            }
        )
    return messages


class DecisionRequest(BaseModel):
    """
    The mentor's response to one recommendation.

    Static, unlike the prediction request: the three actions are a fixed part
    of the design, not a function of the trained model.

    ``final_price`` is required and positive for "modify", because a
    modification without a new price says nothing. It is ignored for "reject",
    where the mentor has declined to tell us their price, and is filled in
    from the recommendation for "accept".
    """

    model_config = ConfigDict(extra="forbid")

    recommendation_id: int = Field(ge=1, description="Recommendation")
    decision: Literal["accept", "modify", "reject"] = Field(description="Decision")
    # validate_default, because a form that omits the price box entirely
    # leaves this at its default, and Pydantic skips validators for a field
    # that was never supplied. Without it, "modify" with no price would pass
    # validation and only be caught by the database CHECK constraint, which
    # is a 500 rather than a message beside the field.
    final_price: float | None = Field(
        default=None, gt=0, validate_default=True, description="New price"
    )

    @field_validator("final_price")
    @classmethod
    def price_must_match_action(
        cls, value: float | None, info: ValidationInfo
    ) -> float | None:
        """
        A field validator rather than a model validator, so the error is
        reported against ``final_price`` and the page can show it beside the
        price box. A model-level error carries no field and could only be
        shown in the summary.

        ``decision`` is declared first, so it is already validated and present
        in ``info.data`` by the time this runs. It is absent only when
        ``decision`` itself failed, and there is nothing to check against then.
        """
        decision = info.data.get("decision")
        if decision == "modify" and value is None:
            raise ValueError(
                "Choosing Modify needs a new price greater than 0 in the price box."
            )
        if decision == "reject":
            # Whatever is left in the price box is not part of a rejection.
            return None
        return value


# Overrides for the "Load example listing" button: one concrete inner-Sydney
# listing rather than a column-by-column average. The medians below describe a
# listing nobody owns, which is fine as a starting point and poor as a
# demonstration, so the example is internally consistent instead: a two-bedroom
# apartment in the City of Sydney, well reviewed and often booked.
EXAMPLE_LISTING: dict[str, Any] = {
    "room_type": "Entire home/apt",
    "accommodates": 4,
    "bedrooms": 2,
    "beds": 2,
    "bathrooms": 1,
    "neighbourhood_cleansed": "Sydney",
    "latitude": -33.8688,
    "longitude": 151.2093,
    "hosts_time_as_host_years": 6,
    "hosts_time_as_host_months": 4,
    "host_listings_count": 2,
    "host_is_superhost": "t",
    "host_identity_verified": "t",
    "host_has_profile_pic": "t",
    "review_scores_rating": 4.85,
    "review_scores_accuracy": 4.86,
    "review_scores_communication": 4.9,
    "review_scores_value": 4.7,
    "number_of_reviews": 84,
    "number_of_reviews_ltm": 24,
    "number_of_reviews_l30d": 2,
    "reviews_per_month": 1.8,
    "availability_30": 11,
    "availability_90": 38,
    "availability_365": 190,
}


def example_values(model: LoadedModel) -> dict[str, Any]:
    """
    The pre-filled form: the training median or mode of every column.

    Filling the form from the training centre means it always holds a
    submittable listing, so a demo never opens on 20 empty boxes and no value
    can be out of the range validation accepts.

    Medians and modes come from the metadata the training run wrote, computed
    on the training split only. When they are absent, because the metadata
    predates them, numeric fields fall back to the midpoint of the range and
    categorical fields to the first category, which is still inside the
    accepted range.
    """
    medians = model.numeric_medians
    modes = model.categorical_modes

    values: dict[str, Any] = {}
    for spec in field_specs(model):
        if spec.kind == "choice":
            fallback = spec.choices[0] if spec.choices else ""
            values[spec.name] = modes.get(spec.name, fallback)
        elif spec.name in medians:
            median = medians[spec.name]
            values[spec.name] = int(round(median)) if spec.step == "1" else median
        elif spec.minimum is None or spec.maximum is None:
            values[spec.name] = ""
        else:
            midpoint = (spec.minimum + spec.maximum) / 2
            values[spec.name] = (
                int(round(midpoint)) if spec.step == "1" else round(midpoint, 4)
            )
    return values


def example_listing_values(model: LoadedModel) -> dict[str, Any]:
    """
    The "Load example listing" values, clamped to what validation accepts.

    Built from :data:`EXAMPLE_LISTING` over the median defaults, so a column
    the example does not mention still gets a usable value. Each number is
    clamped to its training range and each category checked against the
    training categories, because the example is written by hand and the ranges
    come from whichever snapshot was trained on.
    """
    values = example_values(model)
    specs = {spec.name: spec for spec in field_specs(model)}

    for column, value in EXAMPLE_LISTING.items():
        spec = specs.get(column)
        if spec is None:
            continue
        if spec.kind == "choice":
            if value in spec.choices:
                values[column] = value
            continue
        number = float(value)
        if spec.minimum is not None:
            number = max(number, spec.minimum)
        if spec.maximum is not None:
            number = min(number, spec.maximum)
        values[column] = int(round(number)) if spec.step == "1" else number

    return values
