"""Synthetic records used in deterministic tests."""

from __future__ import annotations

from datetime import datetime, timezone


def aware_utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """Create a timezone-aware UTC timestamp for tests."""

    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def standard_observation_data() -> dict[str, object]:
    """Return a valid standard observation payload."""

    return {
        "record_id": "rec-001",
        "dataset_id": "dataset-macro-001",
        "provider": "ExampleProvider",
        "source_type": "official",
        "symbol": "SPY",
        "provider_symbol": "SPY",
        "asset_class": "equity",
        "observation_ts": aware_utc(2026, 7, 20, 16, 0),
        "available_ts": aware_utc(2026, 7, 20, 16, 5),
        "ingested_ts": aware_utc(2026, 7, 20, 16, 10),
        "frequency": "daily",
        "timezone": "UTC",
        "value": 123.45,
        "unit": "index",
        "is_adjusted": False,
        "is_estimated": False,
        "is_revised": False,
        "quality_status": "valid",
        "quality_flags": [],
        "source_reference": "https://example.com/source",
        "pipeline_run_id": "run-001",
    }


def signal_record_data() -> dict[str, object]:
    """Return a valid signal record payload."""

    return {
        "signal_id": "sig-001",
        "indicator_id": "ind-001",
        "module": "Macro",
        "calculation_ts": aware_utc(2026, 7, 20, 16, 15),
        "raw_value": 0.42,
        "normalized_value": 0.42,
        "score": 0.5,
        "direction": "bullish",
        "strength": 0.7,
        "interpretation": "Macro conditions are improving.",
        "confidence": "high",
        "freshness": "fresh",
        "evidence_record_ids": ["rec-001"],
        "assumptions": ["No major policy shock"],
        "failure_cases": ["Rapid inflation reacceleration"],
        "contradicting_signal_ids": ["sig-002"],
    }


def market_report_data() -> dict[str, object]:
    """Return a valid market report payload."""

    return {
        "report_id": "report-001",
        "report_as_of": aware_utc(2026, 7, 20, 17, 0),
        "data_cutoff": aware_utc(2026, 7, 20, 16, 30),
        "overall_regime": "mixed / transitioning",
        "confidence": "medium",
        "supporting_signals": ["sig-001"],
        "contradicting_signals": ["sig-002"],
        "base_scenario": "Conditions stay range-bound.",
        "bull_scenario": "Growth and breadth improve.",
        "bear_scenario": "Risk assets weaken on tighter policy.",
        "catalysts": ["CPI release", "FOMC meeting"],
        "invalidation_conditions": ["Broad-based credit stress"],
        "data_limitations": ["No live options tape"],
        "missing_modules": ["Options"],
        "indicators_to_monitor": ["CPI", "UNRATE"],
        "prompt_version": "phase-1",
        "model_name": "none",
        "input_packet_hash": "abc123",
        "validation_status": "valid",
    }

