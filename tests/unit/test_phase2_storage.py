from __future__ import annotations

from pathlib import Path

import pandas as pd

from cross_asset_intelligence.pipelines.orchestration import _store_market_raw_snapshot
from cross_asset_intelligence.storage.duckdb_store import connect_duckdb, initialize_database
from cross_asset_intelligence.storage.repositories import DuckDBRepository


def _utc(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def _market_row(**overrides) -> pd.DataFrame:
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
        "open": 100.0,
        "high": 102.0,
        "low": 99.0,
        "close": 101.0,
        "adjusted_close": 101.0,
        "adjusted_close_status": "adjusted_close",
        "volume": 1000,
        "currency": "USD",
        "quality_status": "valid",
        "quality_flags": ["historical_data"],
        "pipeline_run_id": "run-1",
    }
    base.update(overrides)
    return pd.DataFrame([base])


def _macro_row(**overrides) -> pd.DataFrame:
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
        "quality_flags": ["availability_timestamp_proxy"],
        "source_reference": "FRED series DFF",
        "pipeline_run_id": "run-1",
    }
    base.update(overrides)
    return pd.DataFrame([base])


def _pipeline_run_row(status: str = "completed") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "pipeline_run_id": "run-1",
                "pipeline_name": "free_data_ingestion",
                "provider": "FRED",
                "started_at": _utc("2024-01-03"),
                "completed_at": _utc("2024-01-03"),
                "status": status,
                "requested_start_date": pd.Timestamp("2024-01-01").date(),
                "requested_end_date": pd.Timestamp("2024-01-03").date(),
                "datasets_requested": "fred_dff",
                "records_received": 1,
                "records_validated": 1,
                "records_rejected": 0,
                "warning_count": 0,
                "error_message": None,
                "raw_snapshot_location": "data/raw/fred",
                "created_at": _utc("2024-01-03"),
            }
        ]
    )


def test_duckdb_tables_initialize_successfully(tmp_path):
    db_path = tmp_path / "cross_asset.duckdb"
    with connect_duckdb(db_path) as connection:
        initialize_database(connection)
    assert db_path.exists()


def test_valid_records_insert_and_deduplicate(tmp_path):
    repository = DuckDBRepository(tmp_path / "cross_asset.duckdb")
    repository.initialize()

    market_frame = _market_row()
    repository.insert_market_observations(market_frame)
    repository.insert_market_observations(market_frame)

    count = repository.fetch_dataframe("SELECT COUNT(*) AS n FROM market_observations").iloc[0]["n"]
    assert count == 1


def test_latest_observation_and_date_range_queries(tmp_path):
    repository = DuckDBRepository(tmp_path / "cross_asset.duckdb")
    repository.initialize()

    repository.insert_macro_observations(_macro_row(observation_ts=_utc("2024-01-01"), ingested_ts=_utc("2024-01-01"), value=5.0, record_id="rec-1"))
    repository.insert_macro_observations(_macro_row(observation_ts=_utc("2024-01-03"), ingested_ts=_utc("2024-01-03"), value=5.5, record_id="rec-2"))

    latest = repository.fetch_dataframe("SELECT * FROM macro_observations ORDER BY observation_ts DESC LIMIT 1")
    assert latest.iloc[0]["value"] == 5.5

    ranged = repository.fetch_dataframe(
        "SELECT * FROM macro_observations WHERE observation_ts BETWEEN ? AND ? ORDER BY observation_ts",
        (_utc("2024-01-01"), _utc("2024-01-02")),
    )
    assert len(ranged) == 1


def test_pipeline_runs_record_success_and_failure(tmp_path):
    repository = DuckDBRepository(tmp_path / "cross_asset.duckdb")
    repository.initialize()

    repository.insert_pipeline_run(_pipeline_run_row("completed"))
    repository.insert_pipeline_run(_pipeline_run_row("failed").assign(pipeline_run_id="run-2", provider="yfinance"))

    statuses = repository.fetch_dataframe("SELECT status FROM pipeline_runs ORDER BY provider")
    assert set(statuses["status"]) == {"completed", "failed"}


def test_raw_parquet_snapshots_are_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr("cross_asset_intelligence.pipelines.orchestration.MARKET_RAW_ROOT", tmp_path / "data" / "raw" / "market")
    first = _store_market_raw_snapshot(_market_row(observation_ts=_utc("2024-01-02")), "run-a")
    second = _store_market_raw_snapshot(_market_row(observation_ts=_utc("2024-01-03"), record_id="rec-2"), "run-b")

    assert first != second
    assert (Path(first) / "observations.parquet").exists()
    assert (Path(second) / "observations.parquet").exists()

