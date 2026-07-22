from __future__ import annotations

import pandas as pd

from cross_asset_intelligence.analytics.summary import build_cross_module_summary


def _inputs():
    screener = pd.DataFrame(
        [{"symbol": "SPY", "observation_ts": pd.Timestamp("2026-01-10", tz="UTC"), "market_pressure_score": 40.0, "pressure_label": "Moderate bullish pressure", "trend_classification": "Uptrend", "volatility_classification": "Normal", "freshness_status": "Current"}]
    )
    liquidity = pd.DataFrame(
        [{"symbol": "SPY", "observation_ts": pd.Timestamp("2026-01-10", tz="UTC"), "liquidity_stress_score": 30.0, "liquidity_regime": "Normal", "freshness_status": "Current"}]
    )
    positioning = pd.DataFrame(
        [{"internal_asset_id": "sp500", "participant_category": "Leveraged funds", "report_date": pd.Timestamp("2026-01-06", tz="UTC"), "crowding_condition": "Neutral", "positioning_reversal": False, "long_liquidation_risk": False, "short_squeeze_risk": False}]
    )
    options = pd.DataFrame(
        [
            {"symbol": "SPY", "assumption_set": "calls_positive_puts_negative", "days_to_expiration": 10, "quote_timestamp": pd.Timestamp("2026-01-10", tz="UTC"), "condition_label": "Volatility fairly priced"},
            {"symbol": "QQQ", "assumption_set": "calls_positive_puts_negative", "days_to_expiration": 10, "quote_timestamp": pd.Timestamp("2026-01-10", tz="UTC"), "condition_label": "Positive-gamma estimate"},
        ]
    )
    return screener, liquidity, positioning, options


def _rank(confidence: str) -> int:
    return {"insufficient": 0, "low": 1, "medium": 2, "high": 3}[confidence]


def test_same_inputs_produce_same_output():
    inputs = _inputs()
    assert build_cross_module_summary(*inputs) == build_cross_module_summary(*inputs)


def test_supporting_signals_are_retained():
    result = build_cross_module_summary(*_inputs())
    assert result["supporting_signals"]


def test_contradicting_signals_are_retained():
    screener, liquidity, positioning, options = _inputs()
    liquidity.loc[0, "liquidity_regime"] = "Stressed"
    result = build_cross_module_summary(screener, liquidity, positioning, options)
    assert any("stressed" in item for item in result["contradicting_signals"])


def test_missing_positioning_lowers_confidence():
    screener, liquidity, positioning, options = _inputs()
    complete = build_cross_module_summary(screener, liquidity, positioning, options)
    missing = build_cross_module_summary(screener, liquidity, pd.DataFrame(), options)
    assert _rank(missing["confidence"]) < _rank(complete["confidence"])


def test_missing_options_lowers_confidence_for_spy_and_qqq():
    screener, liquidity, positioning, options = _inputs()
    complete = build_cross_module_summary(screener, liquidity, positioning, options)
    missing = build_cross_module_summary(screener, liquidity, positioning, pd.DataFrame())
    assert _rank(missing["confidence"]) < _rank(complete["confidence"])


def test_stale_data_lowers_confidence():
    screener, liquidity, positioning, options = _inputs()
    complete = build_cross_module_summary(screener, liquidity, positioning, options)
    screener.loc[0, "freshness_status"] = "Stale"
    stale = build_cross_module_summary(screener, liquidity, positioning, options)
    assert _rank(stale["confidence"]) < _rank(complete["confidence"])
