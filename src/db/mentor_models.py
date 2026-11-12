"""
Persistence schema for the mentor-facing pricing API.

Six tables, following the shape of the flow rather than the shape of the
model:

``mentors``
    Who registered, and the hash of the password they sign in with. Profile
    text is stored because the mentor's profile page needs it, not because the
    model reads it: education, years of experience and credentials have no
    equivalent in the training data, so they are profile fields only. The
    ``verified`` flag is the platform's own statement about a mentor rather
    than one of theirs, which is why nothing a mentor sends can set it.
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
``mentor_activity``
    The same mentor's activity month by month, for the chart on their own
    page. Read by people rather than by a model: nothing in it reaches a
    price.
``recommendations``
    What the model advised, with the exact inputs it was given. The snapshot
    is stored so a price can be explained months later, after the mentor has
    edited the service and the live inputs no longer match.
``decisions``
    What the mentor did about the advice: at most one row per recommendation,
    which the database enforces. Separate from the recommendation on purpose:
    the system advises and the mentor decides, and keeping the two rows apart
    is what makes that separation auditable rather than merely claimed.

Written against PostgreSQL, which is the deployment target, and run on SQLite
locally. Nothing here is SQLite-specific: ``JSON`` is the portable type that
maps to ``jsonb``-style storage on PostgreSQL and to serialised text on
SQLite, and every constraint is plain SQL that both accept.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models import Base, UtcDateTime, utcnow
from src.mentor.mapping import (
    FINAL_PRICE_MAX,
    FINAL_PRICE_MIN,
    GROUP_FROM_MENTEES,
    HISTORY_STORED_FIELDS,
    LABEL_GROUP,
    LABEL_ONE_TO_ONE,
    MAX_MENTEES_MAX,
    MAX_MENTEES_MIN,
    YEARS_EXPERIENCE_MAX,
    YEARS_EXPERIENCE_MIN,
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
    # Stored lowercased and trimmed, by src.mentor.security.normalise_email.
    # Unique twice over: on the column, and on its lowercased form in a
    # functional index, so two mentors cannot register the same address in
    # different capitals however a row is written.
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    # The Argon2 hash of the mentor's password. Still nullable, because a
    # mentor row seeded or written before a password existed has none, and a
    # row without one can never be signed in to: see
    # src.mentor.security.verify_password.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Whether the platform has checked who this mentor is. False for everyone
    # who registers, and set by scripts/verify_mentor.py once a person has
    # looked. It is shown on the public directory as a checkmark, and the
    # matching flag on each of the mentor's services is what the model reads.
    verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0", index=True
    )
    headline: Mapped[str | None] = mapped_column(String(300), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    education_level: Mapped[str | None] = mapped_column(String(60), nullable=True)
    experience_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    # How many years the mentor has been mentoring, and the band it falls in.
    # Both profile only, never model inputs. The number is what the mentor is
    # asked and the band is how it is shown, and the band is derived from the
    # number rather than asked separately. Both nullable: answering is
    # optional and nothing about the price depends on it.
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    years_mentoring_band: Mapped[str | None] = mapped_column(String(20), nullable=True)
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
    activity: Mapped[list[MentorActivity]] = relationship(
        back_populates="mentor",
        cascade="all, delete-orphan",
        order_by="MentorActivity.month",
    )
    __table_args__ = (
        CheckConstraint(
            f"years_experience IS NULL OR years_experience BETWEEN "
            f"{YEARS_EXPERIENCE_MIN} AND {YEARS_EXPERIENCE_MAX}",
            name="ck_mentor_years_experience",
        ),
        # One account per address, whatever capitals it was typed in. The
        # application lowercases an address before it stores or compares one,
        # so this index is the guard against the row that bypasses it: a seed
        # script, a migration, or a second application writing the same table.
        # An expression index rather than a constraint, because both SQLite
        # and PostgreSQL support one and neither supports a check on a
        # function of a column it can enforce across rows.
        Index("ix_mentors_email_lower", text("lower(email)"), unique=True),
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


class MentorActivity(Base):
    """
    One month of a mentor's activity, for the chart on their own page.

    One row per mentor per month, keyed on the pair, so a rebuild writes over
    the month it recomputed rather than adding a second copy of it. The month
    is stored as its first day: a date column answers "which month is this"
    without a convention about how a month is spelled, and sorts correctly.

    Separate from ``mentor_history``, which holds the twenty-eight figures a
    model reads as they stand today. This table is the same mentor's activity
    over time, it is read by people rather than by a model, and nothing here
    reaches a price.

    Every measure except the review count is nullable, and that is a statement
    about the sources rather than a convenience: a month the platform has
    reviews for but no booking record has a row with a review count and
    nothing else. A zero would say the mentor was booked for none of their
    offered time, which is a different claim from not knowing.

    Ratings over time are deliberately absent. The sources hold one rating per
    mentor as it stands now, with no record of what it was in any earlier
    month, so a rating line would have to be invented.
    """

    __tablename__ = "mentor_activity"

    mentor_id: Mapped[int] = mapped_column(
        ForeignKey("mentors.id", ondelete="CASCADE"), primary_key=True
    )
    month: Mapped[date] = mapped_column(Date, primary_key=True)

    reviews_count: Mapped[int] = mapped_column(Integer, nullable=False)
    booked_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    # What the mentor charged that month, in whole currency units. Nullable
    # for the same reason as the booked share: a month with no price on record
    # has none, and inventing one would put a figure on a chart that nobody
    # measured.
    price: Mapped[int | None] = mapped_column(Integer, nullable=True)

    mentor: Mapped[Mentor] = relationship(back_populates="activity")

    __table_args__ = (
        CheckConstraint("reviews_count >= 0", name="ck_activity_reviews_count"),
        # NULL is tested explicitly in both: a bare comparison against NULL
        # evaluates to NULL rather than FALSE, and a CHECK only rejects a row
        # on FALSE, so the comparison alone would be no constraint at all on a
        # row that has no figure while also failing to say that none is
        # allowed.
        CheckConstraint(
            "booked_share IS NULL OR (booked_share >= 0 AND booked_share <= 1)",
            name="ck_activity_booked_share",
        ),
        CheckConstraint(
            "price IS NULL OR price > 0", name="ck_activity_price_positive"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"MentorActivity(mentor_id={self.mentor_id!r}, month={self.month!r}, "
            f"reviews_count={self.reviews_count!r})"
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

    @property
    def decision(self) -> PricingDecision | None:
        """
        The mentor's answer to this recommendation, or None while it stands.

        A list of at most one, which the database enforces. Exposed as a
        single value because every caller wants "what did the mentor say" and
        would otherwise reach for ``[0]`` and have to guard it.
        """
        return self.decisions[0] if self.decisions else None

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
    # Unique: a recommendation is answered once. The mentor can ask for a
    # fresh price as often as they like, and each one is a new recommendation
    # with its own decision, so a second decision on the same row would mean
    # two different answers to one question with no way to tell which stands.
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    # What the mentor settled on. Set for "accepted" and "modified", and
    # optional for "rejected": a mentor who declines the advice may say what
    # they charge instead, which is the most useful thing they could tell the
    # system, or may simply decline and say nothing.
    #
    # Numeric rather than Integer because the earlier prototype wrote cents
    # into this column and the type is not worth a rewrite. Everything written
    # through the API is a whole number: see mapping.validate_final_price.
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
        #
        # A rejection is the one action that may go either way: with the
        # mentor's own price, or with nothing. Both branches bound the price
        # the same way, so there is no action for which an unbounded figure
        # can be stored.
        CheckConstraint(
            f"(action IN ('accepted', 'modified') "
            f"   AND final_price IS NOT NULL "
            f"   AND final_price BETWEEN {FINAL_PRICE_MIN} AND {FINAL_PRICE_MAX}) "
            f"OR (action = 'rejected' AND ("
            f"   final_price IS NULL "
            f"   OR final_price BETWEEN {FINAL_PRICE_MIN} AND {FINAL_PRICE_MAX}))",
            name="ck_decision_price_matches_action",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"PricingDecision(id={self.id!r}, "
            f"recommendation_id={self.recommendation_id!r}, action={self.action!r})"
        )
