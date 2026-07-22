"""Registry loader for indicator definitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from cross_asset_intelligence.core.config import load_phase3_config
from cross_asset_intelligence.core.exceptions import ConfigurationError

from .definitions import IndicatorDefinition
from .thresholds import SignalThresholds


@dataclass(frozen=True)
class IndicatorRegistry:
    """Collection of configured indicator definitions."""

    definitions: dict[str, IndicatorDefinition]
    thresholds: SignalThresholds

    def get(self, indicator_id: str) -> IndicatorDefinition:
        try:
            return self.definitions[indicator_id]
        except KeyError as exc:
            raise ConfigurationError(f"Unknown indicator: {indicator_id}") from exc


def _definition_from_config(config) -> IndicatorDefinition:
    return IndicatorDefinition(
        indicator_id=config.indicator_id,
        display_name=config.display_name,
        module=config.module,
        description=config.description,
        formula=config.formula,
        required_datasets=list(config.required_datasets),
        frequency=config.frequency,
        lookback_period=int(config.lookback_period),
        minimum_observations=int(config.minimum_observations),
        unit=config.unit,
        normal_range=tuple(config.normal_range) if config.normal_range is not None else None,
        warning_threshold=config.warning_threshold,
        extreme_threshold=config.extreme_threshold,
        bullish_interpretation=config.bullish_interpretation,
        bearish_interpretation=config.bearish_interpretation,
        limitations=list(config.limitations),
        failure_cases=list(config.failure_cases),
        freshness_requirement=config.freshness_requirement,
        directional_bias=config.directional_bias,
    )


def load_indicator_registry(root_dir: Path | None = None) -> IndicatorRegistry:
    """Load and validate the phase-3 indicator registry."""

    config = load_phase3_config(root_dir)
    definitions = [_definition_from_config(item) for item in config.indicators]
    if len(definitions) < 15:
        raise ConfigurationError("At least 15 indicators are required for Phase 3.")
    ids = [definition.indicator_id for definition in definitions]
    if len(ids) != len(set(ids)):
        raise ConfigurationError("Indicator IDs must be unique.")
    return IndicatorRegistry(
        definitions={definition.indicator_id: definition for definition in definitions},
        thresholds=SignalThresholds(**config.signal_thresholds),
    )

