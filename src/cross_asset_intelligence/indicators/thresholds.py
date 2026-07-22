"""Threshold helpers for signal normalization."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SignalThresholds:
    """Global score thresholds for signal strength."""

    weak: float = 0.25
    moderate: float = 0.5
    strong: float = 0.75
    extreme: float = 0.9
    stale_confidence_penalty: float = 0.2
    missing_confidence_penalty: float = 0.5
    unsupported_confidence_penalty: float = 0.35

