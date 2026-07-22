"""Reusable calculation utilities for deterministic analytics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SeriesWindowResult:
    """Convenience wrapper for windowed calculations."""

    latest: float | None
    prior: float | None
    value: float | None


def clean_observations(frame: pd.DataFrame, *, date_column: str = "date", value_column: str = "value") -> pd.DataFrame:
    """Convert placeholder missing values, parse dates, and sort chronologically."""

    if frame.empty:
        return frame.copy()
    working = frame.copy()
    if value_column in working.columns:
        working[value_column] = working[value_column].replace(".", pd.NA)
        working[value_column] = pd.to_numeric(working[value_column], errors="coerce")
    if date_column in working.columns:
        working[date_column] = pd.to_datetime(working[date_column], utc=True, errors="coerce")
    working = working.dropna(subset=[date_column]).sort_values(date_column).drop_duplicates(subset=[date_column], keep="last").reset_index(drop=True)
    return working


def ensure_datetime_column(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """Return a copy with the selected column normalized to UTC timestamps."""

    working = frame.copy()
    if column in working.columns:
        working[column] = pd.to_datetime(working[column], utc=True, errors="coerce")
    return working


def safe_divide(numerator: float | int | None, denominator: float | int | None) -> float | None:
    """Safely divide two values without raising division-by-zero errors."""

    if numerator is None or denominator is None:
        return None
    if pd.isna(numerator) or pd.isna(denominator) or denominator == 0:
        return None
    return float(numerator) / float(denominator)


def latest_valid_value(series: pd.Series) -> float | None:
    cleaned = pd.to_numeric(series, errors="coerce").dropna()
    if cleaned.empty:
        return None
    return float(cleaned.iloc[-1])


def _window_series(series: pd.Series, periods: int) -> SeriesWindowResult:
    cleaned = pd.to_numeric(series, errors="coerce").dropna()
    if cleaned.empty or len(cleaned) <= periods:
        return SeriesWindowResult(None, None, None)
    latest = float(cleaned.iloc[-1])
    prior = float(cleaned.iloc[-1 - periods])
    return SeriesWindowResult(latest=latest, prior=prior, value=latest - prior)


def absolute_change(series: pd.Series, periods: int) -> float | None:
    """Calculate the absolute change over an explicit lookback."""

    return _window_series(series, periods).value


def percentage_change(series: pd.Series, periods: int) -> float | None:
    """Calculate percentage change over an explicit lookback."""

    window = _window_series(series, periods)
    return safe_divide(window.latest - window.prior if window.latest is not None and window.prior is not None else None, window.prior)


def rolling_mean(series: pd.Series, window: int) -> pd.Series:
    """Rolling mean with a minimum of one valid observation only when the full window exists."""

    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.rolling(window=window, min_periods=window).mean()


def rolling_std(series: pd.Series, window: int) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.rolling(window=window, min_periods=window).std(ddof=0)


def rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    """Rolling z-score with stable missing-data behavior."""

    numeric = pd.to_numeric(series, errors="coerce")
    mean = numeric.rolling(window=window, min_periods=window).mean()
    std = numeric.rolling(window=window, min_periods=window).std(ddof=0)
    zscore = (numeric - mean) / std.replace({0: pd.NA})
    return zscore.replace([np.inf, -np.inf], pd.NA)


def historical_percentile(series: pd.Series, window: int) -> pd.Series:
    """Historical percentile rank for the latest value in each rolling window."""

    numeric = pd.to_numeric(series, errors="coerce")

    def _percentile(values: np.ndarray) -> float:
        latest = values[-1]
        values = values[~np.isnan(values)]
        if len(values) == 0 or np.isnan(latest):
            return np.nan
        return float((values <= latest).sum() / len(values))

    return numeric.rolling(window=window, min_periods=window).apply(_percentile, raw=True)


def annualized_realized_volatility(returns: pd.Series, window: int, periods_per_year: int = 252) -> pd.Series:
    """Annualized realized volatility from periodic returns."""

    numeric = pd.to_numeric(returns, errors="coerce")
    return numeric.rolling(window=window, min_periods=window).std(ddof=0) * np.sqrt(periods_per_year)


def rolling_correlation(series_a: pd.Series, series_b: pd.Series, window: int) -> pd.Series:
    """Rolling correlation with explicit alignment."""

    a = pd.to_numeric(series_a, errors="coerce")
    b = pd.to_numeric(series_b, errors="coerce")
    return a.rolling(window=window, min_periods=window).corr(b)


def rolling_beta(series_y: pd.Series, series_x: pd.Series, window: int) -> pd.Series:
    """Rolling beta of y on x."""

    y = pd.to_numeric(series_y, errors="coerce")
    x = pd.to_numeric(series_x, errors="coerce")
    cov = y.rolling(window=window, min_periods=window).cov(x)
    var = x.rolling(window=window, min_periods=window).var(ddof=0)
    beta = cov / var.replace({0: pd.NA})
    return beta.replace([np.inf, -np.inf], pd.NA)


def trend_direction(series: pd.Series, window: int = 5) -> str:
    """Classify the direction of a short rolling trend."""

    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if len(numeric) < window:
        return "insufficient"
    recent = numeric.iloc[-window:]
    x = np.arange(len(recent), dtype=float)
    slope = np.polyfit(x, recent.to_numpy(dtype=float), 1)[0]
    if slope > 0:
        return "up"
    if slope < 0:
        return "down"
    return "flat"


def minimum_observations_ok(series: pd.Series, minimum: int) -> bool:
    """Check whether enough non-missing observations exist."""

    return pd.to_numeric(series, errors="coerce").dropna().shape[0] >= int(minimum)


def normalize_score(value: float | None, *, lower: float | None, upper: float | None, invert: bool = False) -> float | None:
    """Map a raw value to a bounded score in [-1, 1]."""

    if value is None or pd.isna(value):
        return None
    if lower is None or upper is None or lower == upper:
        return float(max(min(value, 1.0), -1.0)) if invert else float(max(min(value, 1.0), -1.0))
    center = (upper + lower) / 2.0
    half_range = abs(upper - lower) / 2.0
    if half_range == 0:
        return 0.0
    score = (float(value) - center) / half_range
    score = max(min(score, 1.0), -1.0)
    return -score if invert else score


def maximum_drawdown(prices: pd.Series) -> pd.Series:
    """Rolling maximum drawdown for a price series."""

    numeric = pd.to_numeric(prices, errors="coerce")
    rolling_max = numeric.cummax()
    drawdown = numeric / rolling_max - 1.0
    return drawdown


def amihud_illiquidity(returns: pd.Series, dollar_volume: pd.Series, window: int) -> pd.Series:
    """Amihud illiquidity proxy from absolute return divided by dollar volume."""

    ret = pd.to_numeric(returns, errors="coerce").abs()
    dollar = pd.to_numeric(dollar_volume, errors="coerce").replace({0: pd.NA})
    ratio = ret / dollar
    return ratio.rolling(window=window, min_periods=window).mean().replace([np.inf, -np.inf], pd.NA)

