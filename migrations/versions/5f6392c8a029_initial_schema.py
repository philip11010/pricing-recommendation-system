"""Initial schema: the mentor-facing pricing tables, and the earlier
prototype's two tables under their legacy names.

The prototype dashboard owned tables called "recommendations" and "decisions"
with a different shape. The mentor-facing API needs those names for its own
tables, so the prototype's are created here as "legacy_recommendations" and
"legacy_decisions". A database that already holds the prototype's tables under
the old names is not upgraded in place: rename or drop them first, or start
from an empty database.

Revision identifier: initial schema

Revision ID: 5f6392c8a029
Revises: none, this is the first revision
Create Date: 2026-11-03 07:09:24.441100+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# The tables use the project's UTC-aware DateTime, referred to below by its
# full path, so the module that defines it has to be imported.
import src.db.models  # noqa: F401

revision: str = "5f6392c8a029"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "legacy_recommendations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", src.db.models.UtcDateTime(timezone=True), nullable=False
        ),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("predicted_price", sa.Float(), nullable=False),
        sa.Column("data_source", sa.String(length=200), nullable=False),
        sa.CheckConstraint(
            "predicted_price > 0", name="ck_recommendation_price_positive"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("legacy_recommendations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_legacy_recommendations_created_at"),
            ["created_at"],
            unique=False,
        )

    op.create_table(
        "mentors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("headline", sa.String(length=300), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("education_level", sa.String(length=60), nullable=True),
        sa.Column("experience_summary", sa.Text(), nullable=True),
        sa.Column("credentials", sa.Text(), nullable=True),
        sa.Column("years_mentoring_band", sa.String(length=20), nullable=False),
        sa.Column("services_planned", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", src.db.models.UtcDateTime(timezone=True), nullable=False
        ),
        sa.CheckConstraint(
            "services_planned BETWEEN 1 AND 4", name="ck_mentor_services_planned"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    with op.batch_alter_table("mentors", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_mentors_created_at"), ["created_at"], unique=False
        )

    op.create_table(
        "legacy_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recommendation_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("final_price", sa.Float(), nullable=True),
        sa.Column(
            "decided_at", src.db.models.UtcDateTime(timezone=True), nullable=False
        ),
        sa.CheckConstraint(
            "(action IN ('accept', 'modify')    AND final_price IS NOT NULL AND final_price > 0) OR (action = 'reject' AND final_price IS NULL)",
            name="ck_decision_price_matches_action",
        ),
        sa.CheckConstraint(
            "action IN ('accept', 'modify', 'reject')", name="ck_decision_action"
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"], ["legacy_recommendations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("legacy_decisions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_legacy_decisions_decided_at"), ["decided_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_legacy_decisions_recommendation_id"),
            ["recommendation_id"],
            unique=False,
        )

    op.create_table(
        "mentor_history",
        sa.Column("mentor_id", sa.Integer(), nullable=False),
        sa.Column("top_mentor", sa.Boolean(), nullable=True),
        sa.Column("total_reviews", sa.Integer(), nullable=True),
        sa.Column("reviews_last_year", sa.Integer(), nullable=True),
        sa.Column("reviews_per_month", sa.Float(), nullable=True),
        sa.Column("reviews_last_90d", sa.Integer(), nullable=True),
        sa.Column("reviews_last_180d", sa.Integer(), nullable=True),
        sa.Column("reviews_last_365d", sa.Integer(), nullable=True),
        sa.Column("days_since_last_review", sa.Integer(), nullable=True),
        sa.Column("review_growth", sa.Float(), nullable=True),
        sa.Column("first_review_age_years", sa.Float(), nullable=True),
        sa.Column("has_no_reviews", sa.Boolean(), nullable=True),
        sa.Column("rating_overall", sa.Float(), nullable=True),
        sa.Column("rating_accuracy", sa.Float(), nullable=True),
        sa.Column("rating_preparation", sa.Float(), nullable=True),
        sa.Column("rating_punctuality", sa.Float(), nullable=True),
        sa.Column("rating_communication", sa.Float(), nullable=True),
        sa.Column("rating_relevance", sa.Float(), nullable=True),
        sa.Column("rating_value", sa.Float(), nullable=True),
        sa.Column("open_slots_365d", sa.Integer(), nullable=True),
        sa.Column("booked_rate_30d", sa.Float(), nullable=True),
        sa.Column("booked_rate_60d", sa.Float(), nullable=True),
        sa.Column("booked_rate_90d", sa.Float(), nullable=True),
        sa.Column("booked_rate_365d", sa.Float(), nullable=True),
        sa.Column("weekend_booked_rate_365d", sa.Float(), nullable=True),
        sa.Column("weekday_booked_rate_365d", sa.Float(), nullable=True),
        sa.Column("weekend_minus_weekday_booked_rate", sa.Float(), nullable=True),
        sa.Column("availability_blocks_365d", sa.Integer(), nullable=True),
        sa.Column("has_schedule_data", sa.Boolean(), nullable=True),
        sa.Column(
            "updated_at", src.db.models.UtcDateTime(timezone=True), nullable=False
        ),
        sa.ForeignKeyConstraint(["mentor_id"], ["mentors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("mentor_id"),
    )
    op.create_table(
        "services",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mentor_id", sa.Integer(), nullable=False),
        sa.Column("service_type", sa.String(length=30), nullable=False),
        sa.Column("field", sa.String(length=40), nullable=False),
        sa.Column("max_mentees", sa.Integer(), nullable=False),
        sa.Column("min_commitment", sa.Integer(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("profile_verified", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", src.db.models.UtcDateTime(timezone=True), nullable=False
        ),
        sa.CheckConstraint(
            "max_mentees BETWEEN 1 AND 16", name="ck_service_max_mentees"
        ),
        sa.CheckConstraint("min_commitment >= 1", name="ck_service_min_commitment"),
        sa.ForeignKeyConstraint(["mentor_id"], ["mentors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("services", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_services_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_services_mentor_id"), ["mentor_id"], unique=False
        )

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("model_used", sa.String(length=10), nullable=False),
        sa.Column("recommended_price", sa.Integer(), nullable=False),
        sa.Column("price_low", sa.Integer(), nullable=False),
        sa.Column("price_high", sa.Integer(), nullable=False),
        sa.Column("low_confidence", sa.Boolean(), nullable=False),
        sa.Column("inputs_snapshot", sa.JSON(), nullable=False),
        sa.Column("model_version", sa.String(length=60), nullable=False),
        sa.Column(
            "status", sa.String(length=10), server_default="pending", nullable=False
        ),
        sa.Column(
            "generated_at", src.db.models.UtcDateTime(timezone=True), nullable=False
        ),
        sa.CheckConstraint(
            "model_used IN ('core', 'full')", name="ck_recommendation_model"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'modified', 'rejected')",
            name="ck_recommendation_status",
        ),
        sa.CheckConstraint(
            "price_low <= recommended_price AND recommended_price <= price_high",
            name="ck_recommendation_price_within_range",
        ),
        sa.CheckConstraint(
            "recommended_price > 0 AND price_low > 0 AND price_high > 0",
            name="ck_recommendation_prices_positive",
        ),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("recommendations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_recommendations_generated_at"),
            ["generated_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_recommendations_service_id"), ["service_id"], unique=False
        )

    op.create_table(
        "decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recommendation_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("final_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column(
            "decided_at", src.db.models.UtcDateTime(timezone=True), nullable=False
        ),
        sa.CheckConstraint(
            "(action IN ('accepted', 'modified')    AND final_price IS NOT NULL AND final_price > 0) OR (action = 'rejected' AND final_price IS NULL)",
            name="ck_decision_price_matches_action",
        ),
        sa.CheckConstraint(
            "action IN ('accepted', 'modified', 'rejected')", name="ck_decision_action"
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"], ["recommendations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("decisions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_decisions_decided_at"), ["decided_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_decisions_recommendation_id"),
            ["recommendation_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("decisions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_decisions_recommendation_id"))
        batch_op.drop_index(batch_op.f("ix_decisions_decided_at"))

    op.drop_table("decisions")
    with op.batch_alter_table("recommendations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_recommendations_service_id"))
        batch_op.drop_index(batch_op.f("ix_recommendations_generated_at"))

    op.drop_table("recommendations")
    with op.batch_alter_table("services", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_services_mentor_id"))
        batch_op.drop_index(batch_op.f("ix_services_created_at"))

    op.drop_table("services")
    op.drop_table("mentor_history")
    with op.batch_alter_table("legacy_decisions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_legacy_decisions_recommendation_id"))
        batch_op.drop_index(batch_op.f("ix_legacy_decisions_decided_at"))

    op.drop_table("legacy_decisions")
    with op.batch_alter_table("mentors", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_mentors_created_at"))

    op.drop_table("mentors")
    with op.batch_alter_table("legacy_recommendations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_legacy_recommendations_created_at"))

    op.drop_table("legacy_recommendations")
