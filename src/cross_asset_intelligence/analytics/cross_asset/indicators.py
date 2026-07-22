"""Cross-asset relationship calculations."""

from __future__ import annotations

import pandas as pd

from cross_asset_intelligence.analytics.common import historical_percentile, rolling_beta, rolling_correlation, rolling_zscore

from .divergence import classify_correlation_instability, classify_divergence


def compute_rolling_relationships(left: pd.DataFrame, right: pd.DataFrame, *, left_symbol: str, right_symbol: str) -> pd.DataFrame:
    """Align two asset series and compute rolling relationships."""

    if left.empty or right.empty:
        return pd.DataFrame()
    left_frame = left[left["symbol"] == left_symbol].copy()
    right_frame = right[right["symbol"] == right_symbol].copy()
    if left_frame.empty or right_frame.empty:
        return pd.DataFrame()
    left_frame["observation_ts"] = pd.to_datetime(left_frame["observation_ts"], utc=True, errors="coerce")
    right_frame["observation_ts"] = pd.to_datetime(right_frame["observation_ts"], utc=True, errors="coerce")
    left_frame = left_frame.sort_values("observation_ts")
    right_frame = right_frame.sort_values("observation_ts")
    merged = left_frame[["observation_ts", "adjusted_close"]].rename(columns={"adjusted_close": "left_close"}).merge(
        right_frame[["observation_ts", "adjusted_close"]].rename(columns={"adjusted_close": "right_close"}),
        on="observation_ts",
        how="inner",
    )
    if merged.empty:
        return merged
    merged["left_return"] = merged["left_close"].pct_change()
    merged["right_return"] = merged["right_close"].pct_change()
    merged["corr_20d"] = rolling_correlation(merged["left_return"], merged["right_return"], 20)
    merged["corr_60d"] = rolling_correlation(merged["left_return"], merged["right_return"], 60)
    merged["beta_60d"] = rolling_beta(merged["left_return"], merged["right_return"], 60)
    merged["spread"] = merged["left_close"] - merged["right_close"]
    merged["spread_zscore"] = rolling_zscore(merged["spread"], 20)
    merged["instability_score"] = [classify_correlation_instability(c20, c60) for c20, c60 in zip(merged["corr_20d"], merged["corr_60d"], strict=False)]
    merged["divergence_status"] = [classify_divergence(c20, c60, z) for c20, c60, z in zip(merged["corr_20d"], merged["corr_60d"], merged["spread_zscore"], strict=False)]
    return merged.reset_index(drop=True)


def build_cross_asset_summary(left: pd.DataFrame, right: pd.DataFrame, *, left_symbol: str, right_symbol: str) -> pd.DataFrame:
    """Return the latest cross-asset relationship snapshot."""

    relationships = compute_rolling_relationships(left, right, left_symbol=left_symbol, right_symbol=right_symbol)
    if relationships.empty:
        return relationships
    latest = relationships.tail(1).copy()
    latest["relation_label"] = f"{left_symbol} vs {right_symbol}"
    return latest.reset_index(drop=True)

