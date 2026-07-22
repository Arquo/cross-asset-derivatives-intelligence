"""Service layer for dashboard data status queries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from cross_asset_intelligence.storage.repositories import DuckDBRepository


@dataclass(frozen=True)
class DataStatusSummary:
    """Summary used by the Streamlit dashboard."""

    pipeline_runs: pd.DataFrame
    dataset_catalog: pd.DataFrame
    macro_observations: pd.DataFrame
    market_prices: pd.DataFrame
    quality_events: pd.DataFrame


class DataStatusService:
    """Read-only service for the dashboard."""

    def __init__(self, database_path: Path) -> None:
        self.repository = DuckDBRepository(database_path)

    def has_database(self) -> bool:
        return self.repository.database_path.exists()

    def get_summary(self) -> DataStatusSummary:
        if not self.has_database():
            empty = pd.DataFrame()
            return DataStatusSummary(empty, empty, empty, empty, empty)
        return DataStatusSummary(
            pipeline_runs=self.repository.fetch_dataframe("SELECT * FROM pipeline_runs ORDER BY started_at DESC"),
            dataset_catalog=self.repository.fetch_dataframe("SELECT * FROM dataset_catalog ORDER BY dataset_id"),
            macro_observations=self.repository.fetch_dataframe("SELECT * FROM macro_observations ORDER BY observation_ts DESC"),
            market_prices=self.repository.fetch_dataframe("SELECT * FROM market_prices ORDER BY observation_ts DESC"),
            quality_events=self.repository.fetch_dataframe("SELECT * FROM data_quality_events ORDER BY created_at DESC"),
        )

    def latest_pipeline_run(self) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        return self.repository.fetch_dataframe("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 1")

    def rows_by_dataset(self) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        return self.repository.fetch_dataframe(
            """
            SELECT dataset_id, COUNT(*) AS rows_stored
            FROM (
                SELECT dataset_id FROM macro_observations
                UNION ALL
                SELECT dataset_id FROM market_prices
            )
            GROUP BY dataset_id
            ORDER BY dataset_id
            """
        )

    def latest_dataset_status(self) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        return self.repository.fetch_dataframe(
            """
            SELECT dataset_id, provider, frequency, source_type, is_delayed, requires_credentials,
                   last_successful_ingestion, latest_observation_ts, quality_status
            FROM dataset_catalog
            ORDER BY dataset_id
            """
        )

    def fred_latest_table(self) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        return self.repository.fetch_dataframe(
            """
            SELECT d.display_name AS series_name,
                   m.series_id,
                   m.value AS latest_value,
                   d.unit AS units,
                   d.frequency,
                   m.observation_ts AS latest_observation_date,
                   m.ingested_ts AS ingestion_date,
                   m.quality_status
            FROM macro_observations m
            LEFT JOIN dataset_catalog d ON m.dataset_id = d.dataset_id
            QUALIFY ROW_NUMBER() OVER (PARTITION BY m.series_id ORDER BY m.observation_ts DESC) = 1
            ORDER BY series_name
            """
        )

    def market_latest_table(self) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        return self.repository.fetch_dataframe(
            """
            SELECT symbol,
                   close AS latest_close,
                   adjusted_close AS latest_adjusted_close,
                   volume AS latest_volume,
                   observation_ts AS latest_trading_date,
                   ingested_ts AS ingestion_date,
                   quality_status
            FROM market_prices
            QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY observation_ts DESC) = 1
            ORDER BY symbol
            """
        )

    def chart_data(self) -> dict[str, pd.DataFrame]:
        if not self.has_database():
            return {}
        return {
            "spy_qqq": self.repository.fetch_dataframe(
                """
                SELECT symbol, observation_ts, adjusted_close
                FROM market_prices
                WHERE symbol IN ('SPY', 'QQQ')
                ORDER BY observation_ts
                """
            ),
            "yields": self.repository.fetch_dataframe(
                """
                SELECT series_id, observation_ts, value
                FROM macro_observations
                WHERE series_id IN ('DGS2', 'DGS10')
                ORDER BY observation_ts
                """
            ),
            "credit": self.repository.fetch_dataframe(
                """
                SELECT observation_ts, value
                FROM macro_observations
                WHERE series_id = 'BAMLH0A0HYM2'
                ORDER BY observation_ts
                """
            ),
            "liquidity": self.repository.fetch_dataframe(
                """
                SELECT series_id, observation_ts, value
                FROM macro_observations
                WHERE series_id IN ('WALCL', 'WTREGEN', 'RRPONTSYD', 'WRESBAL')
                ORDER BY observation_ts
                """
            ),
        }
