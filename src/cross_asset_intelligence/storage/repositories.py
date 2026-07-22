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

    def insert_cftc_contract_mappings(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(connection, "cftc_contract_mappings", frame, unique_columns=["internal_asset_id"])

    def insert_cftc_positioning_observations(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(
                connection,
                "cftc_positioning_observations",
                frame,
                unique_columns=["internal_asset_id", "report_date", "report_type", "participant_category"],
            )

    def insert_option_contract_snapshots(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(
                connection,
                "option_contract_snapshots",
                frame,
                unique_columns=["snapshot_id", "contract_symbol"],
            )

    def insert_screener_results(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(connection, "screener_results", frame, unique_columns=["symbol", "observation_ts"])

    def insert_market_pressure_scores(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(connection, "market_pressure_scores", frame, unique_columns=["symbol", "observation_ts"])

    def insert_liquidity_analytics(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(connection, "liquidity_analytics", frame, unique_columns=["symbol", "observation_ts"])

    def insert_positioning_analytics(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(
                connection,
                "positioning_analytics",
                frame,
                unique_columns=["internal_asset_id", "participant_category", "report_date"],
            )

    def insert_option_analytics(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(
                connection,
                "option_analytics",
                frame,
                unique_columns=["snapshot_id", "expiration", "assumption_set"],
            )

    def insert_cross_module_summaries(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(connection, "cross_module_summaries", frame, unique_columns=["summary_id"])

    def insert_indicator_values(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(connection, "indicator_values", frame, unique_columns=["indicator_value_id"])

    def insert_signal_records(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(connection, "signal_records", frame, unique_columns=["signal_id"])

    def insert_evidence_links(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(connection, "evidence_links", frame, unique_columns=["evidence_id"])

    def insert_market_context_packets(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(connection, "market_context_packets", frame, unique_columns=["packet_id"])

    def insert_deterministic_reports(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(connection, "deterministic_reports", frame, unique_columns=["report_id"])

    def insert_analytics_runs(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(connection, "analytics_runs", frame, unique_columns=["analytics_run_id"])

    def upsert_dataset_catalog(self, frame: pd.DataFrame) -> None:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            upsert_dataframe(connection, "dataset_catalog", frame, unique_columns=["dataset_id"])

    def fetch_dataframe(self, query: str, params: tuple | None = None) -> pd.DataFrame:
        with connect_duckdb(self.database_path) as connection:
            initialize_database(connection)
            return connection.execute(query, params or ()).fetchdf()
