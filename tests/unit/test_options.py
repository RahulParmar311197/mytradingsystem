from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from packages.domain.models import (
    Exchange,
    Greeks,
    Instrument,
    MarketSegment,
    OptionChain,
    OptionChainEntry,
    OptionContract,
    OptionType,
    Quote,
)
from packages.options import (
    ExpirySelectionCriteria,
    GreekTolerances,
    ImpliedVolatilityObservation,
    LiquidityCriteria,
    OptionLeg,
    OptionMarginConfig,
    OptionPositionRisk,
    aggregate_portfolio_greeks,
    analyze_black_scholes,
    compare_broker_greeks,
    estimate_option_margin,
    implied_volatility,
    implied_volatility_percentile,
    liquid_contracts,
    max_pain,
    payoff_at_expiry,
    put_call_ratio,
    select_contract_across_expiries,
    select_contract_by_delta,
)

NOW = datetime(2026, 9, 19, 5, tzinfo=UTC)
UNDERLYING = uuid4()


def entry(
    option_type: OptionType,
    strike: str,
    open_interest: str,
    *,
    timestamp: datetime = NOW,
    bid: str = "10",
    ask: str = "10.1",
    greeks: Greeks | None = None,
) -> OptionChainEntry:
    instrument = Instrument(
        symbol=f"NIFTY-{strike}-{option_type.value}",
        exchange=Exchange.NSE,
        segment=MarketSegment.OPTIONS,
        tick_size=Decimal("0.05"),
        lot_size=25,
    )
    contract = OptionContract(
        instrument=instrument,
        underlying_id=UNDERLYING,
        expiry=date(2026, 9, 24),
        strike=Decimal(strike),
        option_type=option_type,
    )
    return OptionChainEntry(
        contract=contract,
        quote=Quote(
            instrument_id=instrument.id,
            timestamp=timestamp,
            bid=Decimal(bid),
            ask=Decimal(ask),
            bid_quantity=Decimal(100),
            ask_quantity=Decimal(100),
        ),
        open_interest=Decimal(open_interest),
        change_in_open_interest=Decimal(0),
        volume=Decimal(1000),
        greeks=greeks,
    )


def chain(
    entries: tuple[OptionChainEntry, ...],
    *,
    expiry: date = date(2026, 9, 24),
    timestamp: datetime = NOW,
) -> OptionChain:
    return OptionChain(
        underlying_id=UNDERLYING,
        expiry=expiry,
        timestamp=timestamp,
        entries=tuple(
            item.model_copy(
                update={"contract": item.contract.model_copy(update={"expiry": expiry})}
            )
            for item in entries
        ),
    )


def test_black_scholes_reference_values_and_iv_round_trip() -> None:
    result = analyze_black_scholes(
        OptionType.CALL,
        Decimal(100),
        Decimal(100),
        Decimal(1),
        Decimal("0.05"),
        Decimal("0.2"),
    )
    assert float(result.price) == pytest.approx(10.4506, abs=0.0001)
    assert float(result.delta) == pytest.approx(0.6368, abs=0.0001)
    assert float(result.gamma) == pytest.approx(0.01876, abs=0.00001)
    assert float(result.theta) == pytest.approx(-6.414, abs=0.001)
    assert float(result.vega) == pytest.approx(37.524, abs=0.001)
    assert float(result.rho) == pytest.approx(53.232, abs=0.001)
    solved = implied_volatility(
        result.price,
        OptionType.CALL,
        Decimal(100),
        Decimal(100),
        Decimal(1),
        Decimal("0.05"),
    )
    assert float(solved) == pytest.approx(0.2, abs=0.000001)


def test_chain_pcr_max_pain_and_liquidity_gate() -> None:
    entries = (
        entry(OptionType.CALL, "90", "10"),
        entry(OptionType.CALL, "100", "20"),
        entry(OptionType.PUT, "90", "30"),
        entry(
            OptionType.PUT,
            "100",
            "40",
            timestamp=NOW - timedelta(seconds=31),
            bid="9",
            ask="11",
        ),
    )
    option_chain = chain(entries)
    assert put_call_ratio(option_chain) == Decimal(70) / Decimal(30)
    assert max_pain(option_chain) == Decimal(100)
    liquid = liquid_contracts(
        option_chain,
        NOW,
        LiquidityCriteria(Decimal(100), Decimal(5), Decimal(200), 30),
    )
    assert liquid == entries[:3]


def test_multi_leg_expiry_payoff_is_deterministic() -> None:
    result = payoff_at_expiry(
        (OptionLeg(OptionType.CALL, Decimal(100), Decimal(1), Decimal(5)),),
        (Decimal(90), Decimal(100), Decimal(110)),
    )
    assert tuple(item.gross_payoff for item in result) == (
        Decimal(-5),
        Decimal(-5),
        Decimal(5),
    )


def test_portfolio_greeks_scale_by_signed_lots_and_keep_gross_exposure() -> None:
    greeks = Greeks(
        delta=Decimal("0.5"),
        gamma=Decimal("0.02"),
        theta=Decimal("-3"),
        vega=Decimal("10"),
        rho=Decimal("4"),
        implied_volatility=Decimal("0.2"),
        calculated_at=NOW,
    )
    risk = aggregate_portfolio_greeks(
        (
            OptionPositionRisk(Decimal(2), 25, Decimal(10), greeks),
            OptionPositionRisk(Decimal(-1), 25, Decimal(8), greeks),
        )
    )
    assert risk.gross_options_exposure == Decimal(700)
    assert risk.delta == Decimal("12.5")
    assert risk.gamma == Decimal("0.50")
    assert risk.theta == Decimal(-75)
    assert risk.vega == Decimal(250)
    assert risk.rho == Decimal(100)


def test_invalid_iv_price_and_empty_chain_fail_closed() -> None:
    with pytest.raises(ValueError, match="outside solvable"):
        implied_volatility(
            Decimal(200),
            OptionType.CALL,
            Decimal(100),
            Decimal(100),
            Decimal(1),
            Decimal("0.05"),
        )
    with pytest.raises(ValueError, match="requires"):
        max_pain(chain(()))


def test_chain_identity_and_snapshot_time_fail_closed() -> None:
    valid = entry(OptionType.CALL, "100", "20")
    wrong_underlying = valid.model_copy(
        update={"contract": valid.contract.model_copy(update={"underlying_id": uuid4()})}
    )
    with pytest.raises(ValueError, match="chain identity"):
        put_call_ratio(chain((wrong_underlying,)))

    future_quote = valid.model_copy(
        update={"quote": valid.quote.model_copy(update={"timestamp": NOW + timedelta(seconds=1)})}
    )
    with pytest.raises(ValueError, match="future quote"):
        liquid_contracts(
            chain((future_quote,)),
            NOW,
            LiquidityCriteria(Decimal(0), Decimal(0), Decimal(200), 30),
        )


def test_iv_percentile_is_point_in_time_and_requires_history() -> None:
    history = (
        *(
            ImpliedVolatilityObservation(NOW - timedelta(days=day), Decimal(day) / 100)
            for day in range(1, 6)
        ),
        ImpliedVolatilityObservation(NOW + timedelta(days=1), Decimal("0.01")),
    )
    result = implied_volatility_percentile(Decimal("0.03"), history, NOW, minimum_observations=5)
    assert result.percentile == Decimal(60)
    assert result.observation_count == 5
    with pytest.raises(ValueError, match="insufficient"):
        implied_volatility_percentile(
            Decimal("0.03"), history, NOW - timedelta(days=3), minimum_observations=4
        )


def test_broker_greek_comparison_reports_tolerance_breaches_and_staleness() -> None:
    calculated = analyze_black_scholes(
        OptionType.CALL, Decimal(100), Decimal(100), Decimal(1), Decimal("0.05"), Decimal("0.2")
    )
    broker = Greeks(
        delta=calculated.delta + Decimal("0.02"),
        gamma=calculated.gamma,
        theta=calculated.theta,
        vega=calculated.vega,
        rho=calculated.rho,
        implied_volatility=Decimal("0.2"),
        calculated_at=NOW - timedelta(seconds=1),
        model="broker",
    )
    tolerances = GreekTolerances(
        Decimal("0.01"),
        Decimal("0.001"),
        Decimal("0.1"),
        Decimal("0.1"),
        Decimal("0.1"),
        Decimal("0.01"),
        5,
    )
    comparison = compare_broker_greeks(broker, calculated, Decimal("0.2"), NOW, tolerances)
    assert comparison.matches is False
    assert comparison.exceeded_tolerances == ("delta",)
    with pytest.raises(ValueError, match="stale"):
        compare_broker_greeks(
            broker.model_copy(update={"calculated_at": NOW - timedelta(seconds=6)}),
            calculated,
            Decimal("0.2"),
            NOW,
            tolerances,
        )


def test_delta_selection_requires_liquidity_and_greek_evidence() -> None:
    def greek(delta: str) -> Greeks:
        return Greeks(
            delta=Decimal(delta),
            gamma=Decimal("0.01"),
            theta=Decimal("-1"),
            vega=Decimal(5),
            rho=Decimal(2),
            implied_volatility=Decimal("0.2"),
            calculated_at=NOW,
        )

    candidates = (
        entry(OptionType.CALL, "100", "50", greeks=greek("0.55")),
        entry(OptionType.CALL, "110", "50", greeks=greek("0.31")),
        entry(OptionType.PUT, "100", "50", greeks=greek("-0.30")),
    )
    selected = select_contract_by_delta(
        chain(candidates),
        OptionType.CALL,
        Decimal("0.30"),
        NOW,
        LiquidityCriteria(Decimal(100), Decimal(5), Decimal(200), 30),
    )
    assert selected.contract.strike == Decimal(110)


def test_expiry_selection_uses_ist_date_and_configured_preference() -> None:
    greeks = Greeks(
        delta=Decimal("0.30"),
        gamma=Decimal("0.01"),
        theta=Decimal("-1"),
        vega=Decimal(5),
        rho=Decimal(2),
        implied_volatility=Decimal("0.2"),
        calculated_at=NOW,
    )
    near = chain((entry(OptionType.CALL, "100", "50", greeks=greeks),))
    far = chain((entry(OptionType.CALL, "110", "50", greeks=greeks),), expiry=date(2026, 10, 1))
    liquidity = LiquidityCriteria(Decimal(100), Decimal(5), Decimal(200), 30)
    nearest = select_contract_across_expiries(
        (far, near),
        OptionType.CALL,
        Decimal("0.30"),
        NOW,
        liquidity,
        ExpirySelectionCriteria(1, 20),
    )
    assert nearest.contract.expiry == date(2026, 9, 24)
    farthest = select_contract_across_expiries(
        (near, far),
        OptionType.CALL,
        Decimal("0.30"),
        NOW,
        liquidity,
        ExpirySelectionCriteria(1, 20, prefer_nearest_expiry=False),
    )
    assert farthest.contract.expiry == date(2026, 10, 1)


def test_expiry_selection_rejects_future_chain_snapshot() -> None:
    future = chain((), timestamp=NOW + timedelta(seconds=1))
    with pytest.raises(ValueError, match="future chain"):
        select_contract_across_expiries(
            (future,),
            OptionType.CALL,
            Decimal("0.30"),
            NOW,
            LiquidityCriteria(Decimal(0), Decimal(0), Decimal(200), 30),
            ExpirySelectionCriteria(0, 30),
        )


def test_option_margin_estimate_exposes_scenarios_and_short_floor() -> None:
    config = OptionMarginConfig((Decimal("-0.10"), Decimal(0), Decimal("0.10")), Decimal("0.15"))
    short_call = estimate_option_margin(
        (OptionLeg(OptionType.CALL, Decimal(100), Decimal(-1), Decimal(5)),),
        Decimal(100),
        config,
    )
    assert short_call.premium_outlay == 0
    assert short_call.maximum_scenario_loss == Decimal(5)
    assert short_call.short_notional_floor == Decimal(15)
    assert short_call.required_margin == Decimal(15)
    assert short_call.scenario_losses == (
        (Decimal("-0.10"), Decimal(0)),
        (Decimal(0), Decimal(0)),
        (Decimal("0.10"), Decimal(5)),
    )

    long_call = estimate_option_margin(
        (OptionLeg(OptionType.CALL, Decimal(100), Decimal(2), Decimal(5)),),
        Decimal(100),
        config,
    )
    assert long_call.required_margin == Decimal(10)
    assert long_call.premium_outlay == Decimal(10)


def test_option_margin_configuration_fails_closed() -> None:
    with pytest.raises(ValueError, match="greater than -1"):
        OptionMarginConfig((Decimal(-1),), Decimal("0.15"))
