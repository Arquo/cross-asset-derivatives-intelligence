"""Deterministic record validation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import pandas as pd

from cross_asset_intelligence.core.constants import Frequency, QualityStatus


@dataclass(frozen=True)
class ValidationEvent:
    """A single validation warning or rejection."""

    dataset_id: str
    record_id: str | None
    severity: str
    rule_name: str
    message: str


@dataclass(frozen=True)
class ValidationOutcome:
    """Result of validating a set of records."""

    accepted: pd.DataFrame
    rejected: pd.DataFrame
    events: list[ValidationEvent] = field(default_factory=list)


DEFAULT_STALE_THRESHOLDS = {
    "daily": 3,
    "weekly": 10,
    "monthly": 45,
    "quarterly": 120,
}


def _is_na(value: Any) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value)


def _frequency_threshold(frequency: str, stale_thresholds: dict[str, int]) -> int | None:
    return stale_thresholds.get(frequency, DEFAULT_STALE_THRESHOLDS.get(frequency))


def validate_macro_records(frame: pd.DataFrame, stale_thresholds: dict[str, int]) -> ValidationOutcome:
    accepted_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    events: list[ValidationEvent] = []

    if frame.empty:
        return ValidationOutcome(accepted=frame.copy(), rejected=frame.copy(), events=[])

    working = frame.copy()
    working["observation_ts"] = pd.to_datetime(working["observation_ts"], utc=True, errors="coerce")
    working["available_ts"] = pd.to_datetime(working["available_ts"], utc=True, errors="coerce")
    working["ingested_ts"] = pd.to_datetime(working["ingested_ts"], utc=True, errors="coerce")

    for _, row in working.iterrows():
        record = row.to_dict()
        flags = list(record.get("quality_flags", []))
        rejected = False

        if _is_na(record.get("series_id")):
            rejected = True
            events.append(ValidationEvent(record.get("dataset_id", ""), record.get("record_id"), "error", "missing_series_id", "Series ID is required."))
        if _is_na(record.get("observation_ts")):
            rejected = True
            events.append(ValidationEvent(record.get("dataset_id", ""), record.get("record_id"), "error", "missing_observation_timestamp", "Observation timestamp is required."))
        if _is_na(record.get("value")):
            rejected = True
            events.append(ValidationEvent(record.get("dataset_id", ""), record.get("record_id"), "error", "non_numeric_value", "Observation value could not be parsed as numeric."))
        if _is_na(record.get("unit")):
            rejected = True
            events.append(ValidationEvent(record.get("dataset_id", ""), record.get("record_id"), "error", "missing_units", "Unit is required."))
        if pd.notna(record.get("observation_ts")) and record["observation_ts"] > pd.Timestamp.now(tz="UTC"):
            rejected = True
            events.append(ValidationEvent(record.get("dataset_id", ""), record.get("record_id"), "error", "future_observation_date", "Observation timestamp is in the future."))

        frequency = str(record.get("frequency", "")).lower()
        threshold = _frequency_threshold(frequency, stale_thresholds)
        latest_seen = record.get("latest_observation_ts")
        if threshold is not None and pd.notna(latest_seen):
            latest_seen_ts = pd.Timestamp(latest_seen)
            if latest_seen_ts.tzinfo is None:
                latest_seen_ts = latest_seen_ts.tz_localize("UTC")
            if pd.Timestamp.now(tz="UTC") - latest_seen_ts > timedelta(days=threshold):
                flags.append("stale_data")

        if rejected:
            record["quality_status"] = QualityStatus.rejected
            rejected_rows.append(record)
        else:
            if flags:
                record["quality_status"] = QualityStatus.warning
            else:
                record["quality_status"] = QualityStatus.valid
            record["quality_flags"] = flags
            accepted_rows.append(record)

    accepted = pd.DataFrame(accepted_rows)
    rejected = pd.DataFrame(rejected_rows)
    return ValidationOutcome(accepted=accepted, rejected=rejected, events=events)


def validate_market_records(frame: pd.DataFrame, stale_thresholds: dict[str, int]) -> ValidationOutcome:
    accepted_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    events: list[ValidationEvent] = []

    if frame.empty:
        events.append(ValidationEvent("", None, "warning", "empty_provider_result", "Provider returned no market rows."))
        return ValidationOutcome(accepted=frame.copy(), rejected=frame.copy(), events=events)

    working = frame.copy()
    working["observation_ts"] = pd.to_datetime(working["observation_ts"], utc=True, errors="coerce")
    working["available_ts"] = pd.to_datetime(working["available_ts"], utc=True, errors="coerce")
    working["ingested_ts"] = pd.to_datetime(working["ingested_ts"], utc=True, errors="coerce")

    dedupe_keys = set()

    for _, row in working.iterrows():
        record = row.to_dict()
        flags = list(record.get("quality_flags", []))
        rejected = False
        symbol = record.get("symbol")
        observation_ts = record.get("observation_ts")
        key = (symbol, observation_ts)
        if key in dedupe_keys:
            rejected = True
            events.append(ValidationEvent(record.get("dataset_id", ""), record.get("record_id"), "error", "duplicate_symbol_date", "Duplicate symbol-date record detected."))
        else:
            dedupe_keys.add(key)
        if _is_na(symbol):
            rejected = True
            events.append(ValidationEvent(record.get("dataset_id", ""), record.get("record_id"), "error", "missing_symbol", "Symbol is required."))
        if _is_na(observation_ts):
            rejected = True
            events.append(ValidationEvent(record.get("dataset_id", ""), record.get("record_id"), "error", "missing_observation_timestamp", "Observation timestamp is required."))
        if _is_na(record.get("close")):
            rejected = True
            events.append(ValidationEvent(record.get("dataset_id", ""), record.get("record_id"), "error", "missing_close", "Close is required."))
        if record.get("volume") is not None and pd.notna(record.get("volume")) and record.get("volume") < 0:
            rejected = True
            events.append(ValidationEvent(record.get("dataset_id", ""), record.get("record_id"), "error", "negative_volume", "Volume cannot be negative."))
        for field in ("open", "high", "low", "close"):
            if pd.notna(record.get(field)) and record.get(field) <= 0:
                rejected = True
                events.append(ValidationEvent(record.get("dataset_id", ""), record.get("record_id"), "error", "non_positive_price", f"{field} must be positive."))
        if pd.notna(record.get("high")) and pd.notna(record.get("low")) and record.get("high") < record.get("low"):
            rejected = True
            events.append(ValidationEvent(record.get("dataset_id", ""), record.get("record_id"), "error", "high_lower_than_low", "High cannot be lower than low."))
        if pd.notna(observation_ts) and observation_ts > pd.Timestamp.now(tz="UTC"):
            rejected = True
            events.append(ValidationEvent(record.get("dataset_id", ""), record.get("record_id"), "error", "future_session_date", "Observation timestamp is in the future."))

        frequency = str(record.get("frequency", "")).lower()
        threshold = _frequency_threshold(frequency, stale_thresholds)
        latest_seen = record.get("latest_observation_ts")
        if threshold is not None and pd.notna(latest_seen):
            latest_seen_ts = pd.Timestamp(latest_seen)
            if latest_seen_ts.tzinfo is None:
                latest_seen_ts = latest_seen_ts.tz_localize("UTC")
            if pd.Timestamp.now(tz="UTC") - latest_seen_ts > timedelta(days=threshold):
                flags.append("stale_data")

        if rejected:
            record["quality_status"] = QualityStatus.rejected
            rejected_rows.append(record)
        else:
            record["quality_status"] = QualityStatus.warning if flags else QualityStatus.valid
            record["quality_flags"] = flags
            accepted_rows.append(record)

    accepted = pd.DataFrame(accepted_rows)
    rejected = pd.DataFrame(rejected_rows)
    return ValidationOutcome(accepted=accepted, rejected=rejected, events=events)
