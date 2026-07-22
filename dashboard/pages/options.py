"""SPY and QQQ options analytics page."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.empty_states import render_pipeline_empty_state
from dashboard.components.freshness import format_utc_timestamp
from dashboard.components.layout import render_page_header, render_section_heading, render_warning_panel
from cross_asset_intelligence.analytics.options.calculations import GAMMA_ASSUMPTIONS, gamma_exposure_by_strike
from cross_asset_intelligence.services.intelligence_service import MarketIntelligenceService


DATABASE_PATH = Path(os.getenv("CROSS_ASSET_DATABASE_PATH", "data/database/cross_asset.duckdb"))
OPTIONS_COMMAND = "python scripts/ingest_data.py --provider options --symbols SPY QQQ"
ANALYTICS_COMMAND = "python scripts/run_analytics.py"


@st.cache_data(ttl=600, show_spinner=False)
def load_options(database_path: str) -> dict[str, pd.DataFrame]:
    service = MarketIntelligenceService(Path(database_path))
    return {
        "analytics": service.latest_option_analytics(),
        "contracts": service.latest_option_contracts(),
        "pipeline_attempt": service.latest_pipeline_attempt("yfinance-options"),
        "analytics_runs": service.latest_runs(),
    }


@st.cache_data(ttl=600, show_spinner=False)
def gamma_profile(frame: pd.DataFrame, spot: float, time_years: float, assumption: str) -> pd.DataFrame:
    rows = []
    for scenario in np.linspace(spot * 0.80, spot * 1.20, 41):
        by_strike = gamma_exposure_by_strike(frame, spot=float(scenario), time_years=time_years, assumption_set=assumption)
        total = pd.to_numeric(by_strike["estimated_gamma_exposure"], errors="coerce").sum(min_count=1)
        rows.append({"spot": scenario, "estimated_gamma_exposure": total})
    return pd.DataFrame(rows)


def _select_expiration(frame: pd.DataFrame, mode: str) -> object:
    ordered = frame.sort_values("days_to_expiration")
    if mode == "Nearest expiration with at least 7 days":
        eligible = ordered[ordered["days_to_expiration"] >= 7]
        return (eligible if not eligible.empty else ordered).iloc[0]["expiration"]
    if mode == "Nearest expiration with at least 30 days":
        eligible = ordered[ordered["days_to_expiration"] >= 30]
        return (eligible if not eligible.empty else ordered).iloc[0]["expiration"]
    return ordered.iloc[0]["expiration"]


def _fmt(value: object, pattern: str = ".2f") -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return "Unavailable" if pd.isna(numeric) else format(float(numeric), pattern)


def render() -> None:
    render_page_header(
        "SPY & QQQ Options",
        "Current option-chain conditions, volatility, skew, open interest, and assumption-sensitive gamma estimates.",
        badges=["Snapshot data", "Research-grade provider"],
    )
    st.caption("yfinance is a free, research-grade, replaceable provider. Quotes may be delayed or incomplete; snapshot history begins when this project collects it.")
    state = load_options(str(DATABASE_PATH))
    contracts = state["contracts"]
    analytics = state["analytics"]
    if contracts.empty:
        render_pipeline_empty_state(
            title="SPY and QQQ option snapshots are required",
            dataset="Timestamped current option chains",
            command=OPTIONS_COMMAND,
            latest_attempt=state["pipeline_attempt"],
        )
        return
    if analytics.empty:
        render_pipeline_empty_state(
            title="Option analytics have not been persisted",
            dataset="Option condition, volatility, skew, open-interest, and gamma calculations",
            command=ANALYTICS_COMMAND,
            latest_attempt=state["analytics_runs"],
        )
        return

    symbol = st.segmented_control("Underlying", ["SPY", "QQQ"], default="SPY") or "SPY"
    symbol_analytics = analytics[analytics["symbol"] == symbol].copy()
    if symbol_analytics.empty:
        render_warning_panel(f"{symbol} has no stored analytics. Run `{OPTIONS_COMMAND}` and then `{ANALYTICS_COMMAND}`.")
        return
    symbol_analytics["expiration"] = pd.to_datetime(symbol_analytics["expiration"]).dt.date
    mode_col, assumption_col = st.columns(2)
    mode = mode_col.selectbox(
        "Expiration control",
        ["Nearest expiration", "Nearest expiration with at least 7 days", "Nearest expiration with at least 30 days", "Custom expiration"],
        index=1,
    )
    assumption = assumption_col.selectbox("Gamma sign assumption", list(GAMMA_ASSUMPTIONS.keys()), index=0)
    assumption_rows = symbol_analytics[symbol_analytics["assumption_set"] == assumption].copy()
    if mode == "Custom expiration":
        expiration = st.selectbox("Expiration", sorted(assumption_rows["expiration"].unique()))
    else:
        expiration = _select_expiration(assumption_rows, mode)
    row = assumption_rows[assumption_rows["expiration"] == expiration].iloc[0]
    chain = contracts[(contracts["symbol"] == symbol) & (pd.to_datetime(contracts["expiration"]).dt.date == expiration)].copy()

    st.caption(
        f"Source: {row['source_label']} | Quote snapshot: {format_utc_timestamp(row['quote_timestamp'])} | "
        f"Expiration: {expiration} | Confidence: {str(row['confidence']).title()}"
    )
    metrics = st.columns(6)
    metrics[0].metric("Underlying", f"${_fmt(row['underlying_price'])}")
    metrics[1].metric("Days to expiration", _fmt(row["days_to_expiration"], ".1f"))
    metrics[2].metric("Put/call volume", _fmt(row["put_call_volume_ratio"]))
    metrics[3].metric("Put/call open interest", _fmt(row["put_call_open_interest_ratio"]))
    metrics[4].metric("ATM implied volatility", f"{_fmt(row['atm_implied_volatility'], '.1%')}")
    metrics[5].metric("20D realized volatility", f"{_fmt(row['realized_volatility_20d'], '.1%')}")

    second = st.columns(6)
    second[0].metric("Call volume", _fmt(row["total_call_volume"], ",.0f"))
    second[1].metric("Put volume", _fmt(row["total_put_volume"], ",.0f"))
    second[2].metric("Median IV", _fmt(row["median_implied_volatility"], ".1%"))
    second[3].metric("IV minus realized", _fmt(row["implied_minus_realized_volatility"], ".1%"))
    second[4].metric("Expected move", f"${_fmt(row['expected_move'])}")
    second[5].metric("Bid-ask quality", str(row["bid_ask_quality"]))

    render_section_heading("Deterministic options condition")
    st.info(str(row["condition_label"]))
    evidence_cols = st.columns(3)
    evidence_cols[0].markdown("**Supporting metrics**")
    evidence_cols[0].write(json.loads(row.get("supporting_metrics") or "[]"))
    evidence_cols[1].markdown("**Contradicting metrics**")
    evidence_cols[1].write(json.loads(row.get("contradicting_metrics") or "[]"))
    evidence_cols[2].markdown("**Expected-move methodology**")
    evidence_cols[2].write(str(row["expected_move_method"]))

    calls = chain[chain["option_type"] == "call"]
    puts = chain[chain["option_type"] == "put"]
    chart_left, chart_right = st.columns(2)
    with chart_left:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=calls["strike"], y=calls["open_interest"], name="Calls"))
        fig.add_trace(go.Bar(x=puts["strike"], y=puts["open_interest"], name="Puts"))
        fig.update_layout(title="Open interest by strike", barmode="group", height=350)
        st.plotly_chart(fig, use_container_width=True)
    with chart_right:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=calls["strike"], y=calls["volume"], name="Calls"))
        fig.add_trace(go.Bar(x=puts["strike"], y=puts["volume"], name="Puts"))
        fig.update_layout(title="Option volume by strike", barmode="group", height=350)
        st.plotly_chart(fig, use_container_width=True)

    chart_left, chart_right = st.columns(2)
    with chart_left:
        fig = go.Figure()
        for option_type, subset in chain.groupby("option_type", sort=False):
            fig.add_trace(go.Scatter(x=subset["strike"], y=subset["implied_volatility"], mode="lines+markers", name=option_type.title()))
        fig.update_layout(title="Implied volatility smile", height=350, yaxis_tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)
    with chart_right:
        gamma_by_strike = pd.DataFrame(json.loads(row.get("gamma_by_strike") or "[]"))
        fig = go.Figure(go.Bar(x=gamma_by_strike.get("strike"), y=gamma_by_strike.get("estimated_gamma_exposure")))
        fig.update_layout(title="Estimated Gamma Exposure by strike", height=350)
        st.plotly_chart(fig, use_container_width=True)

    chart_left, chart_right = st.columns(2)
    with chart_left:
        profile = gamma_profile(chain, float(row["underlying_price"]), max(float(row["days_to_expiration"]) / 365.0, 1 / 365), assumption)
        fig = go.Figure(go.Scatter(x=profile["spot"], y=profile["estimated_gamma_exposure"], mode="lines"))
        fig.add_vline(x=float(row["underlying_price"]), line_dash="dash")
        fig.update_layout(title="Gamma profile across spot scenarios", height=350, xaxis_title="Spot scenario")
        st.plotly_chart(fig, use_container_width=True)
    with chart_right:
        term = assumption_rows.sort_values("days_to_expiration").drop_duplicates("expiration")
        fig = go.Figure(go.Scatter(x=term["days_to_expiration"], y=term["atm_implied_volatility"], mode="lines+markers"))
        fig.update_layout(title="Volatility term structure", height=350, xaxis_title="Days", yaxis_tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

    spot = float(row["underlying_price"])
    expected = pd.to_numeric(pd.Series([row["expected_move"]]), errors="coerce").iloc[0]
    if pd.notna(expected):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[spot - expected, spot, spot + expected], y=["Expected range"] * 3, mode="markers+lines", marker={"size": [10, 14, 10]}))
        fig.update_layout(title="Expected-move range", height=220, xaxis_title="Underlying price", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    structure = st.columns(5)
    structure[0].metric("25-delta put IV", _fmt(row["put_25_delta_iv"], ".1%"))
    structure[1].metric("25-delta call IV", _fmt(row["call_25_delta_iv"], ".1%"))
    structure[2].metric("25-delta risk reversal", _fmt(row["risk_reversal_25d"], ".1%"))
    structure[3].metric("Call wall estimate", _fmt(row["call_wall"], ".0f"))
    structure[4].metric("Put wall estimate", _fmt(row["put_wall"], ".0f"))

    render_section_heading("Estimated Gamma Exposure", "Public chains do not reveal dealer inventory; signs are scenario assumptions, not observed positions.")
    gamma_metrics = st.columns(3)
    gamma_metrics[0].metric("Selected-assumption estimate", _fmt(row["estimated_gamma_exposure"], ",.0f"))
    gamma_metrics[1].metric("Gamma-flip estimate", _fmt(row["gamma_flip"]))
    gamma_metrics[2].metric("Estimation confidence", str(row["confidence"]).title())
    sensitivity = pd.DataFrame(
        [{"Assumption": key, "Estimated exposure": value} for key, value in json.loads(row.get("gamma_sensitivity") or "{}").items()]
    )
    st.dataframe(sensitivity, use_container_width=True, hide_index=True)
    with st.expander("Assumptions and limitations"):
        st.write(json.loads(row.get("assumptions") or "[]"))
        st.write(json.loads(row.get("limitations") or "[]"))
