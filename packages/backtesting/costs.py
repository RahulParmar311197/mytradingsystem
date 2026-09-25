"""Versioned India-market transaction cost formulas.

Rates are fractions of turnover (not percentages) and must be supplied from an
effective-dated, owner-approved schedule. Statutory rates are intentionally not
hard-coded as timeless constants.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from packages.domain.models import Side


class IndianMarketProduct(StrEnum):
    EQUITY_DELIVERY = "equity_delivery"
    EQUITY_INTRADAY = "equity_intraday"
    FUTURES = "futures"
    OPTIONS = "options"


@dataclass(frozen=True, slots=True)
class IndiaChargeSchedule:
    name: str
    effective_from: date
    product: IndianMarketProduct
    brokerage_rate: Decimal
    brokerage_cap_per_order: Decimal | None
    exchange_transaction_rate: Decimal
    sebi_turnover_rate: Decimal
    gst_rate: Decimal
    stt_buy_rate: Decimal
    stt_sell_rate: Decimal
    stamp_duty_buy_rate: Decimal
    ipft_rate: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("charge schedule name cannot be empty")
        rates = (
            self.brokerage_rate,
            self.exchange_transaction_rate,
            self.sebi_turnover_rate,
            self.gst_rate,
            self.stt_buy_rate,
            self.stt_sell_rate,
            self.stamp_duty_buy_rate,
            self.ipft_rate,
        )
        if any(rate < 0 for rate in rates):
            raise ValueError("charge rates cannot be negative")
        if self.brokerage_cap_per_order is not None and self.brokerage_cap_per_order < 0:
            raise ValueError("brokerage cap cannot be negative")


@dataclass(frozen=True, slots=True)
class ChargeBreakdown:
    turnover: Decimal
    brokerage: Decimal
    exchange_transaction_charge: Decimal
    sebi_charge: Decimal
    ipft_charge: Decimal
    gst: Decimal
    stt: Decimal
    stamp_duty: Decimal
    total: Decimal


@dataclass(frozen=True, slots=True)
class IndiaCostModel:
    schedule: IndiaChargeSchedule

    def breakdown(self, notional: Decimal, side: Side) -> ChargeBreakdown:
        if notional < 0:
            raise ValueError("notional cannot be negative")
        brokerage = notional * self.schedule.brokerage_rate
        if self.schedule.brokerage_cap_per_order is not None:
            brokerage = min(brokerage, self.schedule.brokerage_cap_per_order)
        exchange = notional * self.schedule.exchange_transaction_rate
        sebi = notional * self.schedule.sebi_turnover_rate
        ipft = notional * self.schedule.ipft_rate
        gst = (brokerage + exchange + sebi + ipft) * self.schedule.gst_rate
        stt_rate = self.schedule.stt_buy_rate if side is Side.BUY else self.schedule.stt_sell_rate
        stt = notional * stt_rate
        stamp = notional * self.schedule.stamp_duty_buy_rate if side is Side.BUY else Decimal(0)
        total = brokerage + exchange + sebi + ipft + gst + stt + stamp
        return ChargeBreakdown(notional, brokerage, exchange, sebi, ipft, gst, stt, stamp, total)

    def calculate(self, notional: Decimal, side: Side) -> Decimal:
        return self.breakdown(notional, side).total
