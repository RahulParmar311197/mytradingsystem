"""Persist execution order state and immutable events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_execution_orders"
down_revision: str | None = "0005_risk_decisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "execution_orders",
        sa.Column("quantity", sa.Numeric(28, 8), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("filled_quantity", sa.Numeric(28, 8), nullable=False),
        sa.Column("broker_order_id", sa.String(128)),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reconciliation_reason", sa.String(64)),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "execution_order_events",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fill_quantity", sa.Numeric(28, 8), nullable=False),
        sa.Column("broker_order_id", sa.String(128)),
        sa.Column("resulting_version", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["order_id"], ["execution_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "event_id"),
    )
    op.create_index("ix_execution_order_events_order_id", "execution_order_events", ["order_id"])


def downgrade() -> None:
    op.drop_table("execution_order_events")
    op.drop_table("execution_orders")
