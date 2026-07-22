"""Configuration loading helpers for the free-data pipeline and Phase 3 analytics."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cross_asset_intelligence.core.exceptions import ConfigurationError


@dataclass(frozen=True)
class FredSeriesConfig:
    """Configured FRED series entry."""

    series_id: str
    display_name: str
    category: str
    expected_frequency: str
    expected_unit: str
    source_type: str
    stale_after_days: int
    enabled: bool = True


@dataclass(frozen=True)
class MarketSymbolConfig:
    """Configured market symbol entry."""

    internal_symbol: str
    provider_symbol: str
    display_name: str
    asset_class: str
    currency: str
    timezone: str
    enabled: bool = True


@dataclass(frozen=True)
class ProviderConfig:
    """Configured provider entry."""

    provider_name: str
    implementation_status: str
    data_category: str
    expected_frequency: str
    source_type: str
    delayed: bool
    requires_credentials: bool
    timeout: int
    retry_count: int


@dataclass(frozen=True)
class PipelineConfig:
    """Loaded pipeline configuration."""

    fred_series: list[FredSeriesConfig]
    market_symbols: list[MarketSymbolConfig]
    providers: list[ProviderConfig]
    stale_thresholds: dict[str, int]


@dataclass(frozen=True)
class CFTCContractConfig:
    """Configured CFTC contract mapping."""

    internal_asset_id: str
    display_name: str
    cftc_contract_market_code: str | None
    official_contract_name: str
    report_type: str
    exchange: str
    asset_class: str
    contract_unit: str
    preferred_participant_categories: list[str] = field(default_factory=list)
    active: bool = True


@dataclass(frozen=True)
class IndicatorConfig:
    """Configured indicator definition used by deterministic analytics."""

    indicator_id: str
    display_name: str
    module: str
    description: str
    formula: str
    required_datasets: list[str]
    frequency: str
    lookback_period: int
    minimum_observations: int
    unit: str
    normal_range: tuple[float, float] | None
    warning_threshold: float | None
    extreme_threshold: float | None
    bullish_interpretation: str
    bearish_interpretation: str
    limitations: list[str]
    failure_cases: list[str]
    freshness_requirement: str
    directional_bias: str


@dataclass(frozen=True)
class ReportSettings:
    """Deterministic reporting defaults."""

    packet_version: str
    confidence_thresholds: dict[str, int]
    report_directory: str


@dataclass(frozen=True)
class Phase3Config:
    """Loaded Phase 3 configuration bundle."""

    cftc_contracts: list[CFTCContractConfig]
    indicators: list[IndicatorConfig]
    signal_thresholds: dict[str, dict[str, float]]
    report_settings: ReportSettings


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _resolve_root(root_dir: Path | None = None) -> Path:
    return root_dir or Path(__file__).resolve().parents[3]


def _load_config_file(root: Path, relative_path: str) -> dict[str, Any]:
    path = root / relative_path
    if not path.exists():
        raise ConfigurationError(f"Missing configuration file: {relative_path}")
    return _load_yaml(path)


def load_pipeline_config(root_dir: Path | None = None) -> PipelineConfig:
    """Load configs/assets.yaml and configs/data_sources.yaml."""

    root = _resolve_root(root_dir)
    assets = _load_config_file(root, "configs/assets.yaml")
    data_sources = _load_config_file(root, "configs/data_sources.yaml")

    asset_block = assets.get("assets", assets)

    fred_series = [
        FredSeriesConfig(**item)
        for item in asset_block.get("fred_series", [])
    ]
    market_symbols = [
        MarketSymbolConfig(**item)
        for item in asset_block.get("market_symbols", asset_block.get("market", []))
    ]
    providers = [
        ProviderConfig(**item)
        for item in data_sources.get("providers", [])
    ]
    stale_thresholds = asset_block.get("stale_thresholds", {})
    return PipelineConfig(
        fred_series=fred_series,
        market_symbols=market_symbols,
        providers=providers,
        stale_thresholds=stale_thresholds,
    )


def load_phase3_config(root_dir: Path | None = None) -> Phase3Config:
    """Load the Phase 3 YAML configuration files."""

    root = _resolve_root(root_dir)
    cftc = _load_config_file(root, "configs/cftc_contracts.yaml")
    indicators = _load_config_file(root, "configs/indicators.yaml")
    thresholds = _load_config_file(root, "configs/signal_thresholds.yaml")
    report_settings = _load_config_file(root, "configs/report_settings.yaml")

    cftc_contracts = [CFTCContractConfig(**item) for item in cftc.get("contracts", [])]
    indicator_defs = [IndicatorConfig(**item) for item in indicators.get("indicators", [])]
    signal_thresholds = thresholds.get("signal_thresholds", {})
    report = report_settings.get("report_settings", {})
    loaded_report = ReportSettings(
        packet_version=str(report.get("packet_version", "phase-3")),
        confidence_thresholds=dict(report.get("confidence_thresholds", {"low": 34, "medium": 67, "high": 100})),
        report_directory=str(report.get("report_directory", "data/reports")),
    )
    if not cftc_contracts:
        raise ConfigurationError("No CFTC contracts configured.")
    if not indicator_defs:
        raise ConfigurationError("No indicators configured.")
    return Phase3Config(
        cftc_contracts=cftc_contracts,
        indicators=indicator_defs,
        signal_thresholds=signal_thresholds,
        report_settings=loaded_report,
    )
