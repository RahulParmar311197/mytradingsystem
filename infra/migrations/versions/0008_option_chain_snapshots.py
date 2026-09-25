"""Persist immutable normalized option-chain snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_option_chain_snapshots"
down_revision: str | None = "0007_option_iv_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "option_chain_snapshots",
        sa.Column("underlying_id", sa.Uuid(), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_event_id", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(["underlying_id"], ["instruments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_event_id"),
        sa.UniqueConstraint("underlying_id", "expiry", "observed_at", "source"),
    )
    op.create_index(
        "ix_option_chain_snapshots_underlying_id", "option_chain_snapshots", ["underlying_id"]
    )
    op.create_index("ix_option_chain_snapshots_expiry", "option_chain_snapshots", ["expiry"])
    op.create_index(
        "ix_option_chain_snapshots_observed_at", "option_chain_snapshots", ["observed_at"]
    )


def downgrade() -> None:
    op.drop_table("option_chain_snapshots")
