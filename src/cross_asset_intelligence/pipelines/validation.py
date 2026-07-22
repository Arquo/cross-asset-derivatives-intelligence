"""Deterministic validation helpers for market and macro records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import pandas as pd

from cross_asset_intelligence.core.constants import QualityStatus


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

MARKET_JUMP_WARNING_THRESHOLD = 0.2


def _is_na(value: Any) -> bool:
    return value is None or pd.isna(value)


def _frequency_threshold(frequency: str, stale_thresholds: dict[str, int]) -> int | None:
    frequency = str(frequency).lower()
    return stale_thresholds.get(frequency, DEFAULT_STALE_THRESHOLDS.get(frequency))


def _utc_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    for column in ("observation_ts", "available_ts", "ingested_ts", "latest_observation_ts"):
        if column in working.columns:
            working[column] = pd.to_datetime(working[column], utc=True, errors="coerce")
    return working


def _finalize_records(rows: list[dict[str, Any]], rejected: bool = False) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    if "quality_flags" in frame.columns:
        frame["quality_flags"] = frame["quality_flags"].apply(lambda flags: flags if isinstance(flags, list) else ([] if pd.isna(flags) else [str(flags)]))
    frame["quality_status"] = QualityStatus.rejected if rejected else frame.get("quality_status", QualityStatus.valid)
    return frame


def validate_macro_records(frame: pd.DataFrame, stale_thresholds: dict[str, int]) -> ValidationOutcome:
    accepted_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    events: list[ValidationEvent] = []

    if frame.empty:
        return ValidationOutcome(accepted=frame.copy(), rejected=frame.copy(), events=[])

    working = _normalize_frame(frame)
    seen_keys: set[tuple[str | None, pd.Timestamp | None]] = set()

    for _, row in working.iterrows():
        record = row.to_dict()
        flags = list(record.get("quality_flags", [])) if isinstance(record.get("quality_flags"), list) else []
        dataset_id = str(record.get("dataset_id", ""))
        record_id = record.get("record_id")
        rejected = False

        series_id = record.get("series_id")
        observation_ts = record.get("observation_ts")
        available_ts = record.get("available_ts")
        ingested_ts = record.get("ingested_ts")
        value = record.get("value")
        unit = record.get("unit")
        frequency = str(record.get("frequency", "")).lower()

        key = (series_id, observation_ts)
        if key in seen_keys:
            rejected = True
            events.append(ValidationEvent(dataset_id, record_id, "error", "duplicate_series_date", "Duplicate series-date record detected."))
        else:
            seen_keys.add(key)

        if _is_na(series_id) or not str(series_id).strip():
            rejected = True
            flags.append("missing_series_id")
            events.append(ValidationEvent(dataset_id, record_id, "error", "missing_series_id", "Series ID is required."))
        if _is_na(observation_ts):
            rejected = True
            flags.append("missing_observation_timestamp")
            events.append(ValidationEvent(dataset_id, record_id, "error", "missing_observation_timestamp", "Observation timestamp is required."))
        if _is_na(available_ts):
            rejected = True
            flags.append("missing_available_timestamp")
            events.append(ValidationEvent(dataset_id, record_id, "error", "missing_available_timestamp", "Available timestamp is required."))
        if _is_na(ingested_ts):
            rejected = True
            flags.append("missing_ingested_timestamp")
            events.append(ValidationEvent(dataset_id, record_id, "error", "missing_ingested_timestamp", "Ingested timestamp is required."))
        if _is_na(value):
            rejected = True
            flags.append("missing_value")
            events.append(ValidationEvent(dataset_id, record_id, "error", "missing_value", "Observation value is missing."))
        if _is_na(unit) or not str(unit).strip():
            rejected = True
            flags.append("missing_unit")
            events.append(ValidationEvent(dataset_id, record_id, "error", "missing_units", "Unit is required."))
        if pd.notna(observation_ts) and observation_ts > _utc_now():
            rejected = True
            events.append(ValidationEvent(dataset_id, record_id, "error", "future_observation_date", "Observation timestamp is in the future."))
        if pd.notna(available_ts) and pd.notna(ingested_ts) and available_ts > ingested_ts:
            rejected = True
            events.append(ValidationEvent(dataset_id, record_id, "error", "available_after_ingestion", "Available timestamp cannot be after ingestion timestamp."))
        if pd.notna(observation_ts) and pd.notna(ingested_ts) and observation_ts > ingested_ts:
            rejected = True
            events.append(ValidationEvent(dataset_id, record_id, "error", "observation_after_ingestion", "Observation timestamp cannot be after ingestion timestamp."))

        threshold = _frequency_threshold(frequency, stale_thresholds)
        if threshold is not None and pd.notna(observation_ts):
            age_days = (_utc_now() - observation_ts).days
            if age_days > threshold:
                flags.append("stale_data")

        if pd.notna(value) and str(unit).lower() not in {"index", "percent", "claims", "billions_usd", "percentage points"}:
            flags.append("unexpected_units")

        if rejected:
            record["quality_status"] = QualityStatus.rejected
            record["quality_flags"] = flags
            rejected_rows.append(record)
        else:
            record["quality_flags"] = flags
            record["quality_status"] = QualityStatus.warning if flags else QualityStatus.valid
            accepted_rows.append(record)
            for flag in flags:
                events.append(ValidationEvent(dataset_id, record_id, "warning", flag, "Record passed validation with a caveat."))

    return ValidationOutcome(accepted=pd.DataFrame(accepted_rows), rejected=pd.DataFrame(rejected_rows), events=events)


def validate_market_records(frame: pd.DataFrame, stale_thresholds: dict[str, int]) -> ValidationOutcome:
    accepted_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    events: list[ValidationEvent] = []

    if frame.empty:
        events.append(ValidationEvent("", None, "warning", "empty_provider_result", "Provider returned no market rows."))
        return ValidationOutcome(accepted=frame.copy(), rejected=frame.copy(), events=events)

    working = _normalize_frame(frame)
    seen_keys: set[tuple[str | None, pd.Timestamp | None]] = set()
    last_adjusted_close: dict[str, float] = {}
    latest_observation_by_symbol = working.groupby("symbol", dropna=False)["observation_ts"].max().to_dict()

    for _, row in working.iterrows():
        record = row.to_dict()
        flags = list(record.get("quality_flags", [])) if isinstance(record.get("quality_flags"), list) else []
        validation_flags: list[str] = []
        dataset_id = str(record.get("dataset_id", ""))
        record_id = record.get("record_id")
        rejected = False

        symbol = record.get("symbol")
        provider = record.get("provider")
        observation_ts = record.get("observation_ts")
        available_ts = record.get("available_ts")
        ingested_ts = record.get("ingested_ts")
        open_value = record.get("open")
        high = record.get("high")
        low = record.get("low")
        close = record.get("close")
        adjusted_close = record.get("adjusted_close")
        volume = record.get("volume")

        key = (symbol, observation_ts)
        if key in seen_keys:
            rejected = True
            events.append(ValidationEvent(dataset_id, record_id, "error", "duplicate_symbol_date", "Duplicate symbol-date record detected."))
        else:
            seen_keys.add(key)

        if _is_na(symbol) or not str(symbol).strip():
            rejected = True
            flags.append("missing_symbol")
            events.append(ValidationEvent(dataset_id, record_id, "error", "missing_symbol", "Symbol is required."))
        if _is_na(provider) or not str(provider).strip():
            rejected = True
            flags.append("missing_provider")
            events.append(ValidationEvent(dataset_id, record_id, "error", "missing_provider", "Provider is required."))
        if _is_na(observation_ts):
            rejected = True
            flags.append("missing_observation_timestamp")
            events.append(ValidationEvent(dataset_id, record_id, "error", "missing_observation_timestamp", "Observation timestamp is required."))
        if _is_na(available_ts):
            rejected = True
            flags.append("missing_available_timestamp")
            events.append(ValidationEvent(dataset_id, record_id, "error", "missing_available_timestamp", "Available timestamp is required."))
        if _is_na(ingested_ts):
            rejected = True
            flags.append("missing_ingested_timestamp")
            events.append(ValidationEvent(dataset_id, record_id, "error", "missing_ingested_timestamp", "Ingested timestamp is required."))
        if _is_na(close):
            rejected = True
            flags.append("missing_close")
            events.append(ValidationEvent(dataset_id, record_id, "error", "missing_close", "Close is required."))
        if _is_na(adjusted_close):
            rejected = True
            flags.append("missing_adjusted_close")
            events.append(ValidationEvent(dataset_id, record_id, "error", "missing_adjusted_close", "Adjusted close is required."))
        if pd.notna(volume) and volume < 0:
            rejected = True
            events.append(ValidationEvent(dataset_id, record_id, "error", "negative_volume", "Volume cannot be negative."))
        for field_name, field_value in [("open", open_value), ("high", high), ("low", low), ("close", close), ("adjusted_close", adjusted_close)]:
            if pd.notna(field_value) and field_value < 0:
                rejected = True
                events.append(ValidationEvent(dataset_id, record_id, "error", "negative_price", f"{field_name} cannot be negative."))
        if pd.notna(high) and pd.notna(low) and high < low:
            rejected = True
            events.append(ValidationEvent(dataset_id, record_id, "error", "high_below_low", "High cannot be lower than low."))
        if pd.notna(open_value) and pd.notna(low) and pd.notna(high) and not (low <= open_value <= high):
            rejected = True
            events.append(ValidationEvent(dataset_id, record_id, "error", "open_outside_range", "Open must be within the high-low range."))
        if pd.notna(close) and pd.notna(low) and pd.notna(high) and not (low <= close <= high):
            rejected = True
            events.append(ValidationEvent(dataset_id, record_id, "error", "close_outside_range", "Close must be within the high-low range."))
        if pd.notna(observation_ts) and observation_ts > _utc_now():
            rejected = True
            events.append(ValidationEvent(dataset_id, record_id, "error", "future_session_date", "Observation timestamp is in the future."))
        if pd.notna(available_ts) and pd.notna(ingested_ts) and available_ts > ingested_ts:
            rejected = True
            events.append(ValidationEvent(dataset_id, record_id, "error", "available_after_ingestion", "Available timestamp cannot be after ingestion timestamp."))
        if pd.notna(observation_ts) and pd.notna(ingested_ts) and observation_ts > ingested_ts:
            rejected = True
            events.append(ValidationEvent(dataset_id, record_id, "error", "observation_after_ingestion", "Observation timestamp cannot be after ingestion timestamp."))

        threshold = _frequency_threshold(str(record.get("frequency", "daily")).lower(), stale_thresholds)
        if threshold is not None and pd.notna(observation_ts) and observation_ts == latest_observation_by_symbol.get(symbol):
            age_days = (_utc_now() - observation_ts).days
            if age_days > threshold:
                flags.append("stale_data")
                validation_flags.append("stale_data")

        if pd.notna(adjusted_close) and symbol:
            last_value = last_adjusted_close.get(str(symbol))
            if last_value is not None and last_value != 0:
                pct_change = abs(adjusted_close / last_value - 1.0)
                if pct_change > MARKET_JUMP_WARNING_THRESHOLD:
                    flags.append("large_price_jump")
                    validation_flags.append("large_price_jump")
                    events.append(ValidationEvent(dataset_id, record_id, "warning", "large_price_jump", "Large price jump detected; review before analysis."))
            last_adjusted_close[str(symbol)] = float(adjusted_close)

        if rejected:
            record["quality_status"] = QualityStatus.rejected
            record["quality_flags"] = flags
            rejected_rows.append(record)
        else:
            record["quality_flags"] = flags
            record["quality_status"] = QualityStatus.warning if validation_flags else QualityStatus.valid
            accepted_rows.append(record)
            for flag in validation_flags:
                if flag != "large_price_jump":
                    events.append(ValidationEvent(dataset_id, record_id, "warning", flag, "Record passed validation with a caveat."))

    return ValidationOutcome(accepted=pd.DataFrame(accepted_rows), rejected=pd.DataFrame(rejected_rows), events=events)
