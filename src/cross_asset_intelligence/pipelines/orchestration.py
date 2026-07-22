"""End-to-end ingestion orchestration for the Phase 2 data pipeline."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from cross_asset_intelligence.core.config import PipelineConfig, load_pipeline_config
from cross_asset_intelligence.pipelines.ingestion import (
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
from cross_asset_intelligence.services.data_status_service import classify_freshness
from cross_asset_intelligence.providers.fred import FredFetchResult
from cross_asset_intelligence.providers.market import MarketFetchResult
from cross_asset_intelligence.storage.parquet_store import write_atomic_json, write_atomic_parquet
from cross_asset_intelligence.storage.repositories import DuckDBRepository


PIPELINE_NAME = "free_data_ingestion"
DEFAULT_START_DATE = "2015-01-01"
DEFAULT_DATABASE_PATH = Path("data/database/cross_asset.duckdb")
FRED_RAW_ROOT = Path("data/raw/fred")
MARKET_RAW_ROOT = Path("data/raw/market")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Phase 2 ingestion pipeline.")
    parser.add_argument("--provider", choices=["all", "fred", "market"], default="all")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--series", nargs="*", default=None)
    parser.add_argument("--database-path", default=str(DEFAULT_DATABASE_PATH))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _selected_series(config: PipelineConfig, requested: list[str] | None) -> list[str]:
    enabled = [series.series_id for series in config.fred_series if series.enabled]
    if not requested:
        return enabled
    return [series_id for series_id in enabled if series_id in set(requested)]


def _selected_symbols(config: PipelineConfig, requested: list[str] | None) -> list[str]:
    enabled = [symbol.internal_symbol for symbol in config.market_symbols if symbol.enabled]
    if not requested:
        return enabled
    return [symbol for symbol in enabled if symbol in set(requested)]


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
                "rule_id": event.rule_name,
                "message": event.message,
                "created_at": pd.Timestamp.now(tz="UTC"),
            }
            for index, event in enumerate(events, start=1)
        ]
    )
    repository.insert_quality_events(rows)


def _store_fred_raw_snapshots(result: FredFetchResult, pipeline_run_id: str, start_date: str) -> str:
    ingestion_date = pd.Timestamp.now(tz="UTC").date().isoformat()
    run_root = FRED_RAW_ROOT / f"ingestion_date={ingestion_date}" / f"pipeline_run_id={pipeline_run_id}"
    for series_result in result.successful:
        series_dir = run_root / f"series_id={series_result.series_id}"
        parquet_path = series_dir / "observations.parquet"
        metadata_path = series_dir / "metadata.json"
        write_atomic_parquet(series_result.observations, parquet_path)
        write_atomic_json(fred_metadata_sidecar(series_result, pipeline_run_id, ingestion_date), metadata_path)
    return str(run_root)


def _store_market_raw_snapshot(frame: pd.DataFrame, pipeline_run_id: str) -> str:
    ingestion_date = pd.Timestamp.now(tz="UTC").date().isoformat()
    run_root = MARKET_RAW_ROOT / f"ingestion_date={ingestion_date}" / f"pipeline_run_id={pipeline_run_id}"
    write_atomic_parquet(frame, run_root / "observations.parquet")
    return str(run_root)


def _build_dataset_catalog_rows(
    config: PipelineConfig,
    repository: DuckDBRepository,
    provider_status: dict[str, str],
) -> pd.DataFrame:
    now = pd.Timestamp.now(tz="UTC")
    rows: list[dict[str, object]] = []

    for series in config.fred_series:
        dataset_id = f"fred_{series.series_id.lower()}"
        latest = repository.fetch_dataframe(
            "SELECT observation_ts, ingested_ts, quality_status, COUNT(*) OVER () AS record_count FROM macro_observations WHERE dataset_id = ? ORDER BY observation_ts DESC LIMIT 1",
            (dataset_id,),
        )
        if latest.empty:
            rows.append(
                {
                    "dataset_id": dataset_id,
                    "dataset_name": series.display_name,
                    "provider": "FRED",
                    "display_name": series.display_name,
                    "category": series.category,
                    "frequency": series.expected_frequency,
                    "expected_publication_delay_days": series.stale_after_days,
                    "unit": series.expected_unit,
                    "source_type": series.source_type,
                    "is_delayed": True,
                    "requires_credentials": True,
                    "last_successful_ingestion": None,
                    "latest_ingestion_ts": None,
                    "latest_observation_ts": None,
                    "age_days": None,
                    "freshness_status": "Missing",
                    "quality_status": "missing",
                    "record_count": 0,
                    "latest_pipeline_status": provider_status.get("FRED"),
                    "warning_message": "No ingested rows yet.",
                }
            )
            continue
        latest_row = latest.iloc[0]
        latest_observation_ts = pd.to_datetime(latest_row["observation_ts"], utc=True, errors="coerce")
        latest_ingestion_ts = pd.to_datetime(latest_row["ingested_ts"], utc=True, errors="coerce")
        rows.append(
            {
                "dataset_id": dataset_id,
                "dataset_name": series.display_name,
                "provider": "FRED",
                "display_name": series.display_name,
                "category": series.category,
                "frequency": series.expected_frequency,
                "expected_publication_delay_days": series.stale_after_days,
                "unit": series.expected_unit,
                "source_type": series.source_type,
                "is_delayed": True,
                "requires_credentials": True,
                "last_successful_ingestion": latest_ingestion_ts,
                "latest_ingestion_ts": latest_ingestion_ts,
                "latest_observation_ts": latest_observation_ts,
                "age_days": (now - latest_observation_ts).total_seconds() / 86400.0,
                "freshness_status": classify_freshness(latest_observation_ts, latest_ingestion_ts, series.stale_after_days, provider_status.get("FRED"), str(latest_row["quality_status"])),
                "quality_status": str(latest_row["quality_status"]),
                "record_count": int(latest_row["record_count"]),
                "latest_pipeline_status": provider_status.get("FRED"),
                "warning_message": None,
            }
        )

    for symbol in config.market_symbols:
        dataset_id = f"market_{symbol.internal_symbol.lower()}"
        latest = repository.fetch_dataframe(
            "SELECT observation_ts, ingested_ts, quality_status, COUNT(*) OVER () AS record_count FROM market_observations WHERE dataset_id = ? ORDER BY observation_ts DESC LIMIT 1",
            (dataset_id,),
        )
        if latest.empty:
            rows.append(
                {
                    "dataset_id": dataset_id,
                    "dataset_name": symbol.display_name,
                    "provider": "yfinance/Yahoo Finance",
                    "display_name": symbol.display_name,
                    "category": symbol.asset_class,
                    "frequency": "daily",
                    "expected_publication_delay_days": 3,
                    "unit": "price",
                    "source_type": "vendor",
                    "is_delayed": True,
                    "requires_credentials": False,
                    "last_successful_ingestion": None,
                    "latest_ingestion_ts": None,
                    "latest_observation_ts": None,
                    "age_days": None,
                    "freshness_status": "Missing",
                    "quality_status": "missing",
                    "record_count": 0,
                    "latest_pipeline_status": provider_status.get("yfinance"),
                    "warning_message": "No ingested rows yet.",
                }
            )
            continue
        latest_row = latest.iloc[0]
        latest_observation_ts = pd.to_datetime(latest_row["observation_ts"], utc=True, errors="coerce")
        latest_ingestion_ts = pd.to_datetime(latest_row["ingested_ts"], utc=True, errors="coerce")
        rows.append(
            {
                "dataset_id": dataset_id,
                "dataset_name": symbol.display_name,
                "provider": "yfinance/Yahoo Finance",
                "display_name": symbol.display_name,
                "category": symbol.asset_class,
                "frequency": "daily",
                "expected_publication_delay_days": 3,
                "unit": "price",
                "source_type": "vendor",
                "is_delayed": True,
                "requires_credentials": False,
                "last_successful_ingestion": latest_ingestion_ts,
                "latest_ingestion_ts": latest_ingestion_ts,
                "latest_observation_ts": latest_observation_ts,
                "age_days": (now - latest_observation_ts).total_seconds() / 86400.0,
                "freshness_status": classify_freshness(latest_observation_ts, latest_ingestion_ts, 3, provider_status.get("yfinance"), str(latest_row["quality_status"])),
                "quality_status": str(latest_row["quality_status"]),
                "record_count": int(latest_row["record_count"]),
                "latest_pipeline_status": provider_status.get("yfinance"),
                "warning_message": None,
            }
        )

    return pd.DataFrame(rows)


def _run_fred(repository: DuckDBRepository, config: PipelineConfig, api_key: str | None, start_date: str, end_date: str | None, pipeline_run_id: str, dry_run: bool) -> ProviderRunResult:
    started_at = pd.Timestamp.now(tz="UTC")
    provider = build_fred_provider(config, api_key, start_date)
    raw_location: str | None = None
    if not api_key:
        return ProviderRunResult("FRED", "failed", 0, 0, 0, 0, "FRED_API_KEY is not configured.", pipeline_run_id, started_at, pd.Timestamp.now(tz="UTC"))
    try:
        result: FredFetchResult = provider.fetch()
        if not result.successful:
            error_message = "; ".join(item["error"] for item in result.failed) if result.failed else "FRED returned no series."
            return ProviderRunResult("FRED", "failed", result.rows_fetched, 0, 0, 0, error_message, pipeline_run_id, started_at, pd.Timestamp.now(tz="UTC"))
        raw_location = _store_fred_raw_snapshots(result, pipeline_run_id, start_date) if not dry_run else None
        normalized, _ = normalize_fred_fetch_result(result, config, pipeline_run_id)
        validation = validate_macro_records(normalized, config.stale_thresholds)
        if not dry_run:
            repository.insert_macro_observations(validation.accepted)
            _store_quality_events(repository, validation.events, pipeline_run_id)
        completed_at = pd.Timestamp.now(tz="UTC")
        status = "completed_with_warnings" if result.failed or validation.events else "completed"
        provider_status = status
        if not dry_run:
            catalog = _build_dataset_catalog_rows(config, repository, {"FRED": provider_status, "yfinance": None})
            repository.upsert_dataset_catalog(catalog)
        return ProviderRunResult("FRED", status, result.rows_fetched, len(validation.accepted), len(validation.rejected), sum(1 for event in validation.events if event.severity == "warning"), None if not result.failed else "; ".join(item["error"] for item in result.failed), pipeline_run_id, started_at, completed_at)
    except Exception as exc:
        return ProviderRunResult("FRED", "failed", 0, 0, 0, 0, str(exc), pipeline_run_id, started_at, pd.Timestamp.now(tz="UTC"))


def _run_market(repository: DuckDBRepository, config: PipelineConfig, start_date: str, end_date: str | None, pipeline_run_id: str, symbols: list[str] | None, dry_run: bool) -> ProviderRunResult:
    started_at = pd.Timestamp.now(tz="UTC")
    provider = build_market_provider(config, start_date, end_date)
    symbol_filter = set(symbols or [])
    raw_location: str | None = None
    if symbol_filter:
        provider.symbols = [symbol for symbol in provider.symbols if symbol["internal_symbol"] in symbol_filter]
    try:
        result: MarketFetchResult = provider.fetch()
        if result.frame.empty:
            return ProviderRunResult("yfinance", "failed", 0, 0, 0, 0, "yfinance returned no rows.", pipeline_run_id, started_at, pd.Timestamp.now(tz="UTC"))
        raw_location = _store_market_raw_snapshot(result.frame, pipeline_run_id) if not dry_run else None
        validation = validate_market_records(result.frame, config.stale_thresholds)
        if not dry_run:
            repository.insert_market_observations(validation.accepted)
            _store_quality_events(repository, validation.events, pipeline_run_id)
        completed_at = pd.Timestamp.now(tz="UTC")
        status = "completed_with_warnings" if result.failed_symbols or validation.events else "completed"
        if not dry_run:
            catalog = _build_dataset_catalog_rows(config, repository, {"FRED": None, "yfinance": status})
            repository.upsert_dataset_catalog(catalog)
        return ProviderRunResult("yfinance", status, len(result.frame), len(validation.accepted), len(validation.rejected), sum(1 for event in validation.events if event.severity == "warning"), None if not result.failed_symbols else f"Missing symbols: {', '.join(result.failed_symbols)}", pipeline_run_id, started_at, completed_at)
    except Exception as exc:
        return ProviderRunResult("yfinance", "failed", 0, 0, 0, 0, str(exc), pipeline_run_id, started_at, pd.Timestamp.now(tz="UTC"))


def run_pipeline(provider_choice: str, start_date: str, end_date: str | None, symbols: list[str] | None, series: list[str] | None, database_path: Path, dry_run: bool = False) -> list[ProviderRunResult]:
    load_dotenv()
    config = load_pipeline_config(Path.cwd())
    repository = DuckDBRepository(database_path)
    repository.initialize()
    pipeline_run_id = new_pipeline_run_id()
    api_key = os.getenv("FRED_API_KEY", "").strip()

    provider_results: list[ProviderRunResult] = []
    if provider_choice in {"all", "fred"}:
        provider_results.append(_run_fred(repository, config, api_key, start_date, end_date, pipeline_run_id, dry_run))
    if provider_choice in {"all", "market"}:
        provider_results.append(_run_market(repository, config, start_date, end_date, pipeline_run_id, symbols, dry_run))

    if not dry_run:
        run_rows = pd.concat(
            [
                build_pipeline_run_row(
                    result.provider_name,
                    result.pipeline_run_id,
                    PIPELINE_NAME,
                    result.status,
                    start_date,
                    end_date,
                    _selected_series(config, series) if result.provider_name == "FRED" else _selected_symbols(config, symbols),
                    result.rows_fetched,
                    result.rows_validated,
                    result.rows_rejected,
                    result.warning_count,
                    result.error_message,
                    str((FRED_RAW_ROOT if result.provider_name == "FRED" else MARKET_RAW_ROOT) / f"pipeline_run_id={result.pipeline_run_id}"),
                    result.started_at,
                    result.completed_at,
                )
                for result in provider_results
            ],
            ignore_index=True,
        )
        repository.insert_pipeline_run(run_rows)

    return provider_results


def main(argv: list[str] | None = None) -> int:
    args = parse_args() if argv is None else parse_args_from_list(argv)
    results = run_pipeline(
        provider_choice=args.provider,
        start_date=args.start_date,
        end_date=args.end_date,
        symbols=args.symbols,
        series=args.series,
        database_path=Path(args.database_path),
        dry_run=args.dry_run,
    )
    if all(result.status == "failed" for result in results):
        print("Pipeline completed with failures.")
        for result in results:
            print(f"{result.provider_name}: {result.status} ({result.error_message or 'no details'})")
        return 1
    pipeline_run_id = results[0].pipeline_run_id if results else "n/a"
    print(f"pipeline_run_id={pipeline_run_id}")
    for result in results:
        print(f"{result.provider_name}: {result.status}, received={result.rows_fetched}, validated={result.rows_validated}, rejected={result.rows_rejected}")
        if result.error_message:
            print(f"  note: {result.error_message}")
    return 0


def parse_args_from_list(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Phase 2 ingestion pipeline.")
    parser.add_argument("--provider", choices=["all", "fred", "market"], default="all")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--series", nargs="*", default=None)
    parser.add_argument("--database-path", default=str(DEFAULT_DATABASE_PATH))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)
