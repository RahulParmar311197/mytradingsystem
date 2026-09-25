from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from packages.backtesting import (
    IndiaChargeSchedule,
    IndiaCostModel,
    IndianMarketProduct,
)
from packages.domain.models import Side


def schedule() -> IndiaChargeSchedule:
    """Synthetic rates verify formulas; they are not represented as current statutory rates."""
    return IndiaChargeSchedule(
        name="test-schedule-2026-01-01",
        effective_from=date(2026, 1, 1),
        product=IndianMarketProduct.EQUITY_INTRADAY,
        brokerage_rate=Decimal("0.0003"),
        brokerage_cap_per_order=Decimal("20"),
        exchange_transaction_rate=Decimal("0.0000345"),
        sebi_turnover_rate=Decimal("0.000001"),
        gst_rate=Decimal("0.18"),
        stt_buy_rate=Decimal(0),
        stt_sell_rate=Decimal("0.001"),
        stamp_duty_buy_rate=Decimal("0.00015"),
        ipft_rate=Decimal("0.000001"),
    )


def test_charge_breakdown_applies_side_specific_taxes_and_brokerage_cap() -> None:
    model = IndiaCostModel(schedule())
    buy = model.breakdown(Decimal("100000"), Side.BUY)
    sell = model.breakdown(Decimal("100000"), Side.SELL)
    assert buy.brokerage == Decimal("20")
    assert buy.exchange_transaction_charge == Decimal("3.4500000")
    assert buy.sebi_charge == Decimal("0.100000")
    assert buy.ipft_charge == Decimal("0.100000")
    assert buy.gst == Decimal("4.257000000")
    assert buy.stt == 0
    assert buy.stamp_duty == Decimal("15.00000")
    assert buy.total == Decimal("42.907000000")
    assert sell.stt == Decimal("100.000")
    assert sell.stamp_duty == 0
    assert sell.total == Decimal("127.907000000")


def test_charge_schedule_rejects_unsafe_rates_and_negative_notional() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        replace(schedule(), brokerage_rate=Decimal("-0.1"))
    with pytest.raises(ValueError, match="notional"):
        IndiaCostModel(schedule()).calculate(Decimal("-1"), Side.BUY)
