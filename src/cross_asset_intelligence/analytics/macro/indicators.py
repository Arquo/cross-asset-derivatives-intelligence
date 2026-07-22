"""Macro indicator helpers."""

from __future__ import annotations

from analytics.macro_regime import (
    MacroRegimeResult,
    SeriesSnapshot,
    build_macro_regime_result,
    build_series_snapshot,
    calculate_change_over_period,
    calculate_cpi_three_month_annualized,
    calculate_cpi_yoy,
    calculate_yield_curve_slope,
    clean_observations,
    get_value_near_offset,
    latest_valid_observation,
)

__all__ = [
    "MacroRegimeResult",
    "SeriesSnapshot",
    "build_macro_regime_result",
    "build_series_snapshot",
    "calculate_change_over_period",
    "calculate_cpi_three_month_annualized",
    "calculate_cpi_yoy",
    "calculate_yield_curve_slope",
    "clean_observations",
    "get_value_near_offset",
    "latest_valid_observation",
]
