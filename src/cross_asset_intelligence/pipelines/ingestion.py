"""Pipeline ingestion orchestration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
from uuid import uuid4

import pandas as pd

from cross_asset_intelligence.core.config import FredSeriesConfig, MarketSymbolConfig, PipelineConfig, load_pipeline_config
from cross_asset_intelligence.core.constants import QualityStatus, SourceType
from cross_asset_intelligence.core.exceptions import ConfigurationError, ProviderError
from cross_asset_intelligence.pipelines.normalization import ensure_utc_timestamp, make_record_id, normalized_quality_flags, utc_now
from cross_asset_intelligence.pipelines.validation import ValidationEvent, ValidationOutcome, validate_macro_records, validate_market_records
from cross_asset_intelligence.providers.fred import FredProvider
from cross_asset_intelligence.providers.market import YFinanceMarketProvider
from cross_asset_intelligence.storage.duckdb_store import connect_duckdb, initialize_database
from cross_asset_intelligence.storage.parquet_store import write_atomic_json, write_atomic_parquet
from cross_asset_intelligence.storage.repositories import DuckDBRepository


@dataclass(frozen=True)
class ProviderRunResult:
    """Result for one provider."""

    provider_name: str
    status: str
    rows_fetched: int
    rows_validated: int
    rows_rejected: int
    warning_count: int
    error_message: str | None
    pipeline_run_id: str
    started_at: pd.Timestamp
    completed_at: pd.Timestamp


def new_pipeline_run_id() -> str:
    return uuid4().hex


def _pipeline_run_frame(result: ProviderRunResult, requested_start_date: str, requested_end_date: str | None, datasets_requested: list[str]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "pipeline_run_id": result.pipeline_run_id,
            "provider": result.provider_name,
            "started_at": utc_now(),
            "completed_at": utc_now(),
            "status": result.status,
            "requested_start_date": pd.to_datetime(requested_start_date).date() if requested_start_date else None,
            "requested_end_date": pd.to_datetime(requested_end_date).date() if requested_end_date else None,
            "datasets_requested": ",".join(datasets_requested),
            "rows_fetched": result.rows_fetched,
            "rows_validated": result.rows_validated,
            "rows_rejected": result.rows_rejected,
            "warning_count": result.warning_count,
            "error_message": result.error_message,
            "created_at": utc_now(),
        }
    ])


def build_fred_provider(config: PipelineConfig, api_key: str | None, start_date: str) -> FredProvider:
    series_configs = [
        {
            "series_id": series.series_id,
            "display_name": series.display_name,
            "category": series.category,
            "expected_frequency": series.expected_frequency,
            "expected_unit": series.expected_unit,
            "source_type": series.source_type,
            "stale_after_days": series.stale_after_days,
            "enabled": series.enabled,
            "start_date": start_date,
        }
        for series in config.fred_series
        if series.enabled
    ]
    return FredProvider(api_key=api_key, series_configs=series_configs)


def build_market_provider(config: PipelineConfig, start_date: str, end_date: str | None) -> YFinanceMarketProvider:
    symbol_configs = [
        {
            "internal_symbol": symbol.internal_symbol,
            "provider_symbol": symbol.provider_symbol,
            "display_name": symbol.display_name,
            "asset_class": symbol.asset_class,
            "currency": symbol.currency,
            "timezone": symbol.timezone,
            "enabled": symbol.enabled,
        }
        for symbol in config.market_symbols
        if symbol.enabled
    ]
    return YFinanceMarketProvider(symbols=symbol_configs, start_date=start_date, end_date=end_date)


def normalize_fred_fetch_result(result, config: PipelineConfig, pipeline_run_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    quality_events = []
    for series_result in result.successful:
        series_config = next((item for item in config.fred_series if item.series_id == series_result.series_id), None)
        if series_config is None:
            continue
        frame = series_result.observations.copy()
        frame["record_id"] = frame.apply(lambda row: make_record_id(series_result.series_id, row["date"].isoformat()), axis=1)
        frame["dataset_id"] = f"fred_{series_result.series_id.lower()}"
        frame["series_id"] = series_result.series_id
        frame["provider"] = "FRED"
        frame["source_type"] = SourceType.official
        frame["observation_ts"] = pd.to_datetime(frame["date"], utc=True)
        frame["available_ts"] = frame["observation_ts"]
        frame["ingested_ts"] = utc_now()
        frame["frequency"] = series_config.expected_frequency
        frame["unit"] = series_config.expected_unit
        frame["quality_status"] = QualityStatus.valid
        frame["quality_flags"] = [["availability_timestamp_proxy"] for _ in range(len(frame))]
        frame["source_reference"] = f"FRED series {series_result.series_id}"
        frame["pipeline_run_id"] = pipeline_run_id
        rows.append(frame[[
            "record_id","dataset_id","series_id","provider","source_type","observation_ts","available_ts","ingested_ts","frequency","value","unit","quality_status","quality_flags","source_reference","pipeline_run_id"
        ]])
    if rows:
        combined = pd.concat(rows, ignore_index=True)
    else:
        combined = pd.DataFrame(columns=["record_id","dataset_id","series_id","provider","source_type","observation_ts","available_ts","ingested_ts","frequency","value","unit","quality_status","quality_flags","source_reference","pipeline_run_id"])
    return combined, pd.DataFrame(quality_events)


def normalize_market_fetch_result(result, config: PipelineConfig, pipeline_run_id: str) -> pd.DataFrame:
    frame = result.frame.copy()
    if frame.empty:
        return frame
    frame["pipeline_run_id"] = pipeline_run_id
    frame["dataset_id"] = frame["symbol"].map(lambda symbol: f"market_{symbol.lower()}")
    frame["quality_flags"] = frame["quality_flags"].apply(lambda flags: flags if isinstance(flags, list) else [str(flags)] if flags else [])
    if "adjusted_close_status" not in frame.columns:
        frame["adjusted_close_status"] = "available"
    return frame[[
        "record_id","dataset_id","symbol","provider_symbol","provider","source_type","observation_ts","available_ts","ingested_ts","open","high","low","close","adjusted_close","adjusted_close_status","volume","currency","quality_status","quality_flags","pipeline_run_id"
    ]]


def build_pipeline_run_row(
    provider_name: str,
    pipeline_run_id: str,
    pipeline_name: str,
    status: str,
    requested_start_date: str,
    requested_end_date: str | None,
    datasets_requested: list[str],
    records_received: int,
    records_validated: int,
    records_rejected: int,
    warning_count: int,
    error_message: str | None,
    raw_snapshot_location: str | None,
    started_at: pd.Timestamp,
    completed_at: pd.Timestamp,
) -> pd.DataFrame:
    """Create the pipeline_runs row for storage."""

    return pd.DataFrame(
        [
            {
                "pipeline_run_id": pipeline_run_id,
                "pipeline_name": pipeline_name,
                "provider": provider_name,
                "started_at": started_at,
                "completed_at": completed_at,
                "status": status,
                "requested_start_date": pd.Timestamp(requested_start_date).date(),
                "requested_end_date": pd.Timestamp(requested_end_date).date() if requested_end_date else None,
                "datasets_requested": ",".join(datasets_requested),
                "records_received": records_received,
                "records_validated": records_validated,
                "records_rejected": records_rejected,
                "warning_count": warning_count,
                "error_message": error_message,
                "raw_snapshot_location": raw_snapshot_location,
                "created_at": completed_at,
            }
        ]
    )


def fred_metadata_sidecar(series_result, pipeline_run_id: str, ingestion_date: str) -> dict[str, Any]:
    """Build a safe JSON sidecar without secrets."""

    metadata = dict(series_result.metadata)
    metadata.pop("api_key", None)
    metadata.pop("apikey", None)
    return {
        "pipeline_run_id": pipeline_run_id,
        "series_id": series_result.series_id,
        "ingestion_date": ingestion_date,
        "metadata": metadata,
    }
