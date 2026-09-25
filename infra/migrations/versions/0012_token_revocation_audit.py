"""Add correlation evidence to API token revocations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_token_revocation_audit"
down_revision: str | None = "0011_api_token_revocations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "revoked_api_tokens",
        sa.Column(
            "correlation_id",
            sa.String(64),
            server_default="migration-unknown",
            nullable=False,
        ),
    )
    op.alter_column("revoked_api_tokens", "correlation_id", server_default=None)
    op.create_index(
        "ix_revoked_api_tokens_correlation_id", "revoked_api_tokens", ["correlation_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_revoked_api_tokens_correlation_id", table_name="revoked_api_tokens")
    op.drop_column("revoked_api_tokens", "correlation_id")
