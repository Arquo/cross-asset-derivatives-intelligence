"""Configuration loading helpers for the free-data pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


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


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_pipeline_config(root_dir: Path | None = None) -> PipelineConfig:
    """Load configs/assets.yaml and configs/data_sources.yaml."""

    root = root_dir or Path(__file__).resolve().parents[3]
    assets = _load_yaml(root / "configs" / "assets.yaml")
    data_sources = _load_yaml(root / "configs" / "data_sources.yaml")

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
