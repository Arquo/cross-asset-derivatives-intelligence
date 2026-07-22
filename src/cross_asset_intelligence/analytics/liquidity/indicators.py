"""Liquidity and market-structure proxy calculations from daily bars."""

from __future__ import annotations

from collections.abc import Mapping
import json

import numpy as np
import pandas as pd

from cross_asset_intelligence.analytics.screener.metrics import build_market_features, classify_freshness

from .classification import classify_liquidity_regime


LIQUIDITY_WEIGHTS = {
    "amihud_illiquidity": 0.25,
    "realized_volatility": 0.20,
    "intraday_range": 0.15,
    "inverse_relative_dollar_volume": 0.15,
    "hyg_stress": 0.15,
    "vix_stress": 0.10,
}


def calculate_liquidity_stress(
    components: Mapping[str, float | None],
    *,
    weights: Mapping[str, float] = LIQUIDITY_WEIGHTS,
) -> dict[str, object]:
    """Return a 0-100 stress score with transparent weight redistribution."""

    available = {
        name: float(value)
        for name, value in components.items()
        if name in weights and value is not None and pd.notna(value)
    }
    missing = [name for name in weights if name not in available]
    available_weight = sum(weights[name] for name in available)
    if available_weight < 0.50:
        return {
            "score": None,
            "confidence": "insufficient",
            "contributions": [],
            "missing_components": missing,
            "available_weight": available_weight,
        }
    contributions = []
    score = 0.0
    for name, raw_value in available.items():
        bounded = max(0.0, min(1.0, raw_value))
        effective_weight = weights[name] / available_weight
        contribution = bounded * effective_weight * 100.0
        score += contribution
        contributions.append(
            {
                "component": name,
                "raw_value": bounded,
                "base_weight": weights[name],
                "effective_weight": effective_weight,
                "contribution": contribution,
            }
        )
    confidence = "high" if available_weight >= 0.85 else "medium" if available_weight >= 0.70 else "low"
    return {
        "score": max(0.0, min(100.0, score)),
        "confidence": confidence,
        "contributions": contributions,
        "missing_components": missing,
        "available_weight": available_weight,
    }


def _rolling_percentile(series: pd.Series, minimum: int = 20, window: int = 252) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")

    def rank_latest(values: np.ndarray) -> float:
        clean = values[~np.isnan(values)]
        if clean.size == 0 or np.isnan(values[-1]):
            return np.nan
        return float((clean <= values[-1]).sum() / clean.size)

    return numeric.rolling(window, min_periods=minimum).apply(rank_latest, raw=True)


def build_liquidity_components(market_history: pd.DataFrame, macro_history: pd.DataFrame | None = None) -> pd.DataFrame:
    """Build full daily proxy history; macro input is retained for API compatibility."""

    features = build_market_features(market_history)
    if features.empty:
        return features

    hyg = features[features["symbol"] == "HYG"].copy()
    hyg["hyg_stress"] = ((-hyg["return_20d"] * 3.0) + (-hyg["drawdown"])).clip(0.0, 1.0)
    hyg_map = hyg.set_index("observation_ts")["hyg_stress"].to_dict()

    vix = features[features["symbol"] == "VIX"].copy()
    vix["vix_stress"] = _rolling_percentile(vix["price"])
    vix_map = vix.set_index("observation_ts")["vix_stress"].to_dict()

    features["hyg_stress"] = features["observation_ts"].map(hyg_map)
    features["vix_stress"] = features["observation_ts"].map(vix_map)
    return features


def build_liquidity_analytics(
    market_history: pd.DataFrame,
    *,
    analytics_run_id: str = "",
    reference_time: object | None = None,
) -> pd.DataFrame:
    """Calculate and prepare persistable liquidity analytics history."""

    components = build_liquidity_components(market_history)
    if components.empty:
        return pd.DataFrame()
    calculation_ts = pd.Timestamp.now(tz="UTC")
    rows: list[dict[str, object]] = []
    for _, row in components.iterrows():
        relative_dollar = row.get("relative_dollar_volume_20d")
        inverse_relative = None if pd.isna(relative_dollar) else float(np.clip(1.0 - relative_dollar, 0.0, 1.0))
        result = calculate_liquidity_stress(
            {
                "amihud_illiquidity": row.get("amihud_percentile"),
                "realized_volatility": row.get("realized_vol_percentile"),
                "intraday_range": row.get("intraday_range_percentile"),
                "inverse_relative_dollar_volume": inverse_relative,
                "hyg_stress": row.get("hyg_stress"),
                "vix_stress": row.get("vix_stress"),
            }
        )
        rows.append(
            {
                "analytics_run_id": analytics_run_id,
                "symbol": row["symbol"],
                "observation_ts": row["observation_ts"],
                "calculation_ts": calculation_ts,
                "dollar_volume": row.get("dollar_volume"),
                "average_dollar_volume_20d": row.get("average_dollar_volume_20d"),
                "relative_dollar_volume_20d": relative_dollar,
                "relative_volume_20d": row.get("relative_volume_20d"),
                "realized_volatility_20d": row.get("realized_vol_20d"),
                "intraday_range_pct": row.get("intraday_range_pct"),
                "average_true_range_14d": row.get("average_true_range_14d"),
                "amihud_illiquidity_20d": row.get("amihud_illiquidity_20d"),
                "amihud_percentile": row.get("amihud_percentile"),
                "volume_shock_zscore": row.get("volume_shock_zscore"),
                "price_impact_proxy": row.get("price_impact_proxy"),
                "drawdown": row.get("drawdown"),
                "hyg_stress": row.get("hyg_stress"),
                "vix_stress": row.get("vix_stress"),
                "liquidity_stress_score": result["score"],
                "stress_historical_percentile": pd.NA,
                "liquidity_regime": classify_liquidity_regime(result["score"], confidence=result["confidence"]),
                "confidence": result["confidence"],
                "component_contributions": json.dumps(result["contributions"], sort_keys=True),
                "missing_components": json.dumps(result["missing_components"]),
                "freshness_status": classify_freshness(row["observation_ts"], reference_time),
                "source_label": "Daily OHLCV bar-data proxies; yfinance/Yahoo Finance",
            }
        )
    output = pd.DataFrame(rows)
    output["stress_historical_percentile"] = output.groupby("symbol", sort=False)["liquidity_stress_score"].transform(_rolling_percentile)
    return output


def build_liquidity_summary(market_history: pd.DataFrame, macro_history: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return the latest proxy row for each stored market asset."""

    analytics = build_liquidity_analytics(market_history)
    if analytics.empty:
        return analytics
    return analytics.sort_values("observation_ts").groupby("symbol", sort=False).tail(1).reset_index(drop=True)
