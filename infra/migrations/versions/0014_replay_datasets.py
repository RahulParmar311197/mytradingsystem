"""Persist immutable content-addressed replay candle datasets."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_replay_datasets"
down_revision: str | None = "0013_replay_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "replay_datasets",
        sa.Column("dataset_sha256", sa.String(64), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("timeframe_seconds", sa.Integer(), nullable=False),
        sa.Column("total_events", sa.Integer(), nullable=False),
        sa.Column("first_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("candles", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("timeframe_seconds > 0", name="replay_dataset_timeframe_positive"),
        sa.CheckConstraint("total_events > 0", name="replay_dataset_total_positive"),
        sa.PrimaryKeyConstraint("dataset_sha256"),
    )
    op.create_index("ix_replay_datasets_instrument_id", "replay_datasets", ["instrument_id"])


def downgrade() -> None:
    op.drop_table("replay_datasets")
