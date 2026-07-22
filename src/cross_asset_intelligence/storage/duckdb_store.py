"""DuckDB persistence helpers."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import duckdb
import pandas as pd


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    pipeline_run_id VARCHAR,
    provider VARCHAR,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR,
    requested_start_date DATE,
    requested_end_date DATE,
    datasets_requested VARCHAR,
    rows_fetched BIGINT,
    rows_validated BIGINT,
    rows_rejected BIGINT,
    warning_count BIGINT,
    error_message VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS macro_observations (
    record_id VARCHAR,
    dataset_id VARCHAR,
    series_id VARCHAR,
    provider VARCHAR,
    source_type VARCHAR,
    observation_ts TIMESTAMP WITH TIME ZONE,
    available_ts TIMESTAMP WITH TIME ZONE,
    ingested_ts TIMESTAMP WITH TIME ZONE,
    frequency VARCHAR,
    value DOUBLE,
    unit VARCHAR,
    quality_status VARCHAR,
    quality_flags VARCHAR,
    source_reference VARCHAR,
    pipeline_run_id VARCHAR,
    UNIQUE(series_id, observation_ts)
);

CREATE TABLE IF NOT EXISTS market_prices (
    record_id VARCHAR,
    dataset_id VARCHAR,
    symbol VARCHAR,
    provider_symbol VARCHAR,
    provider VARCHAR,
    source_type VARCHAR,
    observation_ts TIMESTAMP WITH TIME ZONE,
    available_ts TIMESTAMP WITH TIME ZONE,
    ingested_ts TIMESTAMP WITH TIME ZONE,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    adjusted_close DOUBLE,
    volume BIGINT,
    currency VARCHAR,
    quality_status VARCHAR,
    quality_flags VARCHAR,
    pipeline_run_id VARCHAR,
    UNIQUE(symbol, observation_ts)
);

CREATE TABLE IF NOT EXISTS data_quality_events (
    event_id VARCHAR,
    pipeline_run_id VARCHAR,
    dataset_id VARCHAR,
    record_id VARCHAR,
    severity VARCHAR,
    rule_name VARCHAR,
    message VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS dataset_catalog (
    dataset_id VARCHAR PRIMARY KEY,
    provider VARCHAR,
    display_name VARCHAR,
    category VARCHAR,
    frequency VARCHAR,
    unit VARCHAR,
    source_type VARCHAR,
    is_delayed BOOLEAN,
    requires_credentials BOOLEAN,
    last_successful_ingestion TIMESTAMP WITH TIME ZONE,
    latest_observation_ts TIMESTAMP WITH TIME ZONE,
    quality_status VARCHAR
);
"""


@contextmanager
def connect_duckdb(database_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(database_path))
    try:
        connection.execute("BEGIN TRANSACTION")
        yield connection
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def initialize_database(connection: duckdb.DuckDBPyConnection) -> None:
    """Create all required tables when missing."""

    connection.execute(SCHEMA_SQL)


def df_to_string(frame: pd.DataFrame) -> pd.DataFrame:
    copied = frame.copy()
    if "quality_flags" in copied.columns:
        copied["quality_flags"] = copied["quality_flags"].apply(lambda flags: "|".join(flags or []) if isinstance(flags, list) else (flags or ""))
    return copied


def upsert_dataframe(connection: duckdb.DuckDBPyConnection, table: str, frame: pd.DataFrame, unique_columns: list[str] | None = None) -> None:
    if frame.empty:
        return
    frame = df_to_string(frame)
    temp_name = f"temp_{table}"
    connection.register(temp_name, frame)
    if unique_columns:
        delete_predicate = " AND ".join([f"{table}.{col} = src.{col}" for col in unique_columns])
        connection.execute(f"DELETE FROM {table} USING {temp_name} AS src WHERE {delete_predicate}")
    connection.execute(f"INSERT INTO {table} SELECT * FROM {temp_name}")
    connection.unregister(temp_name)

