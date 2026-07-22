"""Explicit liquidity-stress regime thresholds."""

from __future__ import annotations

import pandas as pd


def classify_liquidity_regime(score: float | None, confidence: str | float | None = None) -> str:
    if score is None or pd.isna(score) or confidence == "insufficient":
        return "Insufficient data"
    numeric = float(score) * 100.0 if 0.0 <= float(score) <= 1.0 else float(score)
    if numeric <= 20:
        return "Abundant"
    if numeric <= 45:
        return "Normal"
    if numeric <= 70:
        return "Tightening"
    return "Stressed"
