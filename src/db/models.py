"""
Persistence schema: recommendations and the mentor's decision on each.

Two tables, mirroring the advisory design. A ``recommendations`` row records
what the model said and the exact input it said it about. A ``decisions`` row
records what the mentor did with that advice. Keeping them apart is the point
of the system: the model never sets a price, so its output and the human
response to it are separate facts.

``input_json`` stores the validated input verbatim rather than one column per
feature. The feature list is an experimental variable and will change; a
migration per feature would be churn for no gain, and the row only ever needs
to be read back whole, for audit.

Constraints are declared at the database level as well as in the Pydantic
request models, so a row cannot become inconsistent through a code path that
bypasses the API.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# The mentor's three options. "modify" carries a replacement price, "reject"
# carries none, "accept" copies the recommended price.
DECISION_ACTIONS: tuple[str, ...] = ("accept", "modify", "reject")


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp, used as the default for both tables."""
    return datetime.now(UTC)


class UtcDateTime(TypeDecorator):
    """
    A ``DateTime`` that is always UTC-aware in Python.

    SQLite has no timezone type, so a value written as UTC-aware comes back
    naive. A naive datetime that happens to be UTC is a trap: comparing it to
    ``datetime.now(UTC)`` raises, and comparing it to a local naive timestamp
    silently gives the wrong answer. Rather than leave that to every caller,
    values are normalised to UTC on the way in and re-tagged as UTC on the way
    out, so the attribute is aware regardless of backend.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetimes are ambiguous; pass a UTC-aware value")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class Base(DeclarativeBase):
    """Declarative base for every table in the application."""


class Recommendation(Base):
    """One advisory price produced by the model for one set of inputs."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow, nullable=False, index=True
    )
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    predicted_price: Mapped[float] = mapped_column(Float, nullable=False)
    # Recorded per row rather than assumed, so a later run against the real
    # platform dataset is distinguishable from a proxy-trained prediction.
    data_source: Mapped[str] = mapped_column(String(200), nullable=False)

    decisions: Mapped[list[Decision]] = relationship(
        back_populates="recommendation",
        cascade="all, delete-orphan",
        order_by="Decision.decided_at",
    )

    __table_args__ = (
        CheckConstraint("predicted_price > 0", name="ck_recommendation_price_positive"),
    )

    def __repr__(self) -> str:
        return (
            f"Recommendation(id={self.id!r}, model_name={self.model_name!r}, "
            f"predicted_price={self.predicted_price!r})"
        )


class Decision(Base):
    """What the mentor did with one recommendation."""

    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(
        ForeignKey("recommendations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    # Null for "reject": the mentor kept their own price and told us nothing
    # about what it is.
    final_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=utcnow, nullable=False, index=True
    )

    recommendation: Mapped[Recommendation] = relationship(back_populates="decisions")

    __table_args__ = (
        CheckConstraint(
            "action IN ('accept', 'modify', 'reject')", name="ck_decision_action"
        ),
        # A modification without a price is not a modification, and a
        # rejection with one would contradict the column comment above.
        #
        # Every branch tests final_price for NULL explicitly. A bare
        # "final_price > 0" against NULL evaluates to NULL, not FALSE, and a
        # CHECK constraint only rejects a row on FALSE, so the comparison
        # alone would let a price-less "modify" row through.
        CheckConstraint(
            "(action IN ('accept', 'modify') "
            "   AND final_price IS NOT NULL AND final_price > 0) "
            "OR (action = 'reject' AND final_price IS NULL)",
            name="ck_decision_price_matches_action",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"Decision(id={self.id!r}, recommendation_id={self.recommendation_id!r}, "
            f"action={self.action!r}, final_price={self.final_price!r})"
        )
