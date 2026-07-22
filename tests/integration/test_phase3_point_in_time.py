from __future__ import annotations

from pathlib import Path

import pandas as pd

from cross_asset_intelligence.core.config import CFTCContractConfig
from cross_asset_intelligence.pipelines.cftc_normalization import normalize_cftc_fetch_result
from cross_asset_intelligence.providers.cftc import CFTCContractFrame
from cross_asset_intelligence.services.analytics_service import AnalyticsService
from cross_asset_intelligence.storage.repositories import DuckDBRepository


def _macro_row(date: str, value: float, series_id: str = "DFF") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "record_id": f"rec-{date}",
                "dataset_id": f"fred_{series_id.lower()}",
                "series_id": series_id,
                "provider": "FRED",
                "source_type": "official",
                "observation_ts": pd.Timestamp(date, tz="UTC"),
                "available_ts": pd.Timestamp(date, tz="UTC"),
                "ingested_ts": pd.Timestamp(date, tz="UTC"),
                "frequency": "daily",
                "value": value,
                "unit": "percent",
                "quality_status": "valid",
                "quality_flags": [],
                "source_reference": "FRED",
                "pipeline_run_id": "run-1",
            }
        ]
    )


def _cftc_contract() -> CFTCContractConfig:
    return CFTCContractConfig(
        internal_asset_id="sp500",
        display_name="S&P 500",
        cftc_contract_market_code=None,
        official_contract_name="S&P 500 - CHICAGO MERCANTILE EXCHANGE",
        report_type="tff",
        exchange="CHICAGO MERCANTILE EXCHANGE",
        asset_class="equity_index",
        contract_unit="USD per index point",
        preferred_participant_categories=["Dealer or intermediary"],
        active=True,
    )


def test_records_unavailable_on_as_of_date_are_excluded(tmp_path):
    repository = DuckDBRepository(tmp_path / "cross_asset.duckdb")
    repository.initialize()
    repository.insert_macro_observations(_macro_row("2024-01-01", 1.0))
    repository.insert_macro_observations(_macro_row("2024-02-01", 2.0))
    service = AnalyticsService(repository.database_path, root_dir=Path.cwd())
    history = service.macro_history(["DFF"], as_of=pd.Timestamp("2024-01-15", tz="UTC"))
    assert history["value"].tolist() == [1.0]


def test_cftc_reports_are_unavailable_before_publication(tmp_path):
    repository = DuckDBRepository(tmp_path / "cross_asset.duckdb")
    repository.initialize()
    contract = _cftc_contract()
    raw = pd.DataFrame(
        [
            {
                "report_date_as_yyyy_mm_dd": "2024-01-02",
                "contract_market_name": "S&P 500 - CHICAGO MERCANTILE EXCHANGE",
                "market_and_exchange_names": "S&P 500 - CHICAGO MERCANTILE EXCHANGE",
                "open_interest_all": 1000,
                "dealer_positions_long_all": 600,
                "dealer_positions_short_all": 200,
            }
        ]
    )
    result = type("Result", (), {"successful": [CFTCContractFrame(contract=contract, frame=raw, source_url="https://example.com")], "failed": [], "rows_fetched": 1})()
    normalized, _ = normalize_cftc_fetch_result(result, "run-1")
    repository.insert_cftc_positioning_observations(normalized)
    service = AnalyticsService(repository.database_path, root_dir=Path.cwd())
    history = service.cftc_history(["sp500"], as_of=pd.Timestamp("2024-01-03", tz="UTC"))
    assert history.empty
