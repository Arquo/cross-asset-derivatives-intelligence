"""Daily-bar metrics and the cross-asset screener table."""

from __future__ import annotations

from collections.abc import Mapping
import json

import numpy as np
import pandas as pd

from .score import calculate_market_pressure_score


SOURCE_LABEL = "yfinance/Yahoo Finance (research-grade, replaceable)"


def daily_return(prices: pd.Series, periods: int = 1) -> pd.Series:
    return pd.to_numeric(prices, errors="coerce").pct_change(periods)


def moving_average_distance(prices: pd.Series, window: int) -> pd.Series:
    numeric = pd.to_numeric(prices, errors="coerce")
    average = numeric.rolling(window, min_periods=window).mean()
    return numeric / average - 1.0


def realized_volatility(returns: pd.Series, window: int = 20) -> pd.Series:
    return pd.to_numeric(returns, errors="coerce").rolling(window, min_periods=window).std(ddof=0) * np.sqrt(252)


def relative_volume(volume: pd.Series, window: int = 20) -> pd.Series:
    numeric = pd.to_numeric(volume, errors="coerce")
    return numeric / numeric.rolling(window, min_periods=window).mean().replace(0, np.nan)


def dollar_volume(close: pd.Series, volume: pd.Series) -> pd.Series:
    return pd.to_numeric(close, errors="coerce") * pd.to_numeric(volume, errors="coerce")


def intraday_range_pct(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    denominator = pd.to_numeric(close, errors="coerce").replace(0, np.nan)
    return (pd.to_numeric(high, errors="coerce") - pd.to_numeric(low, errors="coerce")) / denominator


def average_true_range(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    high_values = pd.to_numeric(high, errors="coerce")
    low_values = pd.to_numeric(low, errors="coerce")
    close_values = pd.to_numeric(close, errors="coerce")
    previous_close = close_values.shift(1)
    true_range = pd.concat(
        [high_values - low_values, (high_values - previous_close).abs(), (low_values - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window, min_periods=window).mean()


def amihud_illiquidity(returns: pd.Series, dollar_values: pd.Series, window: int = 20) -> pd.Series:
    ratio = pd.to_numeric(returns, errors="coerce").abs() / pd.to_numeric(dollar_values, errors="coerce").replace(0, np.nan)
    return ratio.rolling(window, min_periods=window).mean()


def _rolling_percentile(series: pd.Series, window: int = 252, minimum: int = 20) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")

    def rank_latest(values: np.ndarray) -> float:
        clean = values[~np.isnan(values)]
        if clean.size == 0 or np.isnan(values[-1]):
            return np.nan
        return float((clean <= values[-1]).sum() / clean.size)

    return numeric.rolling(window, min_periods=minimum).apply(rank_latest, raw=True)


def classify_freshness(observation_ts: object, reference_time: object | None = None) -> str:
    observation = pd.to_datetime(observation_ts, utc=True, errors="coerce")
    reference = pd.to_datetime(reference_time, utc=True, errors="coerce") if reference_time is not None else pd.Timestamp.now(tz="UTC")
    if pd.isna(observation) or pd.isna(reference):
        return "Missing"
    age_days = (reference.normalize() - observation.normalize()).days
    if age_days <= 3:
        return "Current"
    if age_days <= 7:
        return "Delayed as expected"
    return "Stale"


def _classify_trend(row: pd.Series) -> str:
    if pd.isna(row.get("return_20d")) or pd.isna(row.get("distance_ma_60d")):
        return "Insufficient data"
    if row["return_20d"] >= 0.05 and row["distance_ma_60d"] > 0:
        return "Strong uptrend"
    if row["return_20d"] > 0 and row["distance_ma_20d"] > 0:
        return "Uptrend"
    if row["return_20d"] <= -0.05 and row["distance_ma_60d"] < 0:
        return "Strong downtrend"
    if row["return_20d"] < 0 and row["distance_ma_20d"] < 0:
        return "Downtrend"
    return "Range-bound"


def _classify_volatility(percentile: object) -> str:
    if percentile is None or pd.isna(percentile):
        return "Insufficient data"
    if percentile >= 0.85:
        return "High"
    if percentile <= 0.20:
        return "Low"
    return "Normal"


def _classify_liquidity(row: pd.Series) -> str:
    percentile = row.get("amihud_percentile")
    relative_dollar = row.get("relative_dollar_volume_20d")
    if pd.isna(percentile) or pd.isna(relative_dollar):
        return "Insufficient data"
    if percentile >= 0.80 or relative_dollar < 0.65:
        return "Deteriorating"
    if percentile <= 0.25 and relative_dollar >= 1.0:
        return "Abundant"
    return "Normal"


def build_market_features(market_history: pd.DataFrame) -> pd.DataFrame:
    """Calculate all daily features used by screener and liquidity modules."""

    if market_history.empty:
        return pd.DataFrame()
    working = market_history.copy()
    working["observation_ts"] = pd.to_datetime(working["observation_ts"], utc=True, errors="coerce")
    working = working.dropna(subset=["symbol", "observation_ts"]).sort_values(["symbol", "observation_ts"]).reset_index(drop=True)
    working["price"] = pd.to_numeric(working.get("adjusted_close"), errors="coerce").fillna(pd.to_numeric(working.get("close"), errors="coerce"))
    output: list[pd.DataFrame] = []
    for _, subset in working.groupby("symbol", sort=False):
        subset = subset.copy().reset_index(drop=True)
        subset["return_1d"] = daily_return(subset["price"], 1)
        for periods in [5, 20, 60]:
            subset[f"return_{periods}d"] = daily_return(subset["price"], periods)
        subset["distance_ma_20d"] = moving_average_distance(subset["price"], 20)
        subset["distance_ma_60d"] = moving_average_distance(subset["price"], 60)
        subset["realized_vol_20d"] = realized_volatility(subset["return_1d"], 20)
        subset["relative_volume_20d"] = relative_volume(subset["volume"], 20)
        subset["dollar_volume"] = dollar_volume(subset["close"], subset["volume"])
        subset["average_dollar_volume_20d"] = subset["dollar_volume"].rolling(20, min_periods=20).mean()
        subset["relative_dollar_volume_20d"] = subset["dollar_volume"] / subset["average_dollar_volume_20d"].replace(0, np.nan)
        subset["intraday_range_pct"] = intraday_range_pct(subset["high"], subset["low"], subset["close"])
        subset["average_true_range_14d"] = average_true_range(subset["high"], subset["low"], subset["close"], 14)
        subset["amihud_illiquidity_20d"] = amihud_illiquidity(subset["return_1d"], subset["dollar_volume"], 20)
        subset["amihud_percentile"] = _rolling_percentile(subset["amihud_illiquidity_20d"])
        subset["realized_vol_percentile"] = _rolling_percentile(subset["realized_vol_20d"])
        subset["intraday_range_percentile"] = _rolling_percentile(subset["intraday_range_pct"])
        volume_mean = pd.to_numeric(subset["volume"], errors="coerce").rolling(20, min_periods=20).mean()
        volume_std = pd.to_numeric(subset["volume"], errors="coerce").rolling(20, min_periods=20).std(ddof=0)
        subset["volume_shock_zscore"] = (pd.to_numeric(subset["volume"], errors="coerce") - volume_mean) / volume_std.replace(0, np.nan)
        subset["price_impact_proxy"] = subset["return_1d"].abs() / subset["relative_dollar_volume_20d"].replace(0, np.nan)
        subset["drawdown"] = subset["price"] / subset["price"].cummax() - 1.0
        output.append(subset)
    return pd.concat(output, ignore_index=True)


def _component_scores(row: pd.Series, positioning_score: float | None) -> dict[str, float | None]:
    trend_inputs = [row.get("return_20d"), row.get("distance_ma_20d"), row.get("distance_ma_60d")]
    trend = None if any(pd.isna(value) for value in trend_inputs) else float(np.clip((trend_inputs[0] * 700) + (trend_inputs[1] * 200) + (trend_inputs[2] * 100), -100, 100))
    relative_volume_value = row.get("relative_volume_20d")
    one_day_return = row.get("return_1d")
    volume = None if pd.isna(relative_volume_value) or pd.isna(one_day_return) else float(np.clip((relative_volume_value - 1.0) * 60 * np.sign(one_day_return), -100, 100))
    vol_percentile = row.get("realized_vol_percentile")
    volatility = None if pd.isna(vol_percentile) else float((0.5 - vol_percentile) * 200)
    amihud_percentile = row.get("amihud_percentile")
    relative_dollar = row.get("relative_dollar_volume_20d")
    liquidity = None if pd.isna(amihud_percentile) or pd.isna(relative_dollar) else float(np.clip((0.5 - amihud_percentile) * 140 + (relative_dollar - 1) * 30, -100, 100))
    return {
        "trend_momentum": trend,
        "volume_confirmation": volume,
        "volatility_condition": volatility,
        "liquidity_condition": liquidity,
        "positioning_condition": positioning_score,
    }


def build_screener(
    market_history: pd.DataFrame,
    *,
    asset_classes: Mapping[str, str],
    positioning: Mapping[str, Mapping[str, object]] | None = None,
    options: Mapping[str, Mapping[str, object]] | None = None,
    reference_time: object | None = None,
    analytics_run_id: str = "",
) -> pd.DataFrame:
    """Return one populated screener row per asset."""

    features = build_market_features(market_history)
    if features.empty:
        return pd.DataFrame()
    calculation_ts = pd.Timestamp.now(tz="UTC")
    latest = features.groupby("symbol", sort=False).tail(1).copy()
    rows: list[dict[str, object]] = []
    for _, row in latest.iterrows():
        symbol = str(row["symbol"])
        positioning_item = (positioning or {}).get(symbol, {})
        options_item = (options or {}).get(symbol, {})
        score_result = calculate_market_pressure_score(_component_scores(row, positioning_item.get("score")))
        rows.append(
            {
                "analytics_run_id": analytics_run_id,
                "symbol": symbol,
                "asset_class": asset_classes.get(symbol, "other"),
                "observation_ts": row["observation_ts"],
                "calculation_ts": calculation_ts,
                "latest_close": row.get("price"),
                "return_1d": row.get("return_1d"),
                "return_5d": row.get("return_5d"),
                "return_20d": row.get("return_20d"),
                "return_60d": row.get("return_60d"),
                "distance_ma_20d": row.get("distance_ma_20d"),
                "distance_ma_60d": row.get("distance_ma_60d"),
                "realized_vol_20d": row.get("realized_vol_20d"),
                "relative_volume_20d": row.get("relative_volume_20d"),
                "dollar_volume": row.get("dollar_volume"),
                "amihud_percentile": row.get("amihud_percentile"),
                "trend_classification": _classify_trend(row),
                "volatility_classification": _classify_volatility(row.get("realized_vol_percentile")),
                "liquidity_classification": _classify_liquidity(row),
                "positioning_classification": positioning_item.get("classification", "Unavailable"),
                "options_classification": options_item.get("classification", "Unavailable"),
                "market_pressure_score": score_result.score,
                "pressure_label": score_result.label,
                "pressure_confidence": score_result.confidence,
                "score_components": json.dumps(score_result.components, sort_keys=True),
                "missing_components": json.dumps(score_result.missing_components),
                "freshness_status": classify_freshness(row["observation_ts"], reference_time),
                "source_label": SOURCE_LABEL,
            }
        )
    return pd.DataFrame(rows)
