from __future__ import annotations

import pandas as pd
import pytest

from cross_asset_intelligence.analytics.liquidity.indicators import calculate_liquidity_stress
from cross_asset_intelligence.analytics.screener.metrics import (
    amihud_illiquidity,
    average_true_range,
    classify_freshness,
    daily_return,
    dollar_volume,
    intraday_range_pct,
    moving_average_distance,
    realized_volatility,
    relative_volume,
)
from cross_asset_intelligence.analytics.screener.score import calculate_market_pressure_score
from cross_asset_intelligence.analytics.screener.views import apply_screener_filters, apply_screener_view


def test_daily_returns():
    result = daily_return(pd.Series([100.0, 101.0, 99.99]))
    assert result.iloc[1] == pytest.approx(0.01)


def test_moving_average_distance():
    result = moving_average_distance(pd.Series([10.0, 12.0]), 2)
    assert result.iloc[-1] == pytest.approx(12 / 11 - 1)


def test_realized_volatility():
    result = realized_volatility(pd.Series([0.01, -0.01, 0.02, -0.02]), 4)
    assert result.iloc[-1] > 0


def test_relative_volume():
    result = relative_volume(pd.Series([100.0, 100.0, 200.0]), 2)
    assert result.iloc[-1] == pytest.approx(200 / 150)


def test_dollar_volume():
    result = dollar_volume(pd.Series([10.0]), pd.Series([1_000]))
    assert result.iloc[0] == 10_000


def test_amihud_illiquidity():
    result = amihud_illiquidity(pd.Series([0.01, -0.02]), pd.Series([1000.0, 2000.0]), 2)
    assert result.iloc[-1] == pytest.approx(0.00001)


def test_intraday_range():
    result = intraday_range_pct(pd.Series([11.0]), pd.Series([9.0]), pd.Series([10.0]))
    assert result.iloc[0] == pytest.approx(0.2)


def test_average_true_range():
    result = average_true_range(pd.Series([11.0, 12.0]), pd.Series([9.0, 10.0]), pd.Series([10.0, 11.0]), 2)
    assert result.iloc[-1] == pytest.approx(2.0)


def test_liquidity_stress_score():
    result = calculate_liquidity_stress(
        {
            "amihud_illiquidity": 0.5,
            "realized_volatility": 0.5,
            "intraday_range": 0.5,
            "inverse_relative_dollar_volume": 0.5,
            "hyg_stress": 0.5,
            "vix_stress": 0.5,
        }
    )
    assert result["score"] == pytest.approx(50.0)


def test_liquidity_missing_component_weight_redistribution():
    result = calculate_liquidity_stress(
        {
            "amihud_illiquidity": 1.0,
            "realized_volatility": 0.0,
            "intraday_range": 0.5,
            "inverse_relative_dollar_volume": 0.5,
            "hyg_stress": None,
            "vix_stress": None,
        }
    )
    assert sum(item["effective_weight"] for item in result["contributions"]) == pytest.approx(1.0)
    assert "hyg_stress" in result["missing_components"]


def test_market_pressure_score_construction():
    result = calculate_market_pressure_score(
        {
            "trend_momentum": 80,
            "volume_confirmation": 40,
            "volatility_condition": 20,
            "liquidity_condition": 60,
            "positioning_condition": 0,
        }
    )
    assert result.score == pytest.approx(45.0)
    assert result.label == "Moderate bullish pressure"


def test_market_pressure_score_stays_bounded():
    result = calculate_market_pressure_score({name: 1_000 for name in ["trend_momentum", "volume_confirmation", "volatility_condition", "liquidity_condition", "positioning_condition"]})
    assert result.score == 100


def test_missing_pressure_data_does_not_become_zero():
    result = calculate_market_pressure_score(
        {
            "trend_momentum": 50,
            "volume_confirmation": None,
            "volatility_condition": 50,
            "liquidity_condition": 50,
            "positioning_condition": None,
        }
    )
    assert result.score == pytest.approx(50)
    assert all(item["component"] != "volume_confirmation" for item in result.components)


def test_screener_sorting_and_filtering_view_models():
    frame = pd.DataFrame(
        [
            {"symbol": "A", "asset_class": "equity", "return_20d": 0.1, "market_pressure_score": 50, "positioning_classification": "Neutral"},
            {"symbol": "B", "asset_class": "rates", "return_20d": -0.2, "market_pressure_score": -40, "positioning_classification": "Crowded short"},
        ]
    )
    assert apply_screener_view(frame, "Strongest momentum").iloc[0]["symbol"] == "A"
    assert apply_screener_filters(frame, {"asset_class": ["rates"]}).iloc[0]["symbol"] == "B"


def test_data_freshness_labels():
    reference = pd.Timestamp("2026-01-10", tz="UTC")
    assert classify_freshness("2026-01-09", reference) == "Current"
    assert classify_freshness("2026-01-05", reference) == "Delayed as expected"
    assert classify_freshness("2025-12-01", reference) == "Stale"
