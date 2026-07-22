from __future__ import annotations

from datetime import timedelta

import pandas as pd

from cross_asset_intelligence.pipelines.validation import validate_macro_records, validate_market_records


def _utc(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def _market_frame(**overrides) -> pd.DataFrame:
    base = {
        "record_id": "rec-1",
        "dataset_id": "market_spy",
        "symbol": "SPY",
        "provider_symbol": "SPY",
        "provider": "yfinance/Yahoo Finance",
        "source_type": "vendor",
        "observation_ts": _utc("2024-01-02"),
        "available_ts": _utc("2024-01-02"),
        "ingested_ts": _utc("2024-01-02"),
        "frequency": "daily",
        "open": 100.0,
        "high": 102.0,
        "low": 99.0,
        "close": 101.0,
        "adjusted_close": 101.0,
        "adjusted_close_status": "adjusted_close",
        "volume": 1000,
        "currency": "USD",
        "quality_status": "valid",
        "quality_flags": [],
        "pipeline_run_id": "run-1",
    }
    base.update(overrides)
    return pd.DataFrame([base])


def _macro_frame(**overrides) -> pd.DataFrame:
    base = {
        "record_id": "rec-1",
        "dataset_id": "fred_dff",
        "series_id": "DFF",
        "provider": "FRED",
        "source_type": "official",
        "observation_ts": _utc("2024-01-02"),
        "available_ts": _utc("2024-01-02"),
        "ingested_ts": _utc("2024-01-02"),
        "frequency": "daily",
        "value": 5.25,
        "unit": "percent",
        "quality_status": "valid",
        "quality_flags": [],
        "source_reference": "FRED series DFF",
        "pipeline_run_id": "run-1",
    }
    base.update(overrides)
    return pd.DataFrame([base])


def test_negative_market_prices_are_rejected():
    outcome = validate_market_records(_market_frame(open=-1.0), {"daily": 3})
    assert not outcome.rejected.empty
    assert any(event.rule_name == "negative_price" for event in outcome.events)


def test_negative_volume_is_rejected():
    outcome = validate_market_records(_market_frame(volume=-10), {"daily": 3})
    assert not outcome.rejected.empty
    assert any(event.rule_name == "negative_volume" for event in outcome.events)


def test_high_below_low_is_rejected():
    outcome = validate_market_records(_market_frame(high=95.0, low=96.0), {"daily": 3})
    assert not outcome.rejected.empty
    assert any(event.rule_name == "high_below_low" for event in outcome.events)


def test_close_outside_high_low_range_is_rejected():
    outcome = validate_market_records(_market_frame(close=150.0), {"daily": 3})
    assert not outcome.rejected.empty
    assert any(event.rule_name == "close_outside_range" for event in outcome.events)


def test_duplicate_symbol_date_records_are_detected():
    frame = pd.concat([_market_frame(), _market_frame(record_id="rec-2")], ignore_index=True)
    outcome = validate_market_records(frame, {"daily": 3})
    assert len(outcome.rejected) == 1
    assert any(event.rule_name == "duplicate_symbol_date" for event in outcome.events)


def test_duplicate_fred_series_date_records_are_detected():
    frame = pd.concat([_macro_frame(), _macro_frame(record_id="rec-2")], ignore_index=True)
    outcome = validate_macro_records(frame, {"daily": 3})
    assert len(outcome.rejected) == 1
    assert any(event.rule_name == "duplicate_series_date" for event in outcome.events)


def test_missing_values_produce_quality_flags():
    outcome = validate_macro_records(_macro_frame(value=pd.NA), {"daily": 3})
    assert not outcome.rejected.empty
    assert "missing_value" in outcome.rejected.iloc[0]["quality_flags"]


def test_stale_data_uses_frequency_aware_thresholds():
    old_timestamp = pd.Timestamp.now(tz="UTC") - timedelta(days=60)
    outcome = validate_macro_records(_macro_frame(observation_ts=old_timestamp, available_ts=old_timestamp, ingested_ts=old_timestamp, frequency="monthly"), {"monthly": 45})
    assert outcome.accepted.iloc[0]["quality_status"] == "warning"
    assert "stale_data" in outcome.accepted.iloc[0]["quality_flags"]
