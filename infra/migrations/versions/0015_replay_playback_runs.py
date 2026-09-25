"""Persist replay playback-run status and terminal evidence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_replay_playback_runs"
down_revision: str | None = "0014_replay_datasets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "replay_playback_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("candles_per_second", sa.Float(), nullable=False),
        sa.Column("maximum_steps", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("frames_emitted", sa.Integer(), nullable=False),
        sa.Column("resulting_version", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("expected_version >= 0", name="replay_run_expected_version_nonnegative"),
        sa.CheckConstraint("candles_per_second >= 0.1", name="replay_run_rate_minimum"),
        sa.CheckConstraint("candles_per_second <= 100", name="replay_run_rate_maximum"),
        sa.CheckConstraint("maximum_steps BETWEEN 1 AND 10000", name="replay_run_steps_bounded"),
        sa.CheckConstraint("frames_emitted >= 0", name="replay_run_frames_nonnegative"),
        sa.CheckConstraint(
            "outcome IN ('running', 'complete', 'stopped', 'step_limit', 'failed')",
            name="replay_run_outcome_valid",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["replay_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_replay_playback_runs_session_id", "replay_playback_runs", ["session_id"])
    op.create_index("ix_replay_playback_runs_outcome", "replay_playback_runs", ["outcome"])


def downgrade() -> None:
    op.drop_table("replay_playback_runs")
