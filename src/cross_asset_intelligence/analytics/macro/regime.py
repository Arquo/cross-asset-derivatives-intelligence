"""Macro regime classifications."""

from __future__ import annotations

import pandas as pd


def classify_inflation_regime(cpi_yoy: float | None, cpi_3m_annualized: float | None) -> str:
    if cpi_yoy is None or cpi_3m_annualized is None or pd.isna(cpi_yoy) or pd.isna(cpi_3m_annualized):
        return "Insufficient data"
    delta = cpi_3m_annualized - cpi_yoy
    if delta >= 0.25:
        return "Accelerating"
    if delta <= -0.25:
        return "Decelerating"
    if abs(delta) < 0.1:
        return "Stable"
    return "Mixed"


def classify_labour_regime(unemployment_change_3m: float | None, initial_claims_trend: float | None = None) -> str:
    if unemployment_change_3m is None or pd.isna(unemployment_change_3m):
        return "Insufficient data"
    if initial_claims_trend is not None and not pd.isna(initial_claims_trend):
        if unemployment_change_3m < 0 and initial_claims_trend < 0:
            return "Strengthening"
        if unemployment_change_3m > 0 and initial_claims_trend > 0:
            return "Weakening"
        if abs(unemployment_change_3m) < 0.1 and abs(initial_claims_trend) < 0.1:
            return "Stable"
        return "Mixed"
    if unemployment_change_3m <= -0.2:
        return "Strengthening"
    if unemployment_change_3m >= 0.2:
        return "Weakening"
    return "Stable"


def classify_policy_regime(ffr_change_3m: float | None) -> str:
    if ffr_change_3m is None or pd.isna(ffr_change_3m):
        return "Insufficient data"
    if ffr_change_3m >= 0.25:
        return "Tightening"
    if ffr_change_3m <= -0.25:
        return "Easing"
    return "Stable"


def classify_yield_curve_regime(slope: float | None, slope_change: float | None = None) -> str:
    if slope is None or pd.isna(slope):
        return "Insufficient data"
    if slope_change is None or pd.isna(slope_change):
        if slope <= -0.05:
            return "Inverted"
        if abs(slope) <= 0.15:
            return "Flat"
        return "Normal"
    if abs(slope) <= 0.15 and abs(slope_change) <= 0.05:
        return "Flat"
    if slope > 0.5 and slope_change > 0.05:
        return "Steepening"
    if slope > 0.5 and slope_change < -0.05:
        return "Bear flattening"
    if slope < -0.05 and slope_change > 0.05:
        return "Bull steepening"
    if slope < -0.05 and slope_change < -0.05:
        return "Bear steepening"
    if slope <= -0.05:
        return "Inverted"
    return "Normal"


def classify_credit_regime(high_yield_spread_change: float | None, high_yield_spread_level: float | None = None) -> str:
    if high_yield_spread_change is None or pd.isna(high_yield_spread_change):
        return "Insufficient data"
    if high_yield_spread_level is not None and not pd.isna(high_yield_spread_level):
        if high_yield_spread_level >= 5.0 or high_yield_spread_change >= 0.5:
            return "Stressed"
    if high_yield_spread_change >= 0.25:
        return "Deteriorating"
    if high_yield_spread_change <= -0.25:
        return "Improving"
    return "Stable"


def classify_liquidity_regime(liquidity_score: float | None, confidence: float | None = None) -> str:
    if liquidity_score is None or pd.isna(liquidity_score):
        return "Insufficient data"
    if confidence is not None and confidence < 0.5:
        return "Mixed"
    if liquidity_score >= 0.2:
        return "Expanding"
    if liquidity_score <= -0.2:
        return "Contracting"
    return "Stable"


def classify_overall_macro_regime(
    inflation_regime: str,
    labour_regime: str,
    policy_regime: str,
    yield_curve_regime: str,
    credit_regime: str | None = None,
    liquidity_regime: str | None = None,
) -> str:
    regimes = {inflation_regime, labour_regime, policy_regime, yield_curve_regime}
    if credit_regime is not None:
        regimes.add(credit_regime)
    if liquidity_regime is not None:
        regimes.add(liquidity_regime)
    if "Insufficient data" in regimes:
        return "Insufficient data"
    if liquidity_regime in {"Expanding"} and policy_regime in {"Stable", "Easing"} and labour_regime in {"Strengthening", "Stable"}:
        return "Liquidity-driven risk-on"
    if liquidity_regime in {"Contracting"} and credit_regime in {"Deteriorating", "Stressed"}:
        return "Liquidity contraction"
    if inflation_regime == "Stable" and labour_regime == "Strengthening" and policy_regime == "Stable" and yield_curve_regime in {"Normal", "Steepening"}:
        return "Goldilocks"
    if inflation_regime in {"Accelerating", "Mixed"} and policy_regime in {"Tightening", "Stable"} and yield_curve_regime in {"Normal", "Steepening"}:
        return "Reflation"
    if inflation_regime in {"Decelerating", "Stable"} and labour_regime in {"Weakening", "Mixed"} and policy_regime in {"Easing", "Stable"}:
        return "Disinflationary slowdown"
    if inflation_regime == "Accelerating" and labour_regime in {"Weakening", "Mixed"} and credit_regime in {"Deteriorating", "Stressed"}:
        return "Stagflation risk"
    if labour_regime in {"Weakening"} and credit_regime in {"Deteriorating", "Stressed"}:
        return "Recessionary"
    return "Mixed / transitioning"

