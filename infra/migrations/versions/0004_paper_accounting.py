"""Add paper cash ledger and P&L snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_paper_accounting"
down_revision: str | None = "0003_paper_trading"
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
        "paper_account_ledgers",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("initial_cash", sa.Numeric(24, 8), nullable=False),
        sa.Column("cash_balance", sa.Numeric(24, 8), nullable=False),
        sa.Column("peak_equity", sa.Numeric(24, 8), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["account_id"], ["trading_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id"),
    )
    op.create_index("ix_paper_account_ledgers_account_id", "paper_account_ledgers", ["account_id"])
    op.create_table(
        "paper_pnl_snapshots",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cash", sa.Numeric(24, 8), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(24, 8), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(24, 8), nullable=False),
        sa.Column("equity", sa.Numeric(24, 8), nullable=False),
        sa.Column("gross_exposure", sa.Numeric(24, 8), nullable=False),
        sa.Column("net_exposure", sa.Numeric(24, 8), nullable=False),
        sa.Column("drawdown", sa.Numeric(16, 12), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["account_id"], ["trading_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_pnl_snapshots_account_id", "paper_pnl_snapshots", ["account_id"])
    op.create_index("ix_paper_pnl_snapshots_occurred_at", "paper_pnl_snapshots", ["occurred_at"])


def downgrade() -> None:
    op.drop_table("paper_pnl_snapshots")
    op.drop_table("paper_account_ledgers")
