"""Persist idempotent point-in-time option IV observations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_option_iv_history"
down_revision: str | None = "0006_execution_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "option_iv_observations",
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("implied_volatility", sa.Numeric(18, 10), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_event_id", sa.String(128), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_event_id"),
        sa.UniqueConstraint("instrument_id", "observed_at", "source"),
    )
    op.create_index(
        "ix_option_iv_observations_instrument_id", "option_iv_observations", ["instrument_id"]
    )
    op.create_index(
        "ix_option_iv_observations_observed_at", "option_iv_observations", ["observed_at"]
    )


def downgrade() -> None:
    op.drop_table("option_iv_observations")
