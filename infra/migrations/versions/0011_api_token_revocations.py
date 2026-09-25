"""Persist API token revocations without retaining token plaintext."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_api_token_revocations"
down_revision: str | None = "0010_ml_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "revoked_api_tokens",
        sa.Column("token_sha256", sa.String(64), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(512), nullable=False),
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
        sa.UniqueConstraint("token_sha256"),
    )
    op.create_index(
        "ix_revoked_api_tokens_token_sha256",
        "revoked_api_tokens",
        ["token_sha256"],
        unique=True,
    )
    op.create_index("ix_revoked_api_tokens_revoked_at", "revoked_api_tokens", ["revoked_at"])


def downgrade() -> None:
    op.drop_table("revoked_api_tokens")
