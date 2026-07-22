"""Deterministic CFTC positioning calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .classification import classify_positioning_bucket, classify_positioning_risk


def _rolling_percentile(series: pd.Series, window: int, minimum: int) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")

    def rank_latest(values: np.ndarray) -> float:
        clean = values[~np.isnan(values)]
        if clean.size == 0 or np.isnan(values[-1]):
            return np.nan
        return float((clean <= values[-1]).sum() / clean.size)

    return numeric.rolling(window, min_periods=minimum).apply(rank_latest, raw=True)


def _rolling_zscore(series: pd.Series, window: int = 52, minimum: int = 20) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    mean = numeric.rolling(window, min_periods=minimum).mean()
    std = numeric.rolling(window, min_periods=minimum).std(ddof=0)
    return (numeric - mean) / std.replace(0, np.nan)


def _price_trend(price_history: pd.DataFrame | None, asset_id: str) -> float | None:
    if price_history is None or price_history.empty or "asset_id" not in price_history.columns:
        return None
    subset = price_history[price_history["asset_id"] == asset_id].copy()
    if subset.empty:
        return None
    subset = subset.sort_values("observation_ts")
    close = pd.to_numeric(subset.get("adjusted_close", subset.get("close")), errors="coerce").dropna()
    if len(close) <= 20:
        return None
    return float(close.iloc[-1] / close.iloc[-21] - 1.0)


def compute_positioning_metrics(frame: pd.DataFrame, *, price_history: pd.DataFrame | None = None) -> pd.DataFrame:
    """Calculate CFTC levels, changes, percentiles, reversal, and risk flags."""

    if frame.empty:
        return frame.copy()
    working = frame.copy()
    for column in ["report_date", "publication_date", "ingested_ts"]:
        working[column] = pd.to_datetime(working[column], utc=True, errors="coerce")
    working = working.sort_values(["internal_asset_id", "participant_category", "report_date"]).reset_index(drop=True)
    output: list[pd.DataFrame] = []
    for (asset_id, category), subset in working.groupby(["internal_asset_id", "participant_category"], dropna=False, sort=False):
        subset = subset.copy().reset_index(drop=True)
        subset["gross_long"] = pd.to_numeric(subset["long_contracts"], errors="coerce")
        subset["gross_short"] = pd.to_numeric(subset["short_contracts"], errors="coerce")
        subset["net_position"] = subset["gross_long"] - subset["gross_short"]
        open_interest = pd.to_numeric(subset["open_interest"], errors="coerce").replace(0, np.nan)
        subset["net_pct_open_interest"] = subset["net_position"] / open_interest
        subset["one_week_net_change"] = subset["net_position"].diff(1)
        subset["four_week_net_change"] = subset["net_position"].diff(4)
        subset["open_interest_change"] = open_interest.diff(1)
        subset["rolling_zscore"] = _rolling_zscore(subset["net_pct_open_interest"])
        subset["historical_percentile_52w"] = _rolling_percentile(subset["net_pct_open_interest"], 52, 20)
        subset["historical_percentile_3y"] = _rolling_percentile(subset["net_pct_open_interest"], 156, 52)
        prior_four_week = subset["net_position"].shift(4)
        subset["positioning_reversal"] = ((subset["net_position"] * prior_four_week) < 0).fillna(False)
        trend = _price_trend(price_history, str(asset_id))
        subset["price_trend_20d"] = trend
        history_counts = subset["net_pct_open_interest"].notna().cumsum()
        subset["crowding_condition"] = [
            classify_positioning_bucket(net, percentile, zscore, int(count))
            for net, percentile, zscore, count in zip(
                subset["net_pct_open_interest"],
                subset["historical_percentile_52w"],
                subset["rolling_zscore"],
                history_counts,
                strict=False,
            )
        ]
        risks = [
            classify_positioning_risk(net, trend, percentile)
            for net, percentile in zip(subset["net_pct_open_interest"], subset["historical_percentile_52w"], strict=False)
        ]
        subset["price_positioning_divergence"] = [risk["positioning_price_divergence"] for risk in risks]
        subset["long_liquidation_risk"] = [risk["long_liquidation_risk"] for risk in risks]
        subset["short_squeeze_risk"] = [risk["short_squeeze_risk"] for risk in risks]
        subset["confidence"] = ["high" if count >= 156 else "medium" if count >= 52 else "low" if count >= 20 else "insufficient" for count in history_counts]
        subset["calculation_ts"] = pd.Timestamp.now(tz="UTC")
        subset["internal_asset_id"] = asset_id
        subset["participant_category"] = category
        output.append(subset)
    return pd.concat(output, ignore_index=True)


def build_positioning_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Return latest positioning analytics per mapped contract/category."""

    if frame.empty:
        return frame.copy()
    metrics = frame.copy() if "net_position" in frame.columns else compute_positioning_metrics(frame)
    return metrics.sort_values("report_date").groupby(["internal_asset_id", "participant_category"], sort=False).tail(1).reset_index(drop=True)
