"""Command-line entry point for the Phase 1B free-data pipeline."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import pandas as pd

from cross_asset_intelligence.core.config import load_pipeline_config
from cross_asset_intelligence.core.logging_config import configure_logging
from cross_asset_intelligence.pipelines.ingestion import (
    FredFetchResult,
    FredProvider,
    MarketFetchResult,
    ProviderRunResult,
    build_fred_provider,
    build_market_provider,
    build_pipeline_run_row,
    fred_metadata_sidecar,
    new_pipeline_run_id,
    normalize_fred_fetch_result,
    normalize_market_fetch_result,
)
from cross_asset_intelligence.pipelines.validation import ValidationEvent, validate_macro_records, validate_market_records
from cross_asset_intelligence.services.data_status_service import DataStatusService
from cross_asset_intelligence.storage.duckdb_store import initialize_database
from cross_asset_intelligence.storage.parquet_store import write_atomic_json, write_atomic_parquet
from cross_asset_intelligence.storage.repositories import DuckDBRepository


LOGGER = configure_logging(logging.INFO)
DEFAULT_START_DATE = "2015-01-01"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the free-data ingestion pipeline.")
    parser.add_argument("--start", default=DEFAULT_START_DATE)
    parser.add_argument("--end", default=None)
    parser.add_argument("--provider", choices=["all", "fred", "market"], default="all")
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--series", nargs="*", default=None)
    parser.add_argument("--database-path", default=str(Path("data/processed/cross_asset_intelligence.duckdb")))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _requested_datasets(provider: str, config) -> list[str]:
    if provider == "fred":
        return [series.series_id for series in config.fred_series if series.enabled]
    if provider == "market":
        return [symbol.internal_symbol for symbol in config.market_symbols if symbol.enabled]
    return [*([series.series_id for series in config.fred_series if series.enabled]), *([symbol.internal_symbol for symbol in config.market_symbols if symbol.enabled])]


def _store_quality_events(repository: DuckDBRepository, events: list[ValidationEvent], pipeline_run_id: str) -> None:
    if not events:
        return
    rows = pd.DataFrame(
        [
            {
                "event_id": f"{pipeline_run_id}-{index}",
                "pipeline_run_id": pipeline_run_id,
                "dataset_id": event.dataset_id,
                "record_id": event.record_id,
                "severity": event.severity,
                "rule_name": event.rule_name,
                "message": event.message,
                "created_at": pd.Timestamp.now(tz="UTC"),
            }
            for index, event in enumerate(events, start=1)
        ]
    )
    repository.insert_quality_events(rows)


def _store_dataset_catalog(repository: DuckDBRepository, config, last_successful_ingestion: pd.Timestamp | None = None) -> None:
    rows = []
    for series in config.fred_series:
        rows.append(
            {
                "dataset_id": f"fred_{series.series_id.lower()}",
                "provider": "FRED",
                "display_name": series.display_name,
                "category": series.category,
                "frequency": series.expected_frequency,
                "unit": series.expected_unit,
                "source_type": series.source_type,
                "is_delayed": True,
                "requires_credentials": True,
                "last_successful_ingestion": last_successful_ingestion,
                "latest_observation_ts": None,
                "quality_status": "planned",
            }
        )
    for symbol in config.market_symbols:
        rows.append(
            {
                "dataset_id": f"market_{symbol.internal_symbol.lower()}",
                "provider": "yfinance/Yahoo Finance",
                "display_name": symbol.display_name,
                "category": "market",
                "frequency": "daily",
                "unit": "price",
                "source_type": "vendor",
                "is_delayed": True,
                "requires_credentials": False,
                "last_successful_ingestion": last_successful_ingestion,
                "latest_observation_ts": None,
                "quality_status": "planned",
            }
        )
    repository.upsert_dataset_catalog(pd.DataFrame(rows))


def _run_fred(repository: DuckDBRepository, config, api_key: str | None, start: str, end: str | None, pipeline_run_id: str, dry_run: bool) -> ProviderRunResult:
    started_at = pd.Timestamp.now(tz="UTC")
    provider = build_fred_provider(config, api_key, start)
    if not api_key:
        completed_at = pd.Timestamp.now(tz="UTC")
        return ProviderRunResult("FRED", "skipped", 0, 0, 0, 0, "FRED_API_KEY missing", pipeline_run_id, started_at, completed_at)
    try:
        result: FredFetchResult = provider.fetch()
        normalized, _ = normalize_fred_fetch_result(result, config, pipeline_run_id)
        validation = validate_macro_records(normalized, config.stale_thresholds)
        if not dry_run:
            repository.insert_macro_observations(validation.accepted)
            _store_quality_events(repository, validation.events, pipeline_run_id)
            _store_dataset_catalog(repository, config, pd.Timestamp.now(tz="UTC"))
            ingestion_date = pd.Timestamp.now(tz="UTC").date().isoformat()
            for series_result in result.successful:
                series_dir = Path("data/raw/fred") / f"ingestion_date={ingestion_date}" / f"series_id={series_result.series_id}"
                parquet_path = series_dir / f"{pipeline_run_id}.parquet"
                metadata_path = series_dir / f"{pipeline_run_id}_metadata.json"
                write_atomic_parquet(series_result.observations, parquet_path)
                write_atomic_json(fred_metadata_sidecar(series_result, pipeline_run_id, ingestion_date), metadata_path)
        completed_at = pd.Timestamp.now(tz="UTC")
        status = "partial_success" if result.failed else "success"
        return ProviderRunResult("FRED", status, result.rows_fetched, len(validation.accepted), len(validation.rejected), sum(1 for event in validation.events if event.severity == "warning"), None if not result.failed else "; ".join(item["error"] for item in result.failed), pipeline_run_id, started_at, completed_at)
    except Exception as exc:
        completed_at = pd.Timestamp.now(tz="UTC")
        return ProviderRunResult("FRED", "failed", 0, 0, 0, 0, str(exc), pipeline_run_id, started_at, completed_at)


def _run_market(repository: DuckDBRepository, config, start: str, end: str | None, pipeline_run_id: str, symbols: list[str] | None, dry_run: bool) -> ProviderRunResult:
    started_at = pd.Timestamp.now(tz="UTC")
    provider = build_market_provider(config, start, end)
    if symbols:
        provider.symbols = [symbol for symbol in provider.symbols if symbol["internal_symbol"] in symbols]
    try:
        result: MarketFetchResult = provider.fetch()
        validation = validate_market_records(result.frame, config.stale_thresholds)
        if not dry_run:
            repository.insert_market_prices(validation.accepted)
            _store_quality_events(repository, validation.events, pipeline_run_id)
            _store_dataset_catalog(repository, config, pd.Timestamp.now(tz="UTC"))
            ingestion_date = pd.Timestamp.now(tz="UTC").date().isoformat()
            for symbol in validation.accepted["symbol"].drop_duplicates().tolist():
                subset = validation.accepted[validation.accepted["symbol"] == symbol]
                symbol_dir = Path("data/raw/market") / f"ingestion_date={ingestion_date}" / f"symbol={symbol}"
                write_atomic_parquet(subset, symbol_dir / f"{pipeline_run_id}.parquet")
        completed_at = pd.Timestamp.now(tz="UTC")
        status = "success" if not result.failed_symbols else "partial_success"
        return ProviderRunResult("yfinance", status, len(result.frame), len(validation.accepted), len(validation.rejected), sum(1 for event in validation.events if event.severity == "warning"), None if not result.failed_symbols else f"Missing symbols: {', '.join(result.failed_symbols)}", pipeline_run_id, started_at, completed_at)
    except Exception as exc:
        completed_at = pd.Timestamp.now(tz="UTC")
        return ProviderRunResult("yfinance", "failed", 0, 0, 0, 0, str(exc), pipeline_run_id, started_at, completed_at)


def main() -> int:
    args = parse_args()
    config = load_pipeline_config(Path.cwd())
    repository = DuckDBRepository(Path(args.database_path))
    repository.initialize()
    pipeline_run_id = new_pipeline_run_id()

    provider_results: list[ProviderRunResult] = []
    api_key = os.getenv("FRED_API_KEY", "").strip()

    if args.provider in {"all", "fred"}:
        provider_results.append(_run_fred(repository, config, api_key, args.start, args.end, pipeline_run_id, args.dry_run))
    if args.provider in {"all", "market"}:
        provider_results.append(_run_market(repository, config, args.start, args.end, pipeline_run_id, args.symbols, args.dry_run))

    if not args.dry_run:
        run_rows = pd.concat(
            [
                build_pipeline_run_row(
                    result.provider_name,
                    result.pipeline_run_id,
                    result.status,
                    args.start,
                    args.end,
                    _requested_datasets(args.provider if args.provider != "all" else "all", config),
                    result.rows_fetched,
                    result.rows_validated,
                    result.rows_rejected,
                    result.warning_count,
                    result.error_message,
                    result.started_at,
                    result.completed_at,
                )
                for result in provider_results
            ],
            ignore_index=True,
        )
        repository.insert_pipeline_run(run_rows)

    status_counts = {result.status for result in provider_results}
    if all(result.status == "failed" for result in provider_results):
        print("Pipeline completed with failures.")
        for result in provider_results:
            print(f"{result.provider_name}: {result.status} ({result.error_message or 'no details'})")
        return 1

    print(f"pipeline_run_id={pipeline_run_id}")
    for result in provider_results:
        print(f"{result.provider_name}: {result.status}, fetched={result.rows_fetched}, validated={result.rows_validated}, rejected={result.rows_rejected}")
        if result.error_message:
            print(f"  note: {result.error_message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

