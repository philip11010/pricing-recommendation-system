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
    create_model,
    model_validator,
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

    @property
    def placeholder(self) -> str:
        if self.kind != "number" or self.minimum is None:
            return ""
        return f"{_trim(self.minimum)} to {_trim(self.maximum)}"


def _trim(value: float | None) -> str:
    """Format a bound without a trailing ``.0`` on whole numbers."""
    if value is None:
        return ""
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def field_specs(model: LoadedModel) -> list[FieldSpec]:
    """
    Describe every input control, grouped by input variable category.

    Only columns the pipeline actually asks for are included, so a derived
    feature such as ``has_no_reviews`` never appears on the form.
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
            if column in choices:
                specs.append(
                    FieldSpec(
                        name=column,
                        label=label,
                        category=category,
                        kind="choice",
                        required=True,
                        choices=tuple(choices[column]),
                    )
                )
                continue
            bounds = ranges.get(column, {})
            specs.append(
                FieldSpec(
                    name=column,
                    label=label,
                    category=category,
                    kind="number",
                    required=column not in OPTIONAL_REVIEW_COLUMNS,
                    minimum=bounds.get("min"),
                    maximum=bounds.get("max"),
                    step="1" if column in INTEGER_COLUMNS else "any",
                )
            )
    return specs


def grouped_field_specs(model: LoadedModel) -> list[tuple[str, list[FieldSpec]]]:
    """Field specs as ``[(category, [spec, ...]), ...]`` for the template."""
    specs = field_specs(model)
    return [
        (category, [spec for spec in specs if spec.category == category])
        for category, _ in CATEGORY_LISTS
        if any(spec.category == category for spec in specs)
    ]


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
    final_price: float | None = Field(default=None, gt=0, description="New price")

    @model_validator(mode="after")
    def check_price_matches_action(self) -> DecisionRequest:
        if self.decision == "modify" and self.final_price is None:
            raise ValueError(
                "Choosing Modify needs a new price greater than 0 in the price box."
            )
        if self.decision == "reject":
            # Whatever is left in the price box is not part of a rejection.
            object.__setattr__(self, "final_price", None)
        return self


def example_values(model: LoadedModel) -> dict[str, Any]:
    """
    A plausible pre-filled form, so the page is usable without 25 guesses.

    Numeric fields take the midpoint of the training range, rounded for the
    integer columns; categorical fields take the last category, which is the
    affirmative one for the ``f``/``t`` flags. This is a convenience default,
    not a representative listing.
    """
    values: dict[str, Any] = {}
    for spec in field_specs(model):
        if spec.kind == "choice":
            values[spec.name] = spec.choices[-1] if spec.choices else ""
        elif spec.minimum is None or spec.maximum is None:
            values[spec.name] = ""
        else:
            midpoint = (spec.minimum + spec.maximum) / 2
            values[spec.name] = (
                int(round(midpoint)) if spec.step == "1" else round(midpoint, 4)
            )
    return values
