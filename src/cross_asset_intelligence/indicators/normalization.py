"""Normalization routines for indicator values and signal strength."""

from __future__ import annotations

import math

from cross_asset_intelligence.analytics.common import normalize_score

from .definitions import IndicatorDefinition
from .thresholds import SignalThresholds


def normalize_indicator_value(value: float | None, definition: IndicatorDefinition) -> float | None:
    """Normalize a raw indicator value using the configured range and bias."""

    if value is None:
        return None
    normal_range = definition.normal_range
    if normal_range is None:
        return float(max(min(value, 1.0), -1.0))
    lower, upper = normal_range
    invert = definition.directional_bias.lower() == "higher is bearish"
    return normalize_score(float(value), lower=lower, upper=upper, invert=invert)


def signal_strength(score: float | None, thresholds: SignalThresholds) -> str:
    if score is None or math.isnan(score):
        return "Unknown"
    abs_score = abs(float(score))
    if abs_score >= thresholds.extreme:
        return "Extreme"
    if abs_score >= thresholds.strong:
        return "Strong"
    if abs_score >= thresholds.moderate:
        return "Moderate"
    if abs_score >= thresholds.weak:
        return "Weak"
    return "Weak"


def bounded_score(value: float | None) -> float | None:
    if value is None:
        return None
    return max(min(float(value), 1.0), -1.0)

