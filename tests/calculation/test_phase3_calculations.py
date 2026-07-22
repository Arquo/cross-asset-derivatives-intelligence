from __future__ import annotations

import pandas as pd
import pytest

from cross_asset_intelligence.analytics.common import (
    amihud_illiquidity,
    annualized_realized_volatility,
    historical_percentile,
    rolling_beta,
    rolling_correlation,
    rolling_zscore,
    safe_divide,
    percentage_change,
    absolute_change,
)
from cross_asset_intelligence.analytics.liquidity.classification import classify_liquidity_regime
from cross_asset_intelligence.analytics.positioning.classification import classify_positioning_bucket
from cross_asset_intelligence.indicators.definitions import IndicatorDefinition
from cross_asset_intelligence.indicators.normalization import normalize_indicator_value, signal_strength
from cross_asset_intelligence.indicators.thresholds import SignalThresholds


def test_change_helpers_return_expected_values():
    series = pd.Series([100.0, 110.0, 121.0])
    assert absolute_change(series, 1) == pytest.approx(11.0)
    assert percentage_change(series, 1) == pytest.approx(0.1)


def test_rolling_zscore_and_percentile_are_deterministic():
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    zscore = rolling_zscore(series, 3)
    percentile = historical_percentile(series, 3)
    assert pd.isna(zscore.iloc[1])
    assert percentile.iloc[-1] == pytest.approx(1.0)


def test_volatility_correlation_and_beta_helpers_work():
    returns = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02])
    price_a = pd.Series([100, 102, 101, 104, 103], dtype=float)
    price_b = pd.Series([50, 51, 51.5, 52, 52.5], dtype=float)
    dollar_volume = pd.Series([1000, 1200, 1100, 1300, 1400], dtype=float)
    assert annualized_realized_volatility(returns, 3).iloc[-1] > 0
    assert rolling_correlation(price_a, price_b, 3).iloc[-1] <= 1
    assert pd.notna(rolling_beta(price_a, price_b, 3).iloc[-1])
    assert amihud_illiquidity(returns, dollar_volume, 3).iloc[-1] > 0


def test_normalization_and_strength_are_bounded():
    definition = IndicatorDefinition(
        indicator_id="example",
        display_name="Example",
        module="macro",
        description="Example",
        formula="x",
        required_datasets=["dataset"],
        frequency="daily",
        lookback_period=5,
        minimum_observations=5,
        unit="percent",
        normal_range=(0.0, 10.0),
        warning_threshold=8.0,
        extreme_threshold=9.0,
        bullish_interpretation="bullish",
        bearish_interpretation="bearish",
        limitations=[],
        failure_cases=[],
        freshness_requirement="daily",
        directional_bias="higher is bearish",
    )
    score = normalize_indicator_value(7.5, definition)
    assert score is not None
    assert -1.0 <= score <= 1.0
    strength = signal_strength(score, SignalThresholds())
    assert strength in {"Weak", "Moderate", "Strong", "Extreme"}


def test_positioning_and_liquidity_classifications_are_explicit():
    assert classify_positioning_bucket(0.8, 0.9) == "Crowded long"
    assert classify_positioning_bucket(-0.8, 0.1) == "Crowded short"
    assert classify_liquidity_regime(0.15, confidence="high") == "Abundant"
    assert classify_liquidity_regime(0.80, confidence="high") == "Stressed"
    assert classify_liquidity_regime(None, confidence=1.0) == "Insufficient data"


def test_safe_divide_handles_zero_and_missing():
    assert safe_divide(10, 2) == 5
    assert safe_divide(10, 0) is None
    assert safe_divide(None, 2) is None
