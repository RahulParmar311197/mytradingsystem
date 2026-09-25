"""Persist deterministic replay checkpoints with optimistic concurrency."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_replay_sessions"
down_revision: str | None = "0012_token_revocation_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "replay_sessions",
        sa.Column("dataset_sha256", sa.String(64), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("timeframe_seconds", sa.Integer(), nullable=False),
        sa.Column("next_index", sa.Integer(), nullable=False),
        sa.Column("total_events", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("checkpointed_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.CheckConstraint("next_index >= 0", name="replay_next_index_nonnegative"),
        sa.CheckConstraint("total_events > 0", name="replay_total_events_positive"),
        sa.CheckConstraint("next_index <= total_events", name="replay_cursor_within_total"),
        sa.CheckConstraint("version >= 0", name="replay_version_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_replay_sessions_instrument_id", "replay_sessions", ["instrument_id"])
    op.create_index("ix_replay_sessions_checkpointed_at", "replay_sessions", ["checkpointed_at"])


def downgrade() -> None:
    op.drop_table("replay_sessions")
