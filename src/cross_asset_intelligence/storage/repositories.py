"""Repository helpers for DuckDB-backed reads and writes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .duckdb_store import connect_duckdb, initialize_database, upsert_dataframe


@dataclass
class DuckDBRepository:
    """Thin repository wrapper around the project DuckDB file."""

    database_path: Path

    def initialize(self) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)

    def insert_pipeline_run(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(connection, "pipeline_runs", frame)

    def insert_macro_observations(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(connection, "macro_observations", frame, unique_columns=["series_id", "observation_ts"])

    def insert_market_observations(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(connection, "market_observations", frame, unique_columns=["symbol", "observation_ts"])

    def insert_market_prices(self, frame: pd.DataFrame) -> None:
        self.insert_market_observations(frame)

    def insert_quality_events(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(connection, "data_quality_events", frame)

    def upsert_dataset_catalog(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(connection, "dataset_catalog", frame, unique_columns=["dataset_id"])

    def fetch_dataframe(self, query: str, params: tuple | None = None) -> pd.DataFrame:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            return connection.execute(query, params or ()).fetchdf()
