"""Add persistent paper orders, fills, positions, and lifecycle events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_paper_trading"
down_revision: str | None = "0002_market_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column[object], sa.Column[object], sa.Column[object]]:
    return (
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
    )


def upgrade() -> None:
    op.create_table(
        "paper_orders",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("intent_id", sa.Uuid(), nullable=False),
        sa.Column("risk_decision_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("order_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 8), nullable=False),
        sa.Column("filled_quantity", sa.Numeric(28, 8), nullable=False),
        sa.Column("average_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("charges", sa.Numeric(24, 8), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["account_id"], ["trading_accounts.id"]),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "idempotency_key"),
    )
    op.create_index("ix_paper_orders_account_id", "paper_orders", ["account_id"])
    op.create_index("ix_paper_orders_instrument_id", "paper_orders", ["instrument_id"])
    op.create_table(
        "paper_fills",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 8), nullable=False),
        sa.Column("price", sa.Numeric(24, 8), nullable=False),
        sa.Column("charges", sa.Numeric(24, 8), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["order_id"], ["paper_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_fills_order_id", "paper_fills", ["order_id"])
    op.create_table(
        "paper_positions",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 8), nullable=False),
        sa.Column("average_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(24, 8), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["account_id"], ["trading_accounts.id"]),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "instrument_id"),
    )
    op.create_index("ix_paper_positions_account_id", "paper_positions", ["account_id"])
    op.create_index("ix_paper_positions_instrument_id", "paper_positions", ["instrument_id"])
    op.create_table(
        "paper_order_events",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["order_id"], ["paper_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_order_events_order_id", "paper_order_events", ["order_id"])


def downgrade() -> None:
    op.drop_table("paper_order_events")
    op.drop_table("paper_positions")
    op.drop_table("paper_fills")
    op.drop_table("paper_orders")
