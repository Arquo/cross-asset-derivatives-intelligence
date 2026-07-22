"""Service layer for dashboard freshness and pipeline status queries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from cross_asset_intelligence.core.constants import QualityStatus
from cross_asset_intelligence.storage.repositories import DuckDBRepository


FRESHNESS_CURRENT = "Current"
FRESHNESS_DELAYED = "Delayed as expected"
FRESHNESS_STALE = "Stale"
FRESHNESS_MISSING = "Missing"
FRESHNESS_FAILED = "Failed"


@dataclass(frozen=True)
class DataStatusSummary:
    """Prepared dashboard data for the freshness page."""

    pipeline_runs: pd.DataFrame
    dataset_catalog: pd.DataFrame
    macro_observations: pd.DataFrame
    market_observations: pd.DataFrame
    quality_events: pd.DataFrame
    freshness_summary: pd.DataFrame
    overall_health: dict[str, Any]


def classify_freshness(
    latest_observation_ts: pd.Timestamp | None,
    latest_ingestion_ts: pd.Timestamp | None,
    expected_publication_delay_days: int | None,
    latest_pipeline_status: str | None,
    quality_status: str | None,
) -> str:
    """Classify freshness using deterministic rules."""

    if latest_observation_ts is None or pd.isna(latest_observation_ts):
        return FRESHNESS_MISSING
    if latest_pipeline_status == "failed":
        return FRESHNESS_FAILED
    if quality_status == QualityStatus.rejected.value:
        return FRESHNESS_FAILED
    age_days = (pd.Timestamp.now(tz="UTC") - pd.Timestamp(latest_observation_ts)).days
    delay_days = expected_publication_delay_days if expected_publication_delay_days is not None else 0
    if age_days <= delay_days:
        return FRESHNESS_CURRENT
    if age_days <= max(delay_days * 2, delay_days + 1):
        return FRESHNESS_DELAYED
    return FRESHNESS_STALE


class DataStatusService:
    """Read-only service for dashboard status pages."""

    def __init__(self, database_path: Path) -> None:
        self.repository = DuckDBRepository(database_path)

    def has_database(self) -> bool:
        return self.repository.database_path.exists()

    def get_summary(self) -> DataStatusSummary:
        if not self.has_database():
            empty = pd.DataFrame()
            return DataStatusSummary(empty, empty, empty, empty, empty, empty, {})
        pipeline_runs = self.pipeline_run_history()
        dataset_catalog = self.dataset_status_table()
        macro = self.repository.fetch_dataframe("SELECT * FROM macro_observations ORDER BY observation_ts DESC")
        market = self.repository.fetch_dataframe("SELECT * FROM market_observations ORDER BY observation_ts DESC")
        events = self.repository.fetch_dataframe("SELECT * FROM data_quality_events ORDER BY created_at DESC")
        freshness = self.dataset_freshness_summary()
        return DataStatusSummary(
            pipeline_runs=pipeline_runs,
            dataset_catalog=dataset_catalog,
            macro_observations=macro,
            market_observations=market,
            quality_events=events,
            freshness_summary=freshness,
            overall_health=self.overall_health_summary(),
        )

    def pipeline_run_history(self, limit: int | None = 50) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        query = "SELECT * FROM pipeline_runs ORDER BY started_at DESC"
        if limit is not None:
            query += f" LIMIT {int(limit)}"
        return self.repository.fetch_dataframe(query)

    def latest_pipeline_run(self) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        return self.repository.fetch_dataframe("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 1")

    def successful_pipeline_runs(self) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        return self.repository.fetch_dataframe("SELECT * FROM pipeline_runs WHERE status IN ('completed', 'completed_with_warnings') ORDER BY started_at DESC")

    def failed_pipeline_runs(self) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        return self.repository.fetch_dataframe("SELECT * FROM pipeline_runs WHERE status = 'failed' ORDER BY started_at DESC")

    def dataset_status_table(self) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        return self.repository.fetch_dataframe("SELECT * FROM dataset_catalog ORDER BY dataset_name, dataset_id")

    def dataset_freshness_summary(self) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        frame = self.dataset_status_table().copy()
        if frame.empty:
            return frame
        for column in ["latest_observation_ts", "latest_ingestion_ts", "last_successful_ingestion"]:
            if column in frame.columns:
                frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
        now = pd.Timestamp.now(tz="UTC")
        if "age_days" not in frame.columns or frame["age_days"].isna().all():
            frame["age_days"] = (now - frame["latest_observation_ts"]).dt.total_seconds() / 86400.0
        frame["freshness_status"] = frame.apply(
            lambda row: classify_freshness(
                row.get("latest_observation_ts"),
                row.get("latest_ingestion_ts"),
                int(row["expected_publication_delay_days"]) if pd.notna(row.get("expected_publication_delay_days")) else None,
                row.get("latest_pipeline_status"),
                row.get("quality_status"),
            ),
            axis=1,
        )
        return frame

    def missing_datasets(self) -> pd.DataFrame:
        frame = self.dataset_freshness_summary()
        if frame.empty:
            return frame
        return frame[frame["freshness_status"] == FRESHNESS_MISSING].reset_index(drop=True)

    def stale_datasets(self) -> pd.DataFrame:
        frame = self.dataset_freshness_summary()
        if frame.empty:
            return frame
        return frame[frame["freshness_status"] == FRESHNESS_STALE].reset_index(drop=True)

    def overall_health_summary(self) -> dict[str, Any]:
        freshness = self.dataset_freshness_summary()
        latest_run = self.latest_pipeline_run()
        if freshness.empty:
            return {
                "status": "no_database",
                "current": 0,
                "delayed": 0,
                "stale": 0,
                "missing": 0,
                "failed": 0,
                "latest_pipeline_status": None,
            }
        counts = freshness["freshness_status"].value_counts().to_dict()
        return {
            "status": "healthy" if counts.get(FRESHNESS_STALE, 0) == 0 and counts.get(FRESHNESS_FAILED, 0) == 0 else "attention_required",
            "current": int(counts.get(FRESHNESS_CURRENT, 0)),
            "delayed": int(counts.get(FRESHNESS_DELAYED, 0)),
            "stale": int(counts.get(FRESHNESS_STALE, 0)),
            "missing": int(counts.get(FRESHNESS_MISSING, 0)),
            "failed": int(counts.get(FRESHNESS_FAILED, 0)),
            "latest_pipeline_status": None if latest_run.empty else latest_run.iloc[0].get("status"),
        }

    def latest_dataset_status(self) -> pd.DataFrame:
        return self.dataset_freshness_summary()

    def rows_by_dataset(self) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        return self.repository.fetch_dataframe(
            """
            SELECT dataset_id, COUNT(*) AS rows_stored
            FROM (
                SELECT dataset_id FROM macro_observations
                UNION ALL
                SELECT dataset_id FROM market_observations
            )
            GROUP BY dataset_id
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
            FROM market_observations
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
                FROM market_observations
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
