"""Rule-based CFTC positioning classifications and risk flags."""

from __future__ import annotations

import pandas as pd


def classify_positioning_bucket(
    net_pct_open_interest: float | None,
    percentile: float | None,
    zscore: float | None = None,
    history_count: int | None = None,
) -> str:
    """Classify level and crowding from net exposure and its own history."""

    if net_pct_open_interest is None or pd.isna(net_pct_open_interest):
        return "Insufficient history"
    if history_count is not None and history_count < 20:
        return "Insufficient history"
    if percentile is not None and pd.notna(percentile):
        if percentile >= 0.90 and (zscore is None or pd.isna(zscore) or zscore >= 1.0 or net_pct_open_interest >= 0.60):
            return "Crowded long"
        if percentile <= 0.10 and (zscore is None or pd.isna(zscore) or zscore <= -1.0 or net_pct_open_interest <= -0.60):
            return "Crowded short"
        if percentile >= 0.95:
            return "Extremely long"
        if percentile >= 0.70:
            return "Moderately long"
        if percentile <= 0.05:
            return "Extremely short"
        if percentile <= 0.30:
            return "Moderately short"
        return "Neutral"
    if net_pct_open_interest >= 0.75:
        return "Extremely long"
    if net_pct_open_interest >= 0.25:
        return "Moderately long"
    if net_pct_open_interest <= -0.75:
        return "Extremely short"
    if net_pct_open_interest <= -0.25:
        return "Moderately short"
    return "Neutral"


def classify_positioning_risk(
    net_pct_open_interest: float | None,
    price_trend: float | None,
    percentile: float | None = None,
) -> dict[str, bool]:
    """Return descriptive crowding risks; these are not predictions."""

    if net_pct_open_interest is None or pd.isna(net_pct_open_interest):
        return {"long_liquidation_risk": False, "short_squeeze_risk": False, "positioning_price_divergence": False}
    crowded_long = (percentile is not None and pd.notna(percentile) and percentile >= 0.90) or net_pct_open_interest >= 0.60
    crowded_short = (percentile is not None and pd.notna(percentile) and percentile <= 0.10) or net_pct_open_interest <= -0.60
    valid_trend = price_trend is not None and pd.notna(price_trend)
    long_liquidation_risk = bool(crowded_long and valid_trend and price_trend < 0)
    short_squeeze_risk = bool(crowded_short and valid_trend and price_trend > 0)
    divergence = bool(valid_trend and ((net_pct_open_interest > 0 and price_trend < 0) or (net_pct_open_interest < 0 and price_trend > 0)))
    return {
        "long_liquidation_risk": long_liquidation_risk,
        "short_squeeze_risk": short_squeeze_risk,
        "positioning_price_divergence": divergence,
    }
