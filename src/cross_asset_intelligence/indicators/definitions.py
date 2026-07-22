"""Indicator definition models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IndicatorDefinition:
    """Human-readable indicator definition."""

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
    limitations: list[str] = field(default_factory=list)
    failure_cases: list[str] = field(default_factory=list)
    freshness_requirement: str = "daily"
    directional_bias: str = "context-dependent"

