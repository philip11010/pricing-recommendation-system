"""
Persistence schema for the mentor-facing pricing API.

Five tables, following the shape of the flow rather than the shape of the
model:

``mentors``
    Who registered. Profile text is stored because the mentor's profile page
    needs it, not because the model reads it: education, experience and
    credentials have no equivalent in the training data, so they are profile
    fields only.
``services``
    What a mentor offers. A mentor can have several; each is priced on its
    own, because the size and the audience differ between them. The label a
    session carries is derived from how many mentees can join it, and a
    constraint holds the two together.
``mentor_history``
    A mentor's accumulated track record, in mentor-facing names. One row per
    mentor, written by the platform rather than by the mentor. A mentor with a
    complete row is priced by the full model; a mentor with none, or with a
    partial one, is priced by the core model.
``recommendations``
    What the model advised, with the exact inputs it was given. The snapshot
    is stored so a price can be explained months later, after the mentor has
    edited the service and the live inputs no longer match.
``decisions``
    What the mentor did about the advice. Separate from the recommendation on
    purpose: the system advises and the mentor decides, and keeping the two
    rows apart is what makes that separation auditable rather than merely
    claimed.

Written against PostgreSQL, which is the deployment target, and run on SQLite
locally. Nothing here is SQLite-specific: ``JSON`` is the portable type that
maps to ``jsonb``-style storage on PostgreSQL and to serialised text on
SQLite, and every constraint is plain SQL that both accept.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models import Base, UtcDateTime, utcnow
from src.mentor.mapping import (
    GROUP_FROM_MENTEES,
    HISTORY_STORED_FIELDS,
    LABEL_GROUP,
    LABEL_ONE_TO_ONE,
    MAX_MENTEES_MAX,
    MAX_MENTEES_MIN,
    SERVICES_CAP,
)

# Which model produced a recommendation. Stored so that a price can be read
# back knowing how much the system had to go on when it gave it.
MODEL_CHOICES: tuple[str, ...] = ("core", "full")

# Where a recommendation stands. "pending" until the mentor answers it; the
# other three mirror the decision they made.
RECOMMENDATION_STATUSES: tuple[str, ...] = (
    "pending",
    "accepted",
    "modified",
    "rejected",
)

# What a mentor can do with advice. "modified" carries the price they chose
# instead, "rejected" carries none.
DECISION_ACTIONS: tuple[str, ...] = ("accepted", "modified", "rejected")


def _in_clause(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class Mentor(Base):
    """One registered mentor."""

    __tablename__ = "mentors"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    # Nullable and unused. There is no authentication yet, but a mentor row
    # created now has to be able to gain a password later without a migration
    # that rewrites existing rows.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    headline: Mapped[str | None] = mapped_column(String(300), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    education_level: Mapped[str | None] = mapped_column(String(60), nullable=True)
    experience_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    years_mentoring_band: Mapped[str] = mapped_column(String(20), nullable=False)
    # Asked once, at registration. Feeds the model together with the number of
    # services actually published: see mapping.effective_services.
    services_planned: Mapped[int] = mapped_column(Integer, nullable=False)
    # A mentor created by scripts/seed_demo_mentors.py to have something to
    # demonstrate. Flagged rather than inferred from the email domain, so the
    # seed script can find its own rows again and remove exactly those.
    is_demo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0", index=True
    )
    # Which record a seeded mentor was built from, as an opaque index into the
    # filtered population rather than anything identifying. Unique so that a
    # second run of the seed script recognises the rows it already wrote
    # instead of adding them again, and null for every mentor who registered.
    source_key: Mapped[int | None] = mapped_column(
        Integer, nullable=True, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow, nullable=False, index=True
    )

    services: Mapped[list[Service]] = relationship(
        back_populates="mentor",
        cascade="all, delete-orphan",
        order_by="Service.id",
    )
    history: Mapped[MentorHistory | None] = relationship(
        back_populates="mentor", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        CheckConstraint(
            f"services_planned BETWEEN 1 AND {SERVICES_CAP}",
            name="ck_mentor_services_planned",
        ),
    )

    def __repr__(self) -> str:
        return f"Mentor(id={self.id!r}, email={self.email!r})"


class Service(Base):
    """One priceable thing a mentor offers."""

    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    mentor_id: Mapped[int] = mapped_column(
        ForeignKey("mentors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field: Mapped[str] = mapped_column(String(40), nullable=False)
    max_mentees: Mapped[int] = mapped_column(Integer, nullable=False)
    # Derived from max_mentees, not asked. Stored rather than computed on
    # read so that a query can group services by what they are called, and
    # constrained below so the stored label and the stored number of seats
    # cannot come apart.
    session_label: Mapped[str] = mapped_column(String(20), nullable=False)
    min_commitment: Mapped[int] = mapped_column(Integer, nullable=False)
    # A list of skill ids. Stored as JSON rather than a join table: the list
    # is read and written whole, never queried by element, and the set of
    # valid ids is a fixed constant in src.mentor.mapping rather than data.
    skills: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    profile_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # What the mentor charges for this service today, in whole currency units,
    # or null if they have not set one. Nullable because a service may exist
    # before it has a price: that is the whole point of asking for advice.
    # Whole units for the same reason a recommendation is stored that way, so
    # the two can be compared without one of them pretending to be finer.
    current_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow, nullable=False, index=True
    )

    mentor: Mapped[Mentor] = relationship(back_populates="services")
    recommendations: Mapped[list[PricingRecommendation]] = relationship(
        back_populates="service",
        cascade="all, delete-orphan",
        order_by="PricingRecommendation.id",
    )

    __table_args__ = (
        CheckConstraint(
            f"max_mentees BETWEEN {MAX_MENTEES_MIN} AND {MAX_MENTEES_MAX}",
            name="ck_service_max_mentees",
        ),
        CheckConstraint("min_commitment >= 1", name="ck_service_min_commitment"),
        # NULL is tested explicitly: "current_price > 0" against NULL is NULL
        # rather than FALSE, and a CHECK only rejects a row on FALSE, so the
        # comparison alone would be no constraint at all on a priceless row
        # while also failing to say that null is allowed.
        CheckConstraint(
            "current_price IS NULL OR current_price > 0",
            name="ck_service_current_price_positive",
        ),
        CheckConstraint(
            f"(max_mentees < {GROUP_FROM_MENTEES} "
            f"   AND session_label = '{LABEL_ONE_TO_ONE}') "
            f"OR (max_mentees >= {GROUP_FROM_MENTEES} "
            f"   AND session_label = '{LABEL_GROUP}')",
            name="ck_service_session_label_matches_size",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"Service(id={self.id!r}, mentor_id={self.mentor_id!r}, "
            f"session_label={self.session_label!r}, field={self.field!r})"
        )


class MentorHistory(Base):
    """
    A mentor's accumulated track record: the extra inputs of the full model.

    One row per mentor, keyed on the mentor rather than carrying its own id,
    because there is nothing to say about a mentor's record except the record
    itself. Every column is nullable: a row may be written before the platform
    can compute all of it, and the prediction service only uses the full model
    when the row is complete.

    Names here are mentor-facing. src.mentor.mapping.HISTORY_FIELDS holds the
    translation to model columns, and is the only place the two vocabularies
    meet.
    """

    __tablename__ = "mentor_history"

    mentor_id: Mapped[int] = mapped_column(
        ForeignKey("mentors.id", ondelete="CASCADE"), primary_key=True
    )

    # Standing
    top_rated_mentor: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Reviews
    reviews_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviews_last_12_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviews_per_month: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviews_90d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviews_180d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviews_365d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    days_since_last_review: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_growth: Mapped[float | None] = mapped_column(Float, nullable=True)
    years_since_first_review: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_no_reviews: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Ratings, each out of five
    rating_overall: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_preparedness: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_onboarding: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_communication: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_accessibility: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Demand: how much of the mentor's offered time gets booked
    open_slots_next_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    booked_share_30d: Mapped[float | None] = mapped_column(Float, nullable=True)
    booked_share_60d: Mapped[float | None] = mapped_column(Float, nullable=True)
    booked_share_90d: Mapped[float | None] = mapped_column(Float, nullable=True)
    booked_share_365d: Mapped[float | None] = mapped_column(Float, nullable=True)
    booked_share_weekend_365d: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    booked_share_weekday_365d: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    booked_share_weekend_minus_weekday: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    availability_blocks_365d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_booking_data: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Time on the platform. Not one of the twenty-eight extra columns: it
    # carries the core tenure column, which the mapping layer holds at a
    # constant for a mentor who has just joined and reads from here for a
    # mentor who has a record.
    tenure_years: Mapped[float | None] = mapped_column(Float, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow, nullable=False
    )

    mentor: Mapped[Mentor] = relationship(back_populates="history")

    def stored_values(self) -> dict[str, Any]:
        """
        The row as the mentor-facing names the mapping layer translates.

        Reading the row through one method rather than at each call site keeps
        the list of what a track record consists of in
        src.mentor.mapping.HISTORY_STORED_FIELDS alone.
        """
        return {name: getattr(self, name, None) for name in HISTORY_STORED_FIELDS}

    @property
    def is_complete(self) -> bool:
        """
        Whether every quantity the full model needs has a value.

        The full model has no notion of a missing input, so a partial row is
        worth no more than none at all: it means the core model is used and
        the price stays marked low confidence.
        """
        return all(value is not None for value in self.stored_values().values())

    def __repr__(self) -> str:
        return (
            f"MentorHistory(mentor_id={self.mentor_id!r}, "
            f"complete={self.is_complete!r})"
        )


class PricingRecommendation(Base):
    """One advisory price for one service, and the inputs behind it."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_used: Mapped[str] = mapped_column(String(10), nullable=False)
    # Whole currency units. The models are trained on a log scale and the
    # output is rounded before it is shown, so storing cents would record a
    # precision the prediction does not have.
    recommended_price: Mapped[int] = mapped_column(Integer, nullable=False)
    price_low: Mapped[int] = mapped_column(Integer, nullable=False)
    price_high: Mapped[int] = mapped_column(Integer, nullable=False)
    # True when the price came from the core model, which has only what the
    # mentor typed to go on. Stored rather than derived from model_used so the
    # flag the mentor was shown stays true even if that rule changes.
    low_confidence: Mapped[bool] = mapped_column(Boolean, nullable=False)
    inputs_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    model_version: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="pending", server_default="pending"
    )
    generated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow, nullable=False, index=True
    )

    service: Mapped[Service] = relationship(back_populates="recommendations")
    decisions: Mapped[list[PricingDecision]] = relationship(
        back_populates="recommendation",
        cascade="all, delete-orphan",
        order_by="PricingDecision.decided_at",
    )

    __table_args__ = (
        CheckConstraint(
            _in_clause("model_used", MODEL_CHOICES), name="ck_recommendation_model"
        ),
        CheckConstraint(
            _in_clause("status", RECOMMENDATION_STATUSES),
            name="ck_recommendation_status",
        ),
        CheckConstraint(
            "recommended_price > 0 AND price_low > 0 AND price_high > 0",
            name="ck_recommendation_prices_positive",
        ),
        CheckConstraint(
            "price_low <= recommended_price AND recommended_price <= price_high",
            name="ck_recommendation_price_within_range",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"PricingRecommendation(id={self.id!r}, service_id={self.service_id!r}, "
            f"recommended_price={self.recommended_price!r})"
        )


class PricingDecision(Base):
    """What the mentor did with one recommendation."""

    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    # Null for "rejected": the mentor declined the advice and did not say what
    # they will charge instead. Numeric rather than integer because a mentor
    # typing their own price may well type cents.
    final_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow, nullable=False, index=True
    )

    recommendation: Mapped[PricingRecommendation] = relationship(
        back_populates="decisions"
    )

    __table_args__ = (
        CheckConstraint(
            _in_clause("action", DECISION_ACTIONS), name="ck_decision_action"
        ),
        # Every branch tests final_price for NULL explicitly. A bare
        # "final_price > 0" against NULL evaluates to NULL, not FALSE, and a
        # CHECK constraint only rejects a row on FALSE, so the comparison
        # alone would let a price-less "modified" row through.
        CheckConstraint(
            "(action IN ('accepted', 'modified') "
            "   AND final_price IS NOT NULL AND final_price > 0) "
            "OR (action = 'rejected' AND final_price IS NULL)",
            name="ck_decision_price_matches_action",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"PricingDecision(id={self.id!r}, "
            f"recommendation_id={self.recommendation_id!r}, action={self.action!r})"
        )
