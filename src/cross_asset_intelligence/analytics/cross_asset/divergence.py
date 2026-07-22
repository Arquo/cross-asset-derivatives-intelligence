"""Cross-asset divergence rules."""

from __future__ import annotations

import pandas as pd


def classify_correlation_instability(corr_20d: float | None, corr_60d: float | None) -> float | None:
    if corr_20d is None or corr_60d is None or pd.isna(corr_20d) or pd.isna(corr_60d):
        return None
    return float(abs(corr_20d - corr_60d))


def classify_divergence(corr_20d: float | None, corr_60d: float | None, spread_zscore: float | None) -> str:
    if corr_20d is None or corr_60d is None or spread_zscore is None:
        return "Insufficient data"
    instability = classify_correlation_instability(corr_20d, corr_60d) or 0.0
    if instability >= 0.35 or abs(spread_zscore) >= 2.0:
        return "Diverging"
    if instability >= 0.2 or abs(spread_zscore) >= 1.0:
        return "Unstable"
    return "Stable"

