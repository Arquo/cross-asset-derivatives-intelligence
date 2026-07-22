"""Deterministic cross-module market setup synthesis."""

from __future__ import annotations

import pandas as pd


def _format_number(value: object) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return "unavailable" if pd.isna(numeric) else f"{float(numeric):.1f}"


def _latest(frame: pd.DataFrame, timestamp_column: str, **filters: str) -> pd.Series | None:
    if frame.empty or timestamp_column not in frame.columns:
        return None
    subset = frame.copy()
    for column, value in filters.items():
        if column in subset.columns:
            subset = subset[subset[column] == value]
    if subset.empty:
        return None
    return subset.sort_values(timestamp_column).iloc[-1]


def _option_row(frame: pd.DataFrame, symbol: str) -> pd.Series | None:
    if frame.empty:
        return None
    subset = frame[(frame["symbol"] == symbol) & (frame["assumption_set"] == "calls_positive_puts_negative")].copy()
    if subset.empty:
        return None
    eligible = subset[pd.to_numeric(subset["days_to_expiration"], errors="coerce") >= 7]
    selected = eligible if not eligible.empty else subset
    return selected.sort_values(["quote_timestamp", "days_to_expiration"], ascending=[False, True]).iloc[0]


def build_cross_module_summary(
    screener: pd.DataFrame,
    liquidity: pd.DataFrame,
    positioning: pd.DataFrame,
    options: pd.DataFrame,
) -> dict[str, object]:
    """Build repeatable prose and evidence lists from calculated module rows."""

    spy = _latest(screener, "observation_ts", symbol="SPY")
    spy_liquidity = _latest(liquidity, "observation_ts", symbol="SPY")
    spy_options = _option_row(options, "SPY")
    qqq_options = _option_row(options, "QQQ")

    supporting: list[str] = []
    contradicting: list[str] = []
    limitations: list[str] = []
    setup: dict[str, str] = {}

    if spy is None:
        pressure_regime = "Insufficient data"
        volatility_condition = "Insufficient data"
        setup["Price action"] = "SPY screener analytics are unavailable."
        limitations.append("Market screener analytics are missing")
    else:
        pressure_regime = str(spy.get("pressure_label", "Insufficient data"))
        volatility_condition = str(spy.get("volatility_classification", "Insufficient data"))
        pressure_value = pd.to_numeric(pd.Series([spy.get("market_pressure_score")]), errors="coerce").iloc[0]
        setup["Price action"] = f"SPY is in a {spy.get('trend_classification')} with a Market Pressure Score of {_format_number(pressure_value)}."
        if pd.notna(pressure_value) and float(pressure_value) >= 20:
            supporting.append(f"SPY market pressure is positive at {float(pressure_value):.1f}")
        elif pd.notna(pressure_value) and float(pressure_value) <= -20:
            contradicting.append(f"SPY market pressure is negative at {float(pressure_value):.1f}")

    if spy_liquidity is None:
        liquidity_condition = "Insufficient data"
        setup["Liquidity"] = "Liquidity proxy analytics are unavailable."
        limitations.append("Liquidity analytics are missing")
    else:
        liquidity_condition = str(spy_liquidity.get("liquidity_regime", "Insufficient data"))
        setup["Liquidity"] = f"Daily-bar proxies classify liquidity as {liquidity_condition} with stress {_format_number(spy_liquidity.get('liquidity_stress_score'))}/100."
        if liquidity_condition in {"Abundant", "Normal"}:
            supporting.append(f"Liquidity is {liquidity_condition.lower()}")
        elif liquidity_condition in {"Tightening", "Stressed"}:
            contradicting.append(f"Liquidity is {liquidity_condition.lower()}")

    latest_positioning = positioning.sort_values("report_date").groupby(["internal_asset_id", "participant_category"], sort=False).tail(1) if not positioning.empty else pd.DataFrame()
    risk_rows = latest_positioning[
        latest_positioning.get("crowding_condition", pd.Series(index=latest_positioning.index, dtype="object")).isin(["Crowded long", "Crowded short"])
        | latest_positioning.get("positioning_reversal", pd.Series(False, index=latest_positioning.index)).fillna(False)
        | latest_positioning.get("long_liquidation_risk", pd.Series(False, index=latest_positioning.index)).fillna(False)
        | latest_positioning.get("short_squeeze_risk", pd.Series(False, index=latest_positioning.index)).fillna(False)
    ] if not latest_positioning.empty else pd.DataFrame()
    if latest_positioning.empty:
        major_positioning_risk = "Unavailable"
        setup["Positioning"] = "CFTC positioning analytics are unavailable."
        limitations.append("Weekly CFTC positioning is missing")
    elif risk_rows.empty:
        major_positioning_risk = "No extreme mapped risk flag"
        setup["Positioning"] = "Mapped CFTC categories show no current extreme crowding or reversal flag."
        supporting.append("Mapped CFTC positioning is not at a flagged extreme")
    else:
        risk = risk_rows.iloc[0]
        major_positioning_risk = f"{risk['internal_asset_id']} {risk['participant_category']}: {risk['crowding_condition']}"
        setup["Positioning"] = f"The main delayed CFTC risk is {major_positioning_risk}."
        contradicting.append(f"Positioning risk: {major_positioning_risk}")

    def option_condition(row: pd.Series | None, symbol: str) -> str:
        if row is None:
            limitations.append(f"{symbol} options snapshot or analytics are missing")
            return "Unavailable"
        condition = str(row.get("condition_label", "Insufficient data"))
        if condition in {"Volatility expensive", "Downside protection expensive", "Negative-gamma estimate", "Elevated tail-risk pricing"}:
            contradicting.append(f"{symbol} options: {condition}")
        else:
            supporting.append(f"{symbol} options: {condition}")
        return condition

    spy_options_condition = option_condition(spy_options, "SPY")
    qqq_options_condition = option_condition(qqq_options, "QQQ")
    setup["Options"] = f"SPY: {spy_options_condition}. QQQ: {qqq_options_condition}. Gamma signs are assumption-based estimates."

    main_confirmation = supporting[0] if supporting else "No strong cross-module confirmation is available."
    main_contradiction = contradicting[0] if contradicting else "No major contradiction is currently flagged."
    main_risk = major_positioning_risk if major_positioning_risk not in {"Unavailable", "No extreme mapped risk flag"} else (main_contradiction if contradicting else "Incomplete data coverage")
    setup["Main confirmation"] = main_confirmation
    setup["Main contradiction"] = main_contradiction
    setup["Main risk"] = main_risk

    confidence_points = 100
    if spy is None:
        confidence_points -= 35
    if spy_liquidity is None:
        confidence_points -= 20
    if latest_positioning.empty:
        confidence_points -= 20
    if spy_options is None:
        confidence_points -= 20
    if qqq_options is None:
        confidence_points -= 10
    stale_frames = [frame for frame in [screener, liquidity] if not frame.empty and "freshness_status" in frame.columns]
    if any((frame["freshness_status"] == "Stale").any() for frame in stale_frames):
        confidence_points -= 20
        limitations.append("One or more daily datasets are stale")
    confidence = "high" if confidence_points >= 85 else "medium" if confidence_points >= 65 else "low" if confidence_points >= 40 else "insufficient"

    source_timestamps = {
        "market": None if spy is None else str(spy.get("observation_ts")),
        "liquidity": None if spy_liquidity is None else str(spy_liquidity.get("observation_ts")),
        "cftc_report": None if latest_positioning.empty else str(latest_positioning["report_date"].max()),
        "options": None if options.empty else str(options["quote_timestamp"].max()),
    }
    return {
        "overall_market_pressure_regime": pressure_regime,
        "liquidity_condition": liquidity_condition,
        "volatility_condition": volatility_condition,
        "major_positioning_risk": major_positioning_risk,
        "spy_options_condition": spy_options_condition,
        "qqq_options_condition": qqq_options_condition,
        "market_setup": setup,
        "supporting_signals": supporting,
        "contradicting_signals": contradicting,
        "data_limitations": limitations,
        "indicators_to_monitor": [
            "SPY 20-day return and 60-day moving-average distance",
            "SPY liquidity-stress score",
            "VIX stress percentile",
            "Leveraged-fund CFTC percentile",
            "SPY 25-delta downside skew",
        ],
        "confidence": confidence,
        "source_timestamps": source_timestamps,
    }
