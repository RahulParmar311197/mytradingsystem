"""Operational heartbeat and a fail-closed initial kill switch."""

import sqlalchemy as sa
from alembic import op

revision = "0003_operations"
down_revision = "0002_market_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_heartbeats",
        sa.Column("service", sa.String(64), primary_key=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("healthy", sa.Boolean(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    op.execute(
        sa.text(
            "INSERT INTO safety_state (key, enabled, reason, updated_at, correlation_id) "
            "SELECT 'kill_switch', true, 'Initial installation: entries locked', "
            "CURRENT_TIMESTAMP, 'migration-0003' "
            "WHERE NOT EXISTS (SELECT 1 FROM safety_state WHERE key = 'kill_switch')"
        )
    )


def downgrade() -> None:
    # Preserve the kill switch during a rollback.
    op.drop_table("service_heartbeats")
