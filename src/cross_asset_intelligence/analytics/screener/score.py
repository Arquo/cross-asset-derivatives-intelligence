"""Transparent construction of the descriptive Market Pressure Score."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd


DEFAULT_PRESSURE_WEIGHTS = {
    "trend_momentum": 0.30,
    "volume_confirmation": 0.20,
    "volatility_condition": 0.20,
    "liquidity_condition": 0.15,
    "positioning_condition": 0.15,
}


@dataclass(frozen=True)
class MarketPressureResult:
    """Score result with the full weight audit trail."""

    score: float | None
    label: str
    confidence: str
    components: list[dict[str, float | str]]
    missing_components: list[str]
    available_weight: float


def pressure_label(score: float | None) -> str:
    if score is None or pd.isna(score):
        return "Insufficient data"
    if score >= 60:
        return "Strong bullish pressure"
    if score >= 20:
        return "Moderate bullish pressure"
    if score <= -60:
        return "Strong bearish pressure"
    if score <= -20:
        return "Moderate bearish pressure"
    return "Neutral"


def calculate_market_pressure_score(
    component_scores: Mapping[str, float | None],
    *,
    weights: Mapping[str, float] = DEFAULT_PRESSURE_WEIGHTS,
) -> MarketPressureResult:
    """Combine available component scores, redistributing unavailable weight."""

    available = {
        name: float(component_scores[name])
        for name in weights
        if name in component_scores and component_scores[name] is not None and pd.notna(component_scores[name])
    }
    missing = [name for name in weights if name not in available]
    available_weight = sum(float(weights[name]) for name in available)
    if available_weight < 0.40:
        return MarketPressureResult(None, "Insufficient data", "insufficient", [], missing, available_weight)

    components: list[dict[str, float | str]] = []
    total = 0.0
    for name, raw_score in available.items():
        bounded_score = max(-100.0, min(100.0, raw_score))
        effective_weight = float(weights[name]) / available_weight
        contribution = bounded_score * effective_weight
        total += contribution
        components.append(
            {
                "component": name,
                "raw_score": bounded_score,
                "base_weight": float(weights[name]),
                "effective_weight": effective_weight,
                "normalized_contribution": contribution,
            }
        )
    score = max(-100.0, min(100.0, total))
    confidence = "high" if available_weight >= 0.85 else "medium" if available_weight >= 0.65 else "low"
    return MarketPressureResult(score, pressure_label(score), confidence, components, missing, available_weight)
