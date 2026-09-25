"""Black-Scholes baseline and transparent option-chain analytics."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from math import erf, exp, log, pi, sqrt
from zoneinfo import ZoneInfo

from packages.domain.models import Greeks, OptionChain, OptionChainEntry, OptionType


@dataclass(frozen=True, slots=True)
class BlackScholesResult:
    price: Decimal
    delta: Decimal
    gamma: Decimal
    theta: Decimal
    vega: Decimal
    rho: Decimal


@dataclass(frozen=True, slots=True)
class LiquidityCriteria:
    minimum_volume: Decimal
    minimum_open_interest: Decimal
    maximum_spread_bps: Decimal
    maximum_quote_age_seconds: int

    def __post_init__(self) -> None:
        if min(self.minimum_volume, self.minimum_open_interest, self.maximum_spread_bps) < 0:
            raise ValueError("liquidity thresholds cannot be negative")
        if self.maximum_quote_age_seconds <= 0:
            raise ValueError("maximum quote age must be positive")


@dataclass(frozen=True, slots=True)
class OptionLeg:
    option_type: OptionType
    strike: Decimal
    quantity: Decimal
    premium: Decimal

    def __post_init__(self) -> None:
        if self.strike <= 0 or self.premium < 0 or self.quantity == 0:
            raise ValueError("invalid option leg")


@dataclass(frozen=True, slots=True)
class OptionPayoff:
    underlying_at_expiry: Decimal
    gross_payoff: Decimal


@dataclass(frozen=True, slots=True)
class OptionPositionRisk:
    """A signed option position and its current per-unit model inputs."""

    quantity: Decimal
    lot_size: int
    mark_price: Decimal
    greeks: Greeks

    def __post_init__(self) -> None:
        if self.quantity == 0 or self.lot_size <= 0 or self.mark_price < 0:
            raise ValueError("invalid option position risk input")


@dataclass(frozen=True, slots=True)
class PortfolioGreeks:
    gross_options_exposure: Decimal
    delta: Decimal
    gamma: Decimal
    theta: Decimal
    vega: Decimal
    rho: Decimal


@dataclass(frozen=True, slots=True)
class ImpliedVolatilityObservation:
    observed_at: datetime
    implied_volatility: Decimal

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("IV observation timestamp must be timezone-aware")
        if not self.implied_volatility.is_finite() or self.implied_volatility < 0:
            raise ValueError("implied volatility must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class ImpliedVolatilityPercentile:
    percentile: Decimal
    observation_count: int
    as_of: datetime


@dataclass(frozen=True, slots=True)
class GreekTolerances:
    delta: Decimal
    gamma: Decimal
    theta: Decimal
    vega: Decimal
    rho: Decimal
    implied_volatility: Decimal
    maximum_age_seconds: int

    def __post_init__(self) -> None:
        values = (self.delta, self.gamma, self.theta, self.vega, self.rho, self.implied_volatility)
        if any(not value.is_finite() or value < 0 for value in values):
            raise ValueError("Greek tolerances must be finite and non-negative")
        if self.maximum_age_seconds <= 0:
            raise ValueError("Greek maximum age must be positive")


@dataclass(frozen=True, slots=True)
class GreekComparison:
    absolute_differences: tuple[tuple[str, Decimal], ...]
    exceeded_tolerances: tuple[str, ...]

    @property
    def matches(self) -> bool:
        return not self.exceeded_tolerances


@dataclass(frozen=True, slots=True)
class ExpirySelectionCriteria:
    minimum_days_to_expiry: int
    maximum_days_to_expiry: int
    prefer_nearest_expiry: bool = True

    def __post_init__(self) -> None:
        if self.minimum_days_to_expiry < 0:
            raise ValueError("minimum days to expiry cannot be negative")
        if self.maximum_days_to_expiry < self.minimum_days_to_expiry:
            raise ValueError("maximum days to expiry cannot precede minimum")


@dataclass(frozen=True, slots=True)
class OptionMarginConfig:
    spot_shocks: tuple[Decimal, ...]
    short_notional_floor_fraction: Decimal
    model_version: str = "scenario-margin-v1"

    def __post_init__(self) -> None:
        if not self.model_version.strip() or not self.spot_shocks:
            raise ValueError("margin model version and spot shocks are required")
        if len(set(self.spot_shocks)) != len(self.spot_shocks):
            raise ValueError("margin spot shocks must be unique")
        if any(not shock.is_finite() or shock <= -1 for shock in self.spot_shocks):
            raise ValueError("margin spot shocks must be finite and greater than -1")
        if (
            not self.short_notional_floor_fraction.is_finite()
            or not Decimal(0) <= self.short_notional_floor_fraction <= 1
        ):
            raise ValueError("short notional floor fraction must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class OptionMarginEstimate:
    required_margin: Decimal
    premium_outlay: Decimal
    maximum_scenario_loss: Decimal
    short_notional_floor: Decimal
    scenario_losses: tuple[tuple[Decimal, Decimal], ...]
    model_version: str


def aggregate_portfolio_greeks(positions: tuple[OptionPositionRisk, ...]) -> PortfolioGreeks:
    """Aggregate signed Greeks and gross marked exposure using contract multipliers."""
    exposure = delta = gamma = theta = vega = rho = Decimal(0)
    for position in positions:
        units = position.quantity * position.lot_size
        exposure += abs(units) * position.mark_price
        delta += units * position.greeks.delta
        gamma += units * position.greeks.gamma
        theta += units * position.greeks.theta
        vega += units * position.greeks.vega
        rho += units * position.greeks.rho
    return PortfolioGreeks(exposure, delta, gamma, theta, vega, rho)


def implied_volatility_percentile(
    current: Decimal,
    observations: tuple[ImpliedVolatilityObservation, ...],
    as_of: datetime,
    *,
    minimum_observations: int = 20,
) -> ImpliedVolatilityPercentile:
    """Calculate an empirical percentile from observations available at ``as_of`` only."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("IV percentile timestamp must be timezone-aware")
    if not current.is_finite() or current < 0 or minimum_observations <= 0:
        raise ValueError("invalid IV percentile input")
    available = tuple(item for item in observations if item.observed_at <= as_of)
    timestamps = tuple(item.observed_at for item in available)
    if len(set(timestamps)) != len(timestamps):
        raise ValueError("IV history contains duplicate timestamps")
    if len(available) < minimum_observations:
        raise ValueError("insufficient point-in-time IV history")
    rank = sum(item.implied_volatility <= current for item in available)
    percentile = Decimal(rank) / Decimal(len(available)) * 100
    return ImpliedVolatilityPercentile(percentile, len(available), as_of)


def compare_broker_greeks(
    broker: Greeks,
    calculated: BlackScholesResult,
    calculated_iv: Decimal,
    as_of: datetime,
    tolerances: GreekTolerances,
) -> GreekComparison:
    """Compare broker Greeks with the internal baseline; stale/future evidence fails closed."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("Greek comparison timestamp must be timezone-aware")
    age = (as_of - broker.calculated_at).total_seconds()
    if age < 0 or age > tolerances.maximum_age_seconds:
        raise ValueError("broker Greeks are stale or from the future")
    pairs = (
        ("delta", broker.delta, calculated.delta, tolerances.delta),
        ("gamma", broker.gamma, calculated.gamma, tolerances.gamma),
        ("theta", broker.theta, calculated.theta, tolerances.theta),
        ("vega", broker.vega, calculated.vega, tolerances.vega),
        ("rho", broker.rho, calculated.rho, tolerances.rho),
        (
            "implied_volatility",
            broker.implied_volatility,
            calculated_iv,
            tolerances.implied_volatility,
        ),
    )
    if any(
        not value.is_finite() for _, actual, expected, _ in pairs for value in (actual, expected)
    ):
        raise ValueError("Greek comparison values must be finite")
    differences = tuple((name, abs(actual - expected)) for name, actual, expected, _ in pairs)
    exceeded = tuple(
        name for name, actual, expected, tolerance in pairs if abs(actual - expected) > tolerance
    )
    return GreekComparison(differences, exceeded)


def _normal_cdf(value: float) -> float:
    return (1.0 + erf(value / sqrt(2.0))) / 2.0


def _normal_pdf(value: float) -> float:
    return exp(-(value**2) / 2.0) / sqrt(2.0 * pi)


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))


def analyze_black_scholes(
    option_type: OptionType,
    spot: Decimal,
    strike: Decimal,
    time_to_expiry_years: Decimal,
    risk_free_rate: Decimal,
    volatility: Decimal,
    dividend_yield: Decimal = Decimal(0),
) -> BlackScholesResult:
    if min(spot, strike, time_to_expiry_years, volatility) <= 0:
        raise ValueError("spot, strike, time, and volatility must be positive")
    s, k, t, r, sigma, q = map(
        float, (spot, strike, time_to_expiry_years, risk_free_rate, volatility, dividend_yield)
    )
    root_t = sqrt(t)
    d1 = (log(s / k) + (r - q + sigma * sigma / 2.0) * t) / (sigma * root_t)
    d2 = d1 - sigma * root_t
    discount_r, discount_q = exp(-r * t), exp(-q * t)
    pdf = _normal_pdf(d1)
    gamma = discount_q * pdf / (s * sigma * root_t)
    vega = s * discount_q * pdf * root_t
    if option_type is OptionType.CALL:
        price = s * discount_q * _normal_cdf(d1) - k * discount_r * _normal_cdf(d2)
        delta = discount_q * _normal_cdf(d1)
        theta = (
            -(s * discount_q * pdf * sigma) / (2.0 * root_t)
            - r * k * discount_r * _normal_cdf(d2)
            + q * s * discount_q * _normal_cdf(d1)
        )
        rho = k * t * discount_r * _normal_cdf(d2)
    else:
        price = k * discount_r * _normal_cdf(-d2) - s * discount_q * _normal_cdf(-d1)
        delta = discount_q * (_normal_cdf(d1) - 1.0)
        theta = (
            -(s * discount_q * pdf * sigma) / (2.0 * root_t)
            + r * k * discount_r * _normal_cdf(-d2)
            - q * s * discount_q * _normal_cdf(-d1)
        )
        rho = -k * t * discount_r * _normal_cdf(-d2)
    return BlackScholesResult(*map(_decimal, (price, delta, gamma, theta, vega, rho)))


def implied_volatility(
    market_price: Decimal,
    option_type: OptionType,
    spot: Decimal,
    strike: Decimal,
    time_to_expiry_years: Decimal,
    risk_free_rate: Decimal,
    dividend_yield: Decimal = Decimal(0),
    *,
    tolerance: Decimal = Decimal("0.000001"),
    maximum_iterations: int = 100,
) -> Decimal:
    if market_price <= 0 or tolerance <= 0 or maximum_iterations <= 0:
        raise ValueError("market price, tolerance, and iterations must be positive")
    low, high = Decimal("0.000001"), Decimal("5")
    low_price = analyze_black_scholes(
        option_type, spot, strike, time_to_expiry_years, risk_free_rate, low, dividend_yield
    ).price
    high_price = analyze_black_scholes(
        option_type, spot, strike, time_to_expiry_years, risk_free_rate, high, dividend_yield
    ).price
    if not low_price <= market_price <= high_price:
        raise ValueError("market price is outside solvable Black-Scholes bounds")
    for _ in range(maximum_iterations):
        middle = (low + high) / 2
        price = analyze_black_scholes(
            option_type,
            spot,
            strike,
            time_to_expiry_years,
            risk_free_rate,
            middle,
            dividend_yield,
        ).price
        if abs(price - market_price) <= tolerance:
            return middle
        if price < market_price:
            low = middle
        else:
            high = middle
    raise ValueError("implied volatility did not converge")


def put_call_ratio(chain: OptionChain) -> Decimal | None:
    _validate_chain(chain)
    call_oi = sum(
        (
            entry.open_interest
            for entry in chain.entries
            if entry.contract.option_type is OptionType.CALL
        ),
        Decimal(0),
    )
    put_oi = sum(
        (
            entry.open_interest
            for entry in chain.entries
            if entry.contract.option_type is OptionType.PUT
        ),
        Decimal(0),
    )
    return put_oi / call_oi if call_oi > 0 else None


def max_pain(chain: OptionChain) -> Decimal:
    _validate_chain(chain)
    if not chain.entries:
        raise ValueError("max pain requires option-chain entries")
    strikes = sorted({entry.contract.strike for entry in chain.entries})
    pain: dict[Decimal, Decimal] = {}
    for settlement in strikes:
        total = Decimal(0)
        for entry in chain.entries:
            intrinsic = (
                max(settlement - entry.contract.strike, Decimal(0))
                if entry.contract.option_type is OptionType.CALL
                else max(entry.contract.strike - settlement, Decimal(0))
            )
            total += intrinsic * entry.open_interest
        pain[settlement] = total
    return min(strikes, key=lambda strike: (pain[strike], strike))


def _is_liquid(entry: OptionChainEntry, as_of: datetime, criteria: LiquidityCriteria) -> bool:
    quote = entry.quote
    age = (as_of - quote.timestamp).total_seconds()
    mid = (quote.bid + quote.ask) / 2
    spread_bps = (quote.ask - quote.bid) / mid * 10000
    return (
        0 <= age <= criteria.maximum_quote_age_seconds
        and entry.volume >= criteria.minimum_volume
        and entry.open_interest >= criteria.minimum_open_interest
        and spread_bps <= criteria.maximum_spread_bps
        and quote.bid_quantity > 0
        and quote.ask_quantity > 0
    )


def liquid_contracts(
    chain: OptionChain, as_of: datetime, criteria: LiquidityCriteria
) -> tuple[OptionChainEntry, ...]:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("liquidity timestamp must be timezone-aware")
    _validate_chain(chain)
    return tuple(entry for entry in chain.entries if _is_liquid(entry, as_of, criteria))


def select_contract_by_delta(
    chain: OptionChain,
    option_type: OptionType,
    target_absolute_delta: Decimal,
    as_of: datetime,
    criteria: LiquidityCriteria,
) -> OptionChainEntry:
    """Select the liquid, fresh contract closest to a target absolute delta."""
    if not target_absolute_delta.is_finite() or not Decimal(0) < target_absolute_delta <= 1:
        raise ValueError("target absolute delta must be in (0, 1]")
    candidates = tuple(
        entry
        for entry in liquid_contracts(chain, as_of, criteria)
        if entry.contract.option_type is option_type
        and entry.greeks is not None
        and 0
        <= (as_of - entry.greeks.calculated_at).total_seconds()
        <= criteria.maximum_quote_age_seconds
    )
    if not candidates:
        raise ValueError("no liquid contract with Greeks matches selection criteria")

    def rank(entry: OptionChainEntry) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        if entry.greeks is None:  # pragma: no cover - narrowed when candidates are built
            raise RuntimeError("contract selection lost Greek evidence")
        mid = (entry.quote.bid + entry.quote.ask) / 2
        spread_bps = (entry.quote.ask - entry.quote.bid) / mid * 10000
        return (
            abs(abs(entry.greeks.delta) - target_absolute_delta),
            spread_bps,
            -entry.open_interest,
            entry.contract.strike,
        )

    return min(candidates, key=rank)


def select_contract_across_expiries(
    chains: tuple[OptionChain, ...],
    option_type: OptionType,
    target_absolute_delta: Decimal,
    as_of: datetime,
    liquidity: LiquidityCriteria,
    expiry: ExpirySelectionCriteria,
) -> OptionChainEntry:
    """Select a contract from eligible expiries using the India-market calendar date."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("expiry selection timestamp must be timezone-aware")
    india_date = as_of.astimezone(ZoneInfo("Asia/Kolkata")).date()
    eligible: list[tuple[int, OptionChainEntry]] = []
    for chain in chains:
        if chain.timestamp > as_of:
            raise ValueError("expiry selection cannot use a future chain snapshot")
        days = (chain.expiry - india_date).days
        if not expiry.minimum_days_to_expiry <= days <= expiry.maximum_days_to_expiry:
            continue
        try:
            selected = select_contract_by_delta(
                chain, option_type, target_absolute_delta, as_of, liquidity
            )
        except ValueError as error:
            if str(error) != "no liquid contract with Greeks matches selection criteria":
                raise
            continue
        eligible.append((days, selected))
    if not eligible:
        raise ValueError("no eligible expiry contains a selectable contract")
    direction = 1 if expiry.prefer_nearest_expiry else -1
    return min(
        eligible,
        key=lambda item: (
            direction * item[0],
            abs(abs(item[1].greeks.delta) - target_absolute_delta)
            if item[1].greeks is not None
            else Decimal("Infinity"),
            item[1].contract.strike,
        ),
    )[1]


def _validate_chain(chain: OptionChain) -> None:
    for entry in chain.entries:
        if (
            entry.contract.underlying_id != chain.underlying_id
            or entry.contract.expiry != chain.expiry
        ):
            raise ValueError("option-chain contract mapping does not match chain identity")
        if entry.quote.instrument_id != entry.contract.instrument.id:
            raise ValueError("option quote does not match option contract instrument")
        if entry.quote.timestamp > chain.timestamp:
            raise ValueError("option-chain snapshot cannot contain a future quote")
        if entry.greeks is not None:
            values = (
                entry.greeks.delta,
                entry.greeks.gamma,
                entry.greeks.theta,
                entry.greeks.vega,
                entry.greeks.rho,
                entry.greeks.implied_volatility,
            )
            if entry.greeks.calculated_at > chain.timestamp:
                raise ValueError("option-chain snapshot cannot contain future Greeks")
            if any(not value.is_finite() for value in values):
                raise ValueError("option-chain Greeks must be finite")


def payoff_at_expiry(
    legs: tuple[OptionLeg, ...], underlying_prices: tuple[Decimal, ...]
) -> tuple[OptionPayoff, ...]:
    if not legs or not underlying_prices or any(price < 0 for price in underlying_prices):
        raise ValueError("payoff requires legs and non-negative underlying prices")
    output: list[OptionPayoff] = []
    for underlying in underlying_prices:
        payoff = Decimal(0)
        for leg in legs:
            intrinsic = (
                max(underlying - leg.strike, Decimal(0))
                if leg.option_type is OptionType.CALL
                else max(leg.strike - underlying, Decimal(0))
            )
            payoff += (intrinsic - leg.premium) * leg.quantity
        output.append(OptionPayoff(underlying, payoff))
    return tuple(output)


def estimate_option_margin(
    legs: tuple[OptionLeg, ...], spot: Decimal, config: OptionMarginConfig
) -> OptionMarginEstimate:
    """Return a transparent research estimate; this is never a substitute for broker margin."""
    if not spot.is_finite() or spot <= 0 or not legs:
        raise ValueError("margin estimation requires positive spot and option legs")
    premium_outlay = sum(
        (leg.premium * leg.quantity for leg in legs if leg.quantity > 0), Decimal(0)
    )
    scenario_losses: list[tuple[Decimal, Decimal]] = []
    for shock in config.spot_shocks:
        scenario_spot = spot * (Decimal(1) + shock)
        payoff = payoff_at_expiry(legs, (scenario_spot,))[0].gross_payoff
        scenario_losses.append((shock, max(-payoff, Decimal(0))))
    maximum_scenario_loss = max(loss for _, loss in scenario_losses)
    short_units = sum((-leg.quantity for leg in legs if leg.quantity < 0), Decimal(0))
    short_notional_floor = short_units * spot * config.short_notional_floor_fraction
    return OptionMarginEstimate(
        required_margin=max(premium_outlay, maximum_scenario_loss, short_notional_floor),
        premium_outlay=premium_outlay,
        maximum_scenario_loss=maximum_scenario_loss,
        short_notional_floor=short_notional_floor,
        scenario_losses=tuple(scenario_losses),
        model_version=config.model_version,
    )
