from __future__ import annotations

from datetime import timedelta

import pandas as pd

from cross_asset_intelligence.services.data_status_service import DataStatusService, classify_freshness
from cross_asset_intelligence.services.market_data_service import calculate_daily_returns, normalize_performance
from cross_asset_intelligence.storage.repositories import DuckDBRepository


def _utc(value: str) -> pd.Timestamp:
    return pd.Timestamp(value, tz="UTC")


def _catalog_row(**overrides) -> pd.DataFrame:
    base = {
        "dataset_id": "market_spy",
        "dataset_name": "SPY",
        "provider": "yfinance/Yahoo Finance",
        "display_name": "SPY",
        "category": "etf",
        "frequency": "daily",
        "expected_publication_delay_days": 3,
        "unit": "price",
        "source_type": "vendor",
        "is_delayed": True,
        "requires_credentials": False,
        "last_successful_ingestion": _utc("2024-01-03"),
        "latest_ingestion_ts": _utc("2024-01-03"),
        "latest_observation_ts": _utc("2024-01-02"),
        "age_days": 1.0,
        "freshness_status": "Current",
        "quality_status": "valid",
        "record_count": 10,
        "latest_pipeline_status": "completed",
        "warning_message": None,
    }
    base.update(overrides)
    return pd.DataFrame([base])


def _price_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["SPY", "SPY", "QQQ", "QQQ"],
            "observation_ts": [_utc("2024-01-01"), _utc("2024-01-02"), _utc("2024-01-01"), _utc("2024-01-02")],
            "adjusted_close": [100.0, 110.0, 200.0, 220.0],
        }
    )


def test_daily_returns_calculate_correctly():
    frame = calculate_daily_returns(_price_frame())
    spy = frame[frame["symbol"] == "SPY"].sort_values("observation_ts")
    assert pd.isna(spy.iloc[0]["daily_return"])
    assert spy.iloc[1]["daily_return"] == 10.0


def test_normalized_performance_starts_at_100():
    frame = normalize_performance(_price_frame())
    spy = frame[frame["symbol"] == "SPY"].sort_values("observation_ts")
    assert spy.iloc[0]["normalized_value"] == 100.0
    assert spy.iloc[1]["normalized_value"] == 110.0


def test_freshness_categories_classify_correctly():
    now = pd.Timestamp.now(tz="UTC")
    assert classify_freshness(now - timedelta(days=1), now, 3, "completed", "valid") == "Current"
    assert classify_freshness(now - timedelta(days=5), now, 3, "completed", "valid") == "Delayed as expected"
    assert classify_freshness(now - timedelta(days=10), now, 3, "completed", "valid") == "Stale"
    assert classify_freshness(None, None, 3, "completed", "valid") == "Missing"
    assert classify_freshness(now - timedelta(days=1), now, 3, "failed", "valid") == "Failed"


def test_missing_datasets_appear_in_status_summary(tmp_path):
    repository = DuckDBRepository(tmp_path / "cross_asset.duckdb")
    repository.initialize()
    repository.upsert_dataset_catalog(
        pd.concat(
            [
                _catalog_row(dataset_id="market_spy", freshness_status="Current", latest_pipeline_status="completed"),
                _catalog_row(dataset_id="fred_cpi", dataset_name="CPI", provider="FRED", display_name="CPI", freshness_status="Missing", latest_observation_ts=pd.NaT, latest_ingestion_ts=pd.NaT, last_successful_ingestion=pd.NaT, quality_status="missing", record_count=0, latest_pipeline_status="completed", warning_message="No data"),
            ],
            ignore_index=True,
        )
    )

    service = DataStatusService(repository.database_path)
    missing = service.missing_datasets()
    assert not missing.empty
    assert "fred_cpi" in set(missing["dataset_id"])


def test_overall_health_reflects_failed_critical_datasets(tmp_path):
    repository = DuckDBRepository(tmp_path / "cross_asset.duckdb")
    repository.initialize()
    repository.upsert_dataset_catalog(
        pd.concat(
            [
                _catalog_row(dataset_id="market_spy", freshness_status="Current", latest_pipeline_status="completed"),
                _catalog_row(dataset_id="fred_cpi", dataset_name="CPI", provider="FRED", display_name="CPI", freshness_status="Failed", latest_observation_ts=_utc("2024-01-02"), latest_ingestion_ts=_utc("2024-01-03"), last_successful_ingestion=_utc("2024-01-03"), quality_status="rejected", record_count=0, latest_pipeline_status="failed", warning_message="Provider failed"),
            ],
            ignore_index=True,
        )
    )

    service = DataStatusService(repository.database_path)
    health = service.overall_health_summary()
    assert health["failed"] >= 1
    assert health["status"] == "attention_required"
