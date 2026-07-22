"""Pure filtering and predefined sorting for the screener UI."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd


VIEW_SORTS: Mapping[str, tuple[str, bool]] = {
    "Strongest momentum": ("return_20d", False),
    "Weakest momentum": ("return_20d", True),
    "Highest volatility": ("realized_vol_20d", False),
    "Largest volume surprise": ("relative_volume_20d", False),
    "Deteriorating liquidity": ("amihud_percentile", False),
    "Crowded longs": ("market_pressure_score", False),
    "Crowded shorts": ("market_pressure_score", True),
    "Largest bullish divergences": ("market_pressure_score", False),
    "Largest bearish divergences": ("market_pressure_score", True),
}


def apply_screener_filters(frame: pd.DataFrame, filters: Mapping[str, list[str] | str | None]) -> pd.DataFrame:
    filtered = frame.copy()
    for column, selected in filters.items():
        if column not in filtered.columns or selected is None or selected == [] or selected == "All":
            continue
        values = selected if isinstance(selected, list) else [selected]
        filtered = filtered[filtered[column].isin(values)]
    return filtered.reset_index(drop=True)


def apply_screener_view(frame: pd.DataFrame, view_name: str) -> pd.DataFrame:
    if frame.empty or view_name not in VIEW_SORTS:
        return frame.copy()
    column, ascending = VIEW_SORTS[view_name]
    filtered = frame.copy()
    if view_name == "Crowded longs":
        filtered = filtered[filtered["positioning_classification"].isin(["Crowded long", "Extremely long"])]
    elif view_name == "Crowded shorts":
        filtered = filtered[filtered["positioning_classification"].isin(["Crowded short", "Extremely short"])]
    elif view_name == "Largest bullish divergences":
        filtered = filtered[(filtered["return_20d"] < 0) & (filtered["market_pressure_score"] > 0)]
    elif view_name == "Largest bearish divergences":
        filtered = filtered[(filtered["return_20d"] > 0) & (filtered["market_pressure_score"] < 0)]
    return filtered.sort_values(column, ascending=ascending, na_position="last").reset_index(drop=True)
