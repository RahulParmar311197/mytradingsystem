from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from packages.decision_engine import DecisionConfig, DecisionInputs, decide
from packages.domain.models import SignalAction
from packages.strategies import StrategySignal


def signal(action: SignalAction = SignalAction.LONG) -> StrategySignal:
    return StrategySignal(
        datetime(2026, 9, 18, 10, tzinfo=UTC),
        uuid4(),
        "trend_continuation",
        "1.0.0",
        action,
        Decimal("0.75"),
        {"fixture": True},
        (),
        Decimal("100") if action in (SignalAction.LONG, SignalAction.SHORT) else None,
        Decimal("98")
        if action is SignalAction.LONG
        else Decimal("102")
        if action is SignalAction.SHORT
        else None,
        (Decimal("104"),)
        if action is SignalAction.LONG
        else (Decimal("96"),)
        if action is SignalAction.SHORT
        else (),
        Decimal("0.005") if action in (SignalAction.LONG, SignalAction.SHORT) else Decimal(0),
        None,
        "fixture",
        "snapshot-1",
    )


def inputs(proposal: StrategySignal | None = None, **changes: Decimal | None) -> DecisionInputs:
    values: dict[str, Decimal | StrategySignal | None] = {
        "strategy_signal": proposal or signal(),
        "technical_score": Decimal("0.8"),
        "smc_ict_score": Decimal("0.8"),
        "regime_compatibility": Decimal("0.8"),
        "volume_score": Decimal("0.8"),
        "options_score": Decimal("0.8"),
        "data_quality_score": Decimal("0.9"),
        "risk_context_score": Decimal("0.8"),
        "ml_probability": None,
    }
    values.update(changes)
    return DecisionInputs(**values)  # type: ignore[arg-type]


def test_approved_direction_still_requires_independent_risk_approval() -> None:
    result = decide(inputs())
    assert result.action is SignalAction.LONG
    assert result.expected_risk_reward == Decimal("2")
    assert result.requires_risk_approval is True
    assert result.requested_risk_fraction == Decimal("0.005")
    assert result.data_snapshot_id == "snapshot-1"
    assert "ml" not in result.contributing_factors


def test_missing_ml_is_removed_and_remaining_weights_are_renormalized() -> None:
    without_ml = decide(inputs(data_quality_score=Decimal("0.8"))).confidence
    with_ml = decide(
        inputs(data_quality_score=Decimal("0.8"), ml_probability=Decimal("0.8"))
    ).confidence
    assert without_ml == Decimal("0.8")
    assert with_ml == Decimal("0.8")


def test_data_quality_and_confidence_fail_closed_to_no_trade() -> None:
    result = decide(inputs(data_quality_score=Decimal("0.5"), technical_score=Decimal("0.1")))
    assert result.action is SignalAction.NO_TRADE
    assert "DATA_QUALITY_BELOW_THRESHOLD" in result.rejection_reasons
    assert result.proposed_entry is None
    assert result.requested_risk_fraction == 0
    assert result.requires_risk_approval is False


def test_invalid_price_geometry_is_rejected() -> None:
    malformed = replace(signal(), proposed_stop=Decimal("101"))
    result = decide(inputs(malformed))
    assert result.action is SignalAction.NO_TRADE
    assert result.rejection_reasons == ("INVALID_PRICE_GEOMETRY",)


def test_strategy_no_trade_remains_common_decision_outcome() -> None:
    no_trade = replace(signal(SignalAction.NO_TRADE), rejection_reasons=("EVENT_RISK_LOCK",))
    result = decide(inputs(no_trade))
    assert result.action is SignalAction.NO_TRADE
    assert result.rejection_reasons == ("EVENT_RISK_LOCK", "STRATEGY_NO_TRADE")
    assert result.requires_risk_approval is False


def test_exit_and_hold_are_not_blocked_by_entry_thresholds() -> None:
    for action in (SignalAction.EXIT, SignalAction.HOLD):
        result = decide(
            inputs(signal(action), data_quality_score=Decimal("0"), technical_score=Decimal("0"))
        )
        assert result.action is action
        assert result.requires_risk_approval is False


def test_score_and_weight_configuration_validation() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        inputs(technical_score=Decimal("1.1"))
    with pytest.raises(ValueError, match="sum exactly to 1"):
        DecisionConfig(technical_weight=Decimal("0.3"))
