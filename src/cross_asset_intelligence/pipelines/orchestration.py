"""End-to-end ingestion orchestration for the Phase 2 data pipeline."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from cross_asset_intelligence.core.config import PipelineConfig, load_phase3_config, load_pipeline_config
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
from cross_asset_intelligence.pipelines.cftc_normalization import normalize_cftc_fetch_result
from cross_asset_intelligence.pipelines.validation import ValidationEvent, validate_macro_records, validate_market_records
from cross_asset_intelligence.services.data_status_service import classify_freshness
from cross_asset_intelligence.providers.cftc import CFTCProvider, CFTCFetchResult
from cross_asset_intelligence.providers.fred import FredFetchResult
from cross_asset_intelligence.providers.market import MarketFetchResult
from cross_asset_intelligence.providers.options import OptionsFetchResult, YFinanceOptionsProvider
from cross_asset_intelligence.storage.parquet_store import write_atomic_json, write_atomic_parquet
from cross_asset_intelligence.storage.repositories import DuckDBRepository


PIPELINE_NAME = "free_data_ingestion"
DEFAULT_START_DATE = "2015-01-01"
DEFAULT_DATABASE_PATH = Path("data/database/cross_asset.duckdb")
FRED_RAW_ROOT = Path("data/raw/fred")
MARKET_RAW_ROOT = Path("data/raw/market")
CFTC_RAW_ROOT = Path("data/raw/cftc")
OPTIONS_RAW_ROOT = Path("data/raw/options")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Phase 2 ingestion pipeline.")
    parser.add_argument("--provider", choices=["all", "fred", "market", "cftc", "options"], default="all")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--series", nargs="*", default=None)
    parser.add_argument("--contracts", nargs="*", default=None)
    parser.add_argument("--report-type", choices=["legacy", "disaggregated", "tff"], default=None)
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


def _selected_contracts(phase3_contracts: list, requested: list[str] | None, report_type: str | None) -> list:
    enabled = [contract for contract in phase3_contracts if contract.active and (report_type is None or contract.report_type == report_type)]
    if not requested:
        return enabled
    requested_set = set(requested)
    return [contract for contract in enabled if contract.internal_asset_id in requested_set]


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


def _store_cftc_raw_snapshots(result: CFTCFetchResult, pipeline_run_id: str) -> str:
    ingestion_date = pd.Timestamp.now(tz="UTC").date().isoformat()
    run_root = CFTC_RAW_ROOT / f"ingestion_date={ingestion_date}" / f"pipeline_run_id={pipeline_run_id}"
    for contract_frame in result.successful:
        contract_dir = run_root / f"internal_asset_id={contract_frame.contract.internal_asset_id}"
        parquet_path = contract_dir / "observations.parquet"
        metadata_path = contract_dir / "metadata.json"
        write_atomic_parquet(contract_frame.frame, parquet_path)
        write_atomic_json(
            {
                "pipeline_run_id": pipeline_run_id,
                "internal_asset_id": contract_frame.contract.internal_asset_id,
                "display_name": contract_frame.contract.display_name,
                "report_type": contract_frame.contract.report_type,
                "source_url": contract_frame.source_url,
                "ingestion_date": ingestion_date,
            },
            metadata_path,
        )
    return str(run_root)


def _store_options_raw_snapshots(result: OptionsFetchResult, pipeline_run_id: str) -> dict[str, str]:
    """Persist every options retrieval under its immutable snapshot ID."""

    locations: dict[str, str] = {}
    for snapshot in result.successful:
        snapshot_root = OPTIONS_RAW_ROOT / f"symbol={snapshot.symbol}" / f"snapshot_id={snapshot.snapshot_id}"
        write_atomic_parquet(snapshot.frame, snapshot_root / "contracts.parquet")
        write_atomic_json(
            {
                "pipeline_run_id": pipeline_run_id,
                "snapshot_id": snapshot.snapshot_id,
                "symbol": snapshot.symbol,
                "quote_timestamp": snapshot.quote_timestamp.isoformat(),
                "underlying_price": snapshot.underlying_price,
                "source_label": "yfinance/Yahoo Finance (research-grade, replaceable)",
            },
            snapshot_root / "metadata.json",
        )
        locations[snapshot.snapshot_id] = str(snapshot_root)
    return locations


def _build_dataset_catalog_rows(
    config: PipelineConfig,
    repository: DuckDBRepository,
    provider_status: dict[str, str],
    phase3_contracts: list | None = None,
    option_symbols: list[str] | None = None,
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

    for contract in phase3_contracts or []:
        dataset_id = f"cftc_{contract.internal_asset_id}"
        latest = repository.fetch_dataframe(
            "SELECT report_date, publication_date, available_ts, ingested_ts, quality_status, COUNT(*) OVER () AS record_count FROM cftc_positioning_observations WHERE internal_asset_id = ? ORDER BY report_date DESC LIMIT 1",
            (contract.internal_asset_id,),
        )
        if latest.empty:
            rows.append(
                {
                    "dataset_id": dataset_id,
                    "dataset_name": contract.display_name,
                    "provider": "CFTC",
                    "display_name": contract.display_name,
                    "category": contract.asset_class,
                    "frequency": "weekly",
                    "expected_publication_delay_days": 3,
                    "unit": contract.contract_unit,
                    "source_type": "official",
                    "is_delayed": True,
                    "requires_credentials": False,
                    "last_successful_ingestion": None,
                    "latest_ingestion_ts": None,
                    "latest_observation_ts": None,
                    "age_days": None,
                    "freshness_status": "Missing",
                    "quality_status": "missing",
                    "record_count": 0,
                    "latest_pipeline_status": provider_status.get("CFTC"),
                    "warning_message": "No ingested rows yet.",
                }
            )
            continue
        latest_row = latest.iloc[0]
        latest_report_date = pd.to_datetime(latest_row["report_date"], utc=True, errors="coerce")
        latest_available_ts = pd.to_datetime(latest_row["available_ts"], utc=True, errors="coerce")
        latest_ingestion_ts = pd.to_datetime(latest_row["ingested_ts"], utc=True, errors="coerce")
        rows.append(
            {
                "dataset_id": dataset_id,
                "dataset_name": contract.display_name,
                "provider": "CFTC",
                "display_name": contract.display_name,
                "category": contract.asset_class,
                "frequency": "weekly",
                "expected_publication_delay_days": 3,
                "unit": contract.contract_unit,
                "source_type": "official",
                "is_delayed": True,
                "requires_credentials": False,
                "last_successful_ingestion": latest_ingestion_ts,
                "latest_ingestion_ts": latest_ingestion_ts,
                "latest_observation_ts": latest_report_date,
                "age_days": (now - latest_available_ts).total_seconds() / 86400.0,
                "freshness_status": classify_freshness(latest_available_ts, latest_ingestion_ts, 3, provider_status.get("CFTC"), str(latest_row["quality_status"])),
                "quality_status": str(latest_row["quality_status"]),
                "record_count": int(latest_row["record_count"]),
                "latest_pipeline_status": provider_status.get("CFTC"),
                "warning_message": "CFTC data is weekly and delayed.",
            }
        )

    for symbol in option_symbols or []:
        dataset_id = f"options_{symbol.lower()}"
        latest = repository.fetch_dataframe(
            "SELECT quote_timestamp, ingested_ts, quality_status, COUNT(*) OVER () AS record_count FROM option_contract_snapshots WHERE symbol = ? ORDER BY quote_timestamp DESC LIMIT 1",
            (symbol,),
        )
        latest_row = latest.iloc[0] if not latest.empty else None
        latest_quote = pd.to_datetime(latest_row["quote_timestamp"], utc=True, errors="coerce") if latest_row is not None else None
        latest_ingestion = pd.to_datetime(latest_row["ingested_ts"], utc=True, errors="coerce") if latest_row is not None else None
        rows.append(
            {
                "dataset_id": dataset_id,
                "dataset_name": f"{symbol} option chains",
                "provider": "yfinance-options",
                "display_name": f"{symbol} option chains",
                "category": "options",
                "frequency": "snapshot",
                "expected_publication_delay_days": 1,
                "unit": "option contract",
                "source_type": "vendor",
                "is_delayed": True,
                "requires_credentials": False,
                "last_successful_ingestion": latest_ingestion,
                "latest_ingestion_ts": latest_ingestion,
                "latest_observation_ts": latest_quote,
                "age_days": (now - latest_quote).total_seconds() / 86400.0 if latest_quote is not None else None,
                "freshness_status": classify_freshness(latest_quote, latest_ingestion, 1, provider_status.get("yfinance-options"), str(latest_row["quality_status"])) if latest_row is not None else "Missing",
                "quality_status": str(latest_row["quality_status"]) if latest_row is not None else "missing",
                "record_count": int(latest_row["record_count"]) if latest_row is not None else 0,
                "latest_pipeline_status": provider_status.get("yfinance-options"),
                "warning_message": "Research-grade, replaceable free-provider snapshot." if latest_row is not None else "No option snapshot stored yet.",
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


def _run_cftc(
    repository: DuckDBRepository,
    config: PipelineConfig,
    phase3_contracts: list,
    start_date: str,
    end_date: str | None,
    pipeline_run_id: str,
    requested_contracts: list[str] | None,
    report_type: str | None,
    dry_run: bool,
) -> ProviderRunResult:
    started_at = pd.Timestamp.now(tz="UTC")
    selected_contracts = _selected_contracts(phase3_contracts, requested_contracts, report_type)
    provider = CFTCProvider(contracts=selected_contracts, start_date=start_date, end_date=end_date)
    raw_location: str | None = None
    try:
        result: CFTCFetchResult = provider.fetch()
        if not result.successful and result.failed:
            error_message = "; ".join(item["error"] for item in result.failed)
            return ProviderRunResult("CFTC", "failed", result.rows_fetched, 0, 0, 0, error_message, pipeline_run_id, started_at, pd.Timestamp.now(tz="UTC"))
        if not result.successful:
            return ProviderRunResult("CFTC", "failed", 0, 0, 0, 0, "CFTC returned no rows.", pipeline_run_id, started_at, pd.Timestamp.now(tz="UTC"))
        raw_location = _store_cftc_raw_snapshots(result, pipeline_run_id) if not dry_run else None
        normalized, warnings = normalize_cftc_fetch_result(result, pipeline_run_id)
        if not dry_run and not normalized.empty:
            repository.insert_cftc_positioning_observations(normalized)
            repository.insert_cftc_contract_mappings(
                pd.DataFrame(
                    [
                        {
                            "internal_asset_id": contract.internal_asset_id,
                            "display_name": contract.display_name,
                            "cftc_contract_market_code": contract.cftc_contract_market_code,
                            "official_contract_name": contract.official_contract_name,
                            "report_type": contract.report_type,
                            "exchange": contract.exchange,
                            "asset_class": contract.asset_class,
                            "contract_unit": contract.contract_unit,
                            "preferred_participant_categories": contract.preferred_participant_categories,
                            "active": contract.active,
                        }
                        for contract in selected_contracts
                    ]
                )
            )
            if not warnings.empty:
                warning_events = [
                    ValidationEvent(
                        dataset_id=f"cftc_{row['internal_asset_id']}",
                        record_id=None,
                        severity="warning",
                        rule_name="cftc_normalization",
                        message=row["message"],
                    )
                    for _, row in warnings.iterrows()
                ]
                _store_quality_events(repository, warning_events, pipeline_run_id)
        if not dry_run:
            catalog = _build_dataset_catalog_rows(config, repository, {"FRED": None, "yfinance": None, "CFTC": "completed_with_warnings" if not warnings.empty else "completed"}, phase3_contracts=selected_contracts)
            repository.upsert_dataset_catalog(catalog)
        completed_at = pd.Timestamp.now(tz="UTC")
        warning_count = len(warnings)
        return ProviderRunResult("CFTC", "completed_with_warnings" if warning_count or result.failed else "completed", result.rows_fetched, len(normalized), 0, warning_count, None if not result.failed else "; ".join(item["error"] for item in result.failed), pipeline_run_id, started_at, completed_at)
    except Exception as exc:
        return ProviderRunResult("CFTC", "failed", 0, 0, 0, 0, str(exc), pipeline_run_id, started_at, pd.Timestamp.now(tz="UTC"))


def _run_options(
    repository: DuckDBRepository,
    pipeline_run_id: str,
    symbols: list[str] | None,
    dry_run: bool,
) -> ProviderRunResult:
    started_at = pd.Timestamp.now(tz="UTC")
    selected_symbols = [symbol.upper() for symbol in (symbols or ["SPY", "QQQ"])]
    provider = YFinanceOptionsProvider(selected_symbols)
    try:
        result = provider.fetch()
        if not result.successful:
            error_message = "; ".join(item["error"] for item in result.failed) if result.failed else "No option chains returned."
            return ProviderRunResult("yfinance-options", "failed", 0, 0, 0, 0, error_message, pipeline_run_id, started_at, pd.Timestamp.now(tz="UTC"))
        locations = _store_options_raw_snapshots(result, pipeline_run_id) if not dry_run else {}
        frames: list[pd.DataFrame] = []
        for snapshot in result.successful:
            frame = snapshot.frame.copy()
            frame["pipeline_run_id"] = pipeline_run_id
            frame["raw_snapshot_location"] = locations.get(snapshot.snapshot_id)
            frames.append(frame)
        combined = pd.concat(frames, ignore_index=True)
        if not dry_run:
            repository.insert_option_contract_snapshots(combined)
            status = "completed_with_warnings" if result.failed else "completed"
            catalog = _build_dataset_catalog_rows(
                load_pipeline_config(Path.cwd()),
                repository,
                {"FRED": None, "yfinance": None, "yfinance-options": status},
                option_symbols=selected_symbols,
            )
            repository.upsert_dataset_catalog(catalog)
        completed_at = pd.Timestamp.now(tz="UTC")
        status = "completed_with_warnings" if result.failed else "completed"
        error_message = "; ".join(f"{item.get('symbol')} {item.get('expiration')}: {item.get('error')}" for item in result.failed) or None
        return ProviderRunResult(
            "yfinance-options",
            status,
            result.rows_fetched,
            len(combined),
            0,
            len(result.failed),
            error_message,
            pipeline_run_id,
            started_at,
            completed_at,
        )
    except Exception as exc:
        return ProviderRunResult("yfinance-options", "failed", 0, 0, 0, 0, str(exc), pipeline_run_id, started_at, pd.Timestamp.now(tz="UTC"))


def run_pipeline(
    provider_choice: str,
    start_date: str,
    end_date: str | None,
    symbols: list[str] | None,
    series: list[str] | None,
    database_path: Path,
    dry_run: bool = False,
    contracts: list[str] | None = None,
    report_type: str | None = None,
) -> list[ProviderRunResult]:
    load_dotenv()
    config = load_pipeline_config(Path.cwd())
    phase3_config = load_phase3_config(Path.cwd())
    repository = DuckDBRepository(database_path)
    repository.initialize()
    pipeline_run_id = new_pipeline_run_id()
    api_key = os.getenv("FRED_API_KEY", "").strip()

    provider_results: list[ProviderRunResult] = []
    if provider_choice in {"all", "fred"}:
        provider_results.append(_run_fred(repository, config, api_key, start_date, end_date, pipeline_run_id, dry_run))
    if provider_choice in {"all", "market"}:
        provider_results.append(_run_market(repository, config, start_date, end_date, pipeline_run_id, symbols, dry_run))
    if provider_choice in {"all", "cftc"}:
        provider_results.append(
            _run_cftc(
                repository,
                config,
                phase3_config.cftc_contracts,
                start_date,
                end_date,
                pipeline_run_id,
                contracts,
                report_type,
                dry_run,
            )
        )
    if provider_choice in {"all", "options"}:
        provider_results.append(_run_options(repository, pipeline_run_id, symbols, dry_run))

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
                    _selected_series(config, series)
                    if result.provider_name == "FRED"
                    else ([symbol.upper() for symbol in (symbols or ["SPY", "QQQ"])] if result.provider_name == "yfinance-options" else _selected_symbols(config, symbols)),
                    result.rows_fetched,
                    result.rows_validated,
                    result.rows_rejected,
                    result.warning_count,
                    result.error_message,
                    str(
                        (
                            FRED_RAW_ROOT
                            if result.provider_name == "FRED"
                            else MARKET_RAW_ROOT
                            if result.provider_name == "yfinance"
                            else OPTIONS_RAW_ROOT
                            if result.provider_name == "yfinance-options"
                            else CFTC_RAW_ROOT
                        )
                        / f"pipeline_run_id={result.pipeline_run_id}"
                    ),
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
        contracts=args.contracts,
        report_type=args.report_type,
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
    parser.add_argument("--provider", choices=["all", "fred", "market", "cftc", "options"], default="all")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--series", nargs="*", default=None)
    parser.add_argument("--contracts", nargs="*", default=None)
    parser.add_argument("--report-type", choices=["legacy", "disaggregated", "tff"], default=None)
    parser.add_argument("--database-path", default=str(DEFAULT_DATABASE_PATH))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)
