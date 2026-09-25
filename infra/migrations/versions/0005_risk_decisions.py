"""Persist final independent risk decisions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_risk_decisions"
down_revision: str | None = "0004_paper_accounting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_decisions",
        sa.Column("order_intent_id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("approved_quantity", sa.Numeric(28, 8), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
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
        sa.ForeignKeyConstraint(["account_id"], ["trading_accounts.id"]),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_intent_id"),
    )
    op.create_index("ix_risk_decisions_order_intent_id", "risk_decisions", ["order_intent_id"])
    op.create_index("ix_risk_decisions_account_id", "risk_decisions", ["account_id"])
    op.create_index("ix_risk_decisions_instrument_id", "risk_decisions", ["instrument_id"])


def downgrade() -> None:
    op.drop_table("risk_decisions")
