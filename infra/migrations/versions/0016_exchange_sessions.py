"""Persist operator supplied trading calendar sessions for causal weekly bars."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_exchange_sessions"
down_revision: str | None = "0015_replay_playback_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exchange_sessions",
        sa.Column("exchange", sa.String(8), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_trading_day", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("exchange", "session_date"),
    )


def downgrade() -> None:
    op.drop_table("exchange_sessions")
