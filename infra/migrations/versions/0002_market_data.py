"""Add instrument master and separate raw, normalized, and quality data."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_market_data"
down_revision: str | None = "0001_phase1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("exchange", sa.String(8), nullable=False),
        sa.Column("segment", sa.String(16), nullable=False),
        sa.Column("isin", sa.String(12)),
        sa.Column("tick_size", sa.Numeric(18, 8), nullable=False),
        sa.Column("lot_size", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_instruments"),
        sa.UniqueConstraint("exchange", "segment", "symbol", name="uq_instruments_exchange"),
    )
    op.create_table(
        "raw_candles",
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_event_id", sa.String(128), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timeframe_seconds", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instruments.id"], name="fk_raw_candles_instrument_id_instruments"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_raw_candles"),
        sa.UniqueConstraint("source", "source_event_id", name="uq_raw_candles_source"),
    )
    op.create_index("ix_raw_candles_instrument_id", "raw_candles", ["instrument_id"])
    op.create_table(
        "candles",
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timeframe_seconds", sa.Integer(), nullable=False),
        sa.Column("open", sa.Numeric(24, 8), nullable=False),
        sa.Column("high", sa.Numeric(24, 8), nullable=False),
        sa.Column("low", sa.Numeric(24, 8), nullable=False),
        sa.Column("close", sa.Numeric(24, 8), nullable=False),
        sa.Column("volume", sa.Numeric(28, 8), nullable=False),
        sa.Column("open_interest", sa.Numeric(28, 8)),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instruments.id"], name="fk_candles_instrument_id_instruments"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_candles"),
        sa.UniqueConstraint(
            "instrument_id", "event_timestamp", "timeframe_seconds", name="uq_candles_instrument_id"
        ),
    )
    op.create_index("ix_candles_instrument_id", "candles", ["instrument_id"])
    op.create_table(
        "market_data_quality_events",
        sa.Column("instrument_id", sa.Uuid()),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("raw_event_id", sa.String(128)),
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
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name="fk_market_data_quality_events_instrument_id_instruments",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_market_data_quality_events"),
        sa.UniqueConstraint(
            "raw_event_id", "code", name="uq_market_data_quality_events_raw_event_id"
        ),
    )
    op.create_index("ix_market_data_quality_events_code", "market_data_quality_events", ["code"])
    op.create_index(
        "ix_market_data_quality_events_event_timestamp",
        "market_data_quality_events",
        ["event_timestamp"],
    )
    op.create_index(
        "ix_market_data_quality_events_instrument_id",
        "market_data_quality_events",
        ["instrument_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_market_data_quality_events_instrument_id", table_name="market_data_quality_events"
    )
    op.drop_index(
        "ix_market_data_quality_events_event_timestamp", table_name="market_data_quality_events"
    )
    op.drop_index("ix_market_data_quality_events_code", table_name="market_data_quality_events")
    op.drop_table("market_data_quality_events")
    op.drop_index("ix_candles_instrument_id", table_name="candles")
    op.drop_table("candles")
    op.drop_index("ix_raw_candles_instrument_id", table_name="raw_candles")
    op.drop_table("raw_candles")
    op.drop_table("instruments")
