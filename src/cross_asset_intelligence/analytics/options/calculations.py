"""Transparent option-chain calculations without directional prediction."""

from __future__ import annotations

from collections.abc import Iterable
import json
from math import erf, exp, log, pi, sqrt

import numpy as np
import pandas as pd

from cross_asset_intelligence.analytics.screener.metrics import build_market_features


GAMMA_ASSUMPTIONS = {
    "calls_positive_puts_negative": {"call": 1.0, "put": -1.0},
    "all_long_gamma": {"call": 1.0, "put": 1.0},
    "calls_negative_puts_positive": {"call": -1.0, "put": 1.0},
}


def _number(value: object) -> float | None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(numeric) else float(numeric)


def mid_price(bid: object, ask: object, last_price: object | None = None) -> float | None:
    """Use a valid quoted midpoint, with last price as an explicit fallback."""

    bid_value, ask_value, last_value = _number(bid), _number(ask), _number(last_price)
    if bid_value is not None and ask_value is not None and bid_value >= 0 and ask_value > 0 and ask_value >= bid_value:
        return (bid_value + ask_value) / 2.0
    if last_value is not None and last_value > 0:
        return last_value
    return None


def put_call_ratio(put_value: object, call_value: object) -> float | None:
    put_numeric, call_numeric = _number(put_value), _number(call_value)
    if put_numeric is None or call_numeric is None or call_numeric <= 0:
        return None
    return put_numeric / call_numeric


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + erf(value / sqrt(2.0)))


def _normal_pdf(value: float) -> float:
    return exp(-0.5 * value * value) / sqrt(2.0 * pi)


def _d1(spot: float, strike: float, time_years: float, volatility: float, risk_free_rate: float, dividend_yield: float) -> float | None:
    if spot <= 0 or strike <= 0 or time_years <= 0 or volatility <= 0:
        return None
    return (log(spot / strike) + (risk_free_rate - dividend_yield + 0.5 * volatility**2) * time_years) / (volatility * sqrt(time_years))


def black_scholes_delta(
    spot: float,
    strike: float,
    time_years: float,
    volatility: float,
    option_type: str,
    risk_free_rate: float = 0.04,
    dividend_yield: float = 0.0,
) -> float | None:
    d1 = _d1(spot, strike, time_years, volatility, risk_free_rate, dividend_yield)
    if d1 is None:
        return None
    discount = exp(-dividend_yield * time_years)
    return discount * _normal_cdf(d1) if option_type.lower() == "call" else discount * (_normal_cdf(d1) - 1.0)


def black_scholes_gamma(
    spot: float,
    strike: float,
    time_years: float,
    volatility: float,
    risk_free_rate: float = 0.04,
    dividend_yield: float = 0.0,
) -> float | None:
    d1 = _d1(spot, strike, time_years, volatility, risk_free_rate, dividend_yield)
    if d1 is None:
        return None
    return exp(-dividend_yield * time_years) * _normal_pdf(d1) / (spot * volatility * sqrt(time_years))


def select_atm_contract(frame: pd.DataFrame, spot: float, option_type: str | None = None) -> pd.Series | None:
    working = frame.copy()
    if option_type is not None:
        working = working[working["option_type"].str.lower() == option_type.lower()]
    working["strike"] = pd.to_numeric(working["strike"], errors="coerce")
    working = working.dropna(subset=["strike"])
    if working.empty:
        return None
    return working.loc[(working["strike"] - spot).abs().idxmin()]


def select_25_delta_contract(
    frame: pd.DataFrame,
    *,
    spot: float,
    time_years: float,
    option_type: str,
    risk_free_rate: float = 0.04,
) -> pd.Series | None:
    working = frame[frame["option_type"].str.lower() == option_type.lower()].copy()
    if working.empty:
        return None
    working["calculated_delta"] = [
        black_scholes_delta(spot, float(strike), time_years, float(iv), option_type, risk_free_rate)
        if pd.notna(strike) and pd.notna(iv)
        else None
        for strike, iv in zip(working["strike"], working["implied_volatility"], strict=False)
    ]
    target = 0.25 if option_type.lower() == "call" else -0.25
    working["delta_difference"] = (pd.to_numeric(working["calculated_delta"], errors="coerce") - target).abs()
    working = working.dropna(subset=["delta_difference"])
    if working.empty:
        return None
    return working.loc[working["delta_difference"].idxmin()]


def expected_move_from_straddle(call_mid: float | None, put_mid: float | None) -> float | None:
    if call_mid is None or put_mid is None or call_mid < 0 or put_mid < 0:
        return None
    return float(call_mid + put_mid)


def expected_move_from_iv(spot: float, implied_volatility: float, time_years: float) -> float | None:
    if spot <= 0 or implied_volatility <= 0 or time_years <= 0:
        return None
    return float(spot * implied_volatility * sqrt(time_years))


def risk_reversal(put_implied_volatility: float | None, call_implied_volatility: float | None) -> float | None:
    if put_implied_volatility is None or call_implied_volatility is None:
        return None
    if pd.isna(put_implied_volatility) or pd.isna(call_implied_volatility):
        return None
    return float(call_implied_volatility - put_implied_volatility)


def open_interest_concentration(open_interest: pd.Series, top_n: int = 5) -> float | None:
    numeric = pd.to_numeric(open_interest, errors="coerce").clip(lower=0).dropna()
    total = numeric.sum()
    if numeric.empty or total <= 0:
        return None
    return float(numeric.nlargest(top_n).sum() / total)


def _time_years(expiration: object, quote_timestamp: object) -> float:
    expiration_ts = pd.Timestamp(expiration)
    expiration_ts = expiration_ts.tz_localize("UTC") if expiration_ts.tzinfo is None else expiration_ts.tz_convert("UTC")
    quote_ts = pd.Timestamp(quote_timestamp)
    quote_ts = quote_ts.tz_localize("UTC") if quote_ts.tzinfo is None else quote_ts.tz_convert("UTC")
    days = max((expiration_ts + pd.Timedelta(hours=21) - quote_ts).total_seconds() / 86400.0, 0.0)
    return days / 365.0


def gamma_exposure_by_strike(
    frame: pd.DataFrame,
    *,
    spot: float,
    time_years: float,
    assumption_set: str = "calls_positive_puts_negative",
) -> pd.DataFrame:
    signs = GAMMA_ASSUMPTIONS[assumption_set]
    working = frame.copy()
    working["gamma"] = [
        black_scholes_gamma(spot, float(strike), time_years, float(iv)) if pd.notna(strike) and pd.notna(iv) else None
        for strike, iv in zip(working["strike"], working["implied_volatility"], strict=False)
    ]
    oi = pd.to_numeric(working["open_interest"], errors="coerce")
    multiplier = (
        pd.to_numeric(working["contract_multiplier"], errors="coerce").fillna(100.0)
        if "contract_multiplier" in working.columns
        else pd.Series(100.0, index=working.index)
    )
    working["estimated_gamma_exposure"] = [
        gamma * open_interest * contract_multiplier * spot**2 * signs.get(str(option_type).lower(), 0.0)
        if gamma is not None and pd.notna(open_interest) and pd.notna(contract_multiplier)
        else np.nan
        for gamma, open_interest, contract_multiplier, option_type in zip(
            working["gamma"], oi, multiplier, working["option_type"], strict=False
        )
    ]
    return (
        working.groupby("strike", as_index=False)["estimated_gamma_exposure"]
        .sum(min_count=1)
        .sort_values("strike")
        .reset_index(drop=True)
    )


def gamma_assumption_sensitivity(frame: pd.DataFrame, *, spot: float, time_years: float) -> dict[str, float | None]:
    totals: dict[str, float | None] = {}
    for assumption in GAMMA_ASSUMPTIONS:
        by_strike = gamma_exposure_by_strike(frame, spot=spot, time_years=time_years, assumption_set=assumption)
        total = pd.to_numeric(by_strike["estimated_gamma_exposure"], errors="coerce").sum(min_count=1)
        totals[assumption] = None if pd.isna(total) else float(total)
    return totals


def gamma_flip_estimate(
    frame: pd.DataFrame,
    *,
    spot_scenarios: Iterable[float],
    time_years: float,
    assumption_set: str = "calls_positive_puts_negative",
) -> float | None:
    points: list[tuple[float, float]] = []
    for scenario in sorted(float(value) for value in spot_scenarios if value > 0):
        exposure = gamma_exposure_by_strike(frame, spot=scenario, time_years=time_years, assumption_set=assumption_set)
        total = pd.to_numeric(exposure["estimated_gamma_exposure"], errors="coerce").sum(min_count=1)
        if pd.notna(total):
            points.append((scenario, float(total)))
    for (left_spot, left_value), (right_spot, right_value) in zip(points, points[1:], strict=False):
        if left_value == 0:
            return left_spot
        if left_value * right_value < 0:
            fraction = abs(left_value) / (abs(left_value) + abs(right_value))
            return left_spot + fraction * (right_spot - left_spot)
    return None


def _bid_ask_quality(frame: pd.DataFrame) -> tuple[str, float]:
    bid = pd.to_numeric(frame["bid"], errors="coerce")
    ask = pd.to_numeric(frame["ask"], errors="coerce")
    valid = (bid >= 0) & (ask > 0) & (ask >= bid)
    coverage = float(valid.mean()) if len(frame) else 0.0
    if valid.any():
        midpoint = ((bid + ask) / 2.0).replace(0, np.nan)
        median_spread = float(((ask - bid) / midpoint)[valid].median())
    else:
        median_spread = np.nan
    label = "Good" if coverage >= 0.80 and pd.notna(median_spread) and median_spread <= 0.20 else "Mixed" if coverage >= 0.50 else "Poor"
    return label, coverage


def _condition_label(iv_minus_rv: float | None, downside_skew: float | None, gamma_total: float | None, concentration: float | None) -> tuple[str, list[str], list[str]]:
    support: list[str] = []
    contradict: list[str] = []
    if downside_skew is not None and downside_skew >= 0.05:
        support.append(f"25-delta downside skew is {downside_skew:.1%}")
        return "Downside protection expensive", support, contradict
    if iv_minus_rv is not None and iv_minus_rv >= 0.08:
        support.append(f"ATM IV exceeds 20-day realized volatility by {iv_minus_rv:.1%}")
        return "Volatility expensive", support, contradict
    if iv_minus_rv is not None and iv_minus_rv <= -0.05:
        support.append(f"ATM IV trails 20-day realized volatility by {abs(iv_minus_rv):.1%}")
        return "Volatility inexpensive", support, contradict
    if concentration is not None and concentration >= 0.40:
        support.append(f"Top-strike open-interest concentration is {concentration:.1%}")
        return "Concentrated pinning risk", support, contradict
    if gamma_total is not None:
        support.append("Estimated gamma is positive under the selected public-data sign assumption" if gamma_total >= 0 else "Estimated gamma is negative under the selected public-data sign assumption")
        return ("Positive-gamma estimate" if gamma_total >= 0 else "Negative-gamma estimate"), support, contradict
    if iv_minus_rv is not None:
        support.append(f"ATM IV minus realized volatility is {iv_minus_rv:.1%}")
        return "Volatility fairly priced", support, contradict
    return "Insufficient data", support, ["Required volatility or gamma inputs are unavailable"]


def analyze_options_snapshots(
    contracts: pd.DataFrame,
    market_history: pd.DataFrame,
    *,
    analytics_run_id: str = "",
) -> pd.DataFrame:
    """Build expiration-level summaries for each stored snapshot and sign assumption."""

    if contracts.empty:
        return pd.DataFrame()
    market_features = build_market_features(market_history)
    realized_map = {}
    if not market_features.empty:
        realized_map = market_features.groupby("symbol", sort=False).tail(1).set_index("symbol")["realized_vol_20d"].to_dict()
    working = contracts.copy()
    working["quote_timestamp"] = pd.to_datetime(working["quote_timestamp"], utc=True, errors="coerce")
    working["expiration"] = pd.to_datetime(working["expiration"], errors="coerce").dt.date
    calculation_ts = pd.Timestamp.now(tz="UTC")
    rows: list[dict[str, object]] = []
    for (snapshot_id, symbol), snapshot in working.groupby(["snapshot_id", "symbol"], sort=False):
        spot = float(pd.to_numeric(snapshot["underlying_price"], errors="coerce").dropna().iloc[0])
        quote_timestamp = snapshot["quote_timestamp"].dropna().iloc[0]
        expiration_iv: dict[object, float] = {}
        for expiration, expiration_frame in snapshot.groupby("expiration", sort=True):
            atm = select_atm_contract(expiration_frame, spot)
            if atm is not None and pd.notna(atm.get("implied_volatility")):
                expiration_iv[expiration] = float(atm["implied_volatility"])
        term_slope = None
        if len(expiration_iv) >= 2:
            ordered_iv = [expiration_iv[key] for key in sorted(expiration_iv)]
            term_slope = ordered_iv[-1] - ordered_iv[0]

        for expiration, expiration_frame in snapshot.groupby("expiration", sort=True):
            time_years = _time_years(expiration, quote_timestamp)
            days_to_expiration = time_years * 365.0
            calls = expiration_frame[expiration_frame["option_type"].str.lower() == "call"]
            puts = expiration_frame[expiration_frame["option_type"].str.lower() == "put"]
            call_volume = pd.to_numeric(calls["volume"], errors="coerce").sum(min_count=1)
            put_volume = pd.to_numeric(puts["volume"], errors="coerce").sum(min_count=1)
            call_oi = pd.to_numeric(calls["open_interest"], errors="coerce").sum(min_count=1)
            put_oi = pd.to_numeric(puts["open_interest"], errors="coerce").sum(min_count=1)
            atm_call = select_atm_contract(calls, spot, "call")
            atm_put = select_atm_contract(puts, spot, "put")
            atm_ivs = [float(item["implied_volatility"]) for item in [atm_call, atm_put] if item is not None and pd.notna(item.get("implied_volatility"))]
            atm_iv = float(np.median(atm_ivs)) if atm_ivs else None
            median_iv_value = pd.to_numeric(expiration_frame["implied_volatility"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna().median()
            median_iv = None if pd.isna(median_iv_value) else float(median_iv_value)
            quality_label, quote_coverage = _bid_ask_quality(expiration_frame)
            call_mid = mid_price(atm_call.get("bid"), atm_call.get("ask"), atm_call.get("last_price")) if atm_call is not None else None
            put_mid = mid_price(atm_put.get("bid"), atm_put.get("ask"), atm_put.get("last_price")) if atm_put is not None else None
            expected_move = expected_move_from_straddle(call_mid, put_mid)
            expected_method = "ATM straddle midpoint"
            if expected_move is None:
                expected_move = expected_move_from_iv(spot, atm_iv, time_years) if atm_iv is not None else None
                expected_method = "Implied-volatility approximation"
            put_25 = select_25_delta_contract(expiration_frame, spot=spot, time_years=time_years, option_type="put")
            call_25 = select_25_delta_contract(expiration_frame, spot=spot, time_years=time_years, option_type="call")
            put_iv = float(put_25["implied_volatility"]) if put_25 is not None and pd.notna(put_25.get("implied_volatility")) else None
            call_iv = float(call_25["implied_volatility"]) if call_25 is not None and pd.notna(call_25.get("implied_volatility")) else None
            risk_reversal_value = risk_reversal(put_iv, call_iv)
            downside_skew = -risk_reversal_value if risk_reversal_value is not None else None
            call_concentration = open_interest_concentration(calls["open_interest"])
            put_concentration = open_interest_concentration(puts["open_interest"])
            call_wall = float(calls.loc[pd.to_numeric(calls["open_interest"], errors="coerce").idxmax(), "strike"]) if pd.to_numeric(calls["open_interest"], errors="coerce").notna().any() else None
            put_wall = float(puts.loc[pd.to_numeric(puts["open_interest"], errors="coerce").idxmax(), "strike"]) if pd.to_numeric(puts["open_interest"], errors="coerce").notna().any() else None
            realized_vol = _number(realized_map.get(symbol))
            iv_minus_realized = atm_iv - realized_vol if atm_iv is not None and realized_vol is not None else None
            sensitivity = gamma_assumption_sensitivity(expiration_frame, spot=spot, time_years=time_years)
            scenarios = np.linspace(spot * 0.80, spot * 1.20, 41)

            for assumption in GAMMA_ASSUMPTIONS:
                gamma_by_strike = gamma_exposure_by_strike(
                    expiration_frame,
                    spot=spot,
                    time_years=time_years,
                    assumption_set=assumption,
                )
                gamma_total_value = pd.to_numeric(gamma_by_strike["estimated_gamma_exposure"], errors="coerce").sum(min_count=1)
                gamma_total = None if pd.isna(gamma_total_value) else float(gamma_total_value)
                flip = gamma_flip_estimate(expiration_frame, spot_scenarios=scenarios, time_years=time_years, assumption_set=assumption)
                condition, supporting, contradicting = _condition_label(
                    iv_minus_realized,
                    downside_skew,
                    gamma_total,
                    max(value for value in [call_concentration, put_concentration] if value is not None) if any(value is not None for value in [call_concentration, put_concentration]) else None,
                )
                confidence = "high" if quote_coverage >= 0.80 and atm_iv is not None and put_iv is not None and call_iv is not None else "medium" if quote_coverage >= 0.50 and atm_iv is not None else "low"
                rows.append(
                    {
                        "analytics_run_id": analytics_run_id,
                        "snapshot_id": snapshot_id,
                        "symbol": symbol,
                        "expiration": expiration,
                        "assumption_set": assumption,
                        "calculation_ts": calculation_ts,
                        "quote_timestamp": quote_timestamp,
                        "underlying_price": spot,
                        "days_to_expiration": days_to_expiration,
                        "total_call_volume": None if pd.isna(call_volume) else float(call_volume),
                        "total_put_volume": None if pd.isna(put_volume) else float(put_volume),
                        "put_call_volume_ratio": put_call_ratio(put_volume, call_volume),
                        "total_call_open_interest": None if pd.isna(call_oi) else float(call_oi),
                        "total_put_open_interest": None if pd.isna(put_oi) else float(put_oi),
                        "put_call_open_interest_ratio": put_call_ratio(put_oi, call_oi),
                        "atm_implied_volatility": atm_iv,
                        "median_implied_volatility": median_iv,
                        "bid_ask_quality": quality_label,
                        "realized_volatility_20d": realized_vol,
                        "implied_minus_realized_volatility": iv_minus_realized,
                        "term_structure_slope": term_slope,
                        "expected_move": expected_move,
                        "expected_move_method": expected_method,
                        "put_25_delta_iv": put_iv,
                        "call_25_delta_iv": call_iv,
                        "risk_reversal_25d": risk_reversal_value,
                        "downside_skew": downside_skew,
                        "call_oi_concentration": call_concentration,
                        "put_oi_concentration": put_concentration,
                        "call_wall": call_wall,
                        "put_wall": put_wall,
                        "estimated_gamma_exposure": gamma_total,
                        "gamma_flip": flip,
                        "gamma_by_strike": gamma_by_strike.to_json(orient="records"),
                        "gamma_sensitivity": json.dumps(sensitivity, sort_keys=True),
                        "condition_label": condition,
                        "supporting_metrics": json.dumps(supporting),
                        "contradicting_metrics": json.dumps(contradicting),
                        "assumptions": json.dumps(
                            [
                                f"Gamma sign assumption: {assumption}",
                                "Risk-free rate fixed at 4%; dividend yield fixed at 0% for Greek approximation",
                                "Public option chains do not reveal dealer inventory",
                            ]
                        ),
                        "confidence": confidence,
                        "limitations": json.dumps(
                            [
                                "Free-provider quotes may be delayed, stale, crossed, or incomplete",
                                "Estimated Gamma Exposure is not confirmed dealer exposure",
                                "Historical options analysis begins with locally collected snapshots",
                            ]
                        ),
                        "source_label": "yfinance/Yahoo Finance (research-grade, replaceable)",
                    }
                )
    return pd.DataFrame(rows)
