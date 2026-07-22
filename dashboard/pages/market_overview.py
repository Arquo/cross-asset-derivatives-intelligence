"""Market overview backed by persisted market-intelligence outputs."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.empty_states import render_pipeline_empty_state
from dashboard.components.layout import render_page_header, render_section_heading
from cross_asset_intelligence.services.intelligence_service import MarketIntelligenceService
from cross_asset_intelligence.services.market_data_service import normalize_performance


DATABASE_PATH = Path(os.getenv("CROSS_ASSET_DATABASE_PATH", "data/database/cross_asset.duckdb"))
MARKET_COMMAND = "python scripts/ingest_data.py --provider market"
ANALYTICS_COMMAND = "python scripts/run_analytics.py"


@st.cache_data(ttl=600, show_spinner=False)
def load_overview_intelligence(database_path: str) -> dict[str, pd.DataFrame]:
    service = MarketIntelligenceService(Path(database_path))
    return {
        "screener": service.latest_screener(),
        "liquidity": service.liquidity_history(),
        "positioning": service.positioning_history(),
        "options": service.latest_option_analytics(),
        "summary": service.latest_summary(),
        "market_attempt": service.latest_pipeline_attempt("yfinance"),
        "analytics_runs": service.latest_runs(),
    }


def _timestamp(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return "Unavailable"
    value = pd.to_datetime(frame[column], utc=True, errors="coerce").max()
    return "Unavailable" if pd.isna(value) else value.strftime("%Y-%m-%d %H:%M UTC")


def _value(row: pd.Series | None, column: str, fallback: str = "Unavailable") -> str:
    return fallback if row is None or pd.isna(row.get(column)) else str(row.get(column))


def render(
    *,
    latest_market: pd.DataFrame,
    latest_macro: pd.DataFrame,
    market_history: pd.DataFrame,
    yield_history: pd.DataFrame,
    vix_history: pd.DataFrame,
    database_command: str,
    latest_refresh_timestamp,
    overall_health: dict,
) -> None:
    render_page_header(
        "Cross-Asset Derivatives Intelligence Platform",
        "Deterministic end-of-day market evidence across price, liquidity, positioning, options, credit, and rates.",
        badges=["Market Overview", "Stored analytics"],
    )
    state = load_overview_intelligence(str(DATABASE_PATH))
    if latest_market.empty:
        render_pipeline_empty_state(
            title="Daily market data is missing",
            dataset="Configured cross-asset OHLCV universe",
            command=MARKET_COMMAND,
            latest_attempt=state["market_attempt"],
        )
        return

    screener = state["screener"]
    liquidity = state["liquidity"]
    positioning = state["positioning"]
    options = state["options"]
    summary = state["summary"]
    spy = screener[screener["symbol"] == "SPY"].iloc[0] if not screener.empty and not screener[screener["symbol"] == "SPY"].empty else None
    spy_liquidity_rows = liquidity[liquidity["symbol"] == "SPY"] if not liquidity.empty else pd.DataFrame()
    spy_liquidity = spy_liquidity_rows.sort_values("observation_ts").iloc[-1] if not spy_liquidity_rows.empty else None
    summary_row = summary.iloc[0] if not summary.empty else None

    top = st.columns(4)
    top[0].metric("Latest market observation", _timestamp(latest_market, "latest_trading_date"))
    top[1].metric("Latest CFTC report", _timestamp(positioning, "report_date"))
    top[2].metric("Latest options snapshot", _timestamp(options, "quote_timestamp"))
    health_label = overall_health.get("status", "missing").replace("_", " ").title()
    top[3].metric("Overall data health", health_label)

    primary = st.columns(5)
    primary[0].metric("Market Pressure Score", f"{float(spy['market_pressure_score']):.1f}" if spy is not None and pd.notna(spy.get("market_pressure_score")) else "Unavailable")
    primary[1].metric("Liquidity regime", _value(spy_liquidity, "liquidity_regime"))
    primary[2].metric("Volatility regime", _value(spy, "volatility_classification"))
    primary[3].metric("SPY options", _value(summary_row, "spy_options_condition"))
    primary[4].metric("QQQ options", _value(summary_row, "qqq_options_condition"))
    st.metric("Major positioning risk", _value(summary_row, "major_positioning_risk"))

    if summary_row is None:
        render_pipeline_empty_state(
            title="The deterministic market setup has not run",
            dataset="Screener, liquidity, positioning, options, and cross-module summary analytics",
            command=ANALYTICS_COMMAND,
            latest_attempt=state["analytics_runs"],
        )
    else:
        render_section_heading("Today's Market Setup", "Calculated statements with retained confirmations and contradictions.")
        setup = json.loads(summary_row.get("market_setup") or "{}")
        setup_columns = st.columns(2)
        for index, title in enumerate(["Price action", "Liquidity", "Positioning", "Options", "Main confirmation", "Main contradiction", "Main risk"]):
            setup_columns[index % 2].markdown(f"**{title}:** {setup.get(title, 'Unavailable')}")
        st.caption(f"Summary confidence: {str(summary_row['confidence']).title()} | Generated: {_timestamp(summary, 'generated_timestamp')}")

    render_section_heading("Cross-asset performance", "Stored adjusted-close history normalized to 100 at the first observation.")
    performance = normalize_performance(market_history) if not market_history.empty else pd.DataFrame()
    fig = go.Figure()
    for symbol in ["SPY", "QQQ", "IWM", "TLT", "HYG", "GLD", "USO", "UUP", "SMH", "XLF", "XLE", "XLK"]:
        subset = performance[performance["symbol"] == symbol] if not performance.empty else pd.DataFrame()
        if not subset.empty:
            fig.add_trace(go.Scatter(x=subset["observation_ts"], y=subset["normalized_value"], mode="lines", name=symbol))
    fig.update_layout(height=390, yaxis_title="Normalized value", xaxis_title="Observation date")
    st.plotly_chart(fig, use_container_width=True)

    table_col, macro_col = st.columns([1.5, 1])
    with table_col:
        render_section_heading("Latest market pressure")
        if not screener.empty:
            st.dataframe(
                screener[["symbol", "market_pressure_score", "pressure_label", "trend_classification", "liquidity_classification", "freshness_status"]],
                use_container_width=True,
                hide_index=True,
            )
    with macro_col:
        render_section_heading("Credit and rates context")
        macro_lookup = latest_macro.set_index("series_id") if not latest_macro.empty else pd.DataFrame()
        for series_id, label in [("DGS10", "10Y Treasury"), ("DGS2", "2Y Treasury"), ("T10Y2Y", "10Y-2Y spread"), ("BAMLH0A0HYM2", "High-yield OAS")]:
            value = macro_lookup.loc[series_id, "latest_value"] if not macro_lookup.empty and series_id in macro_lookup.index else None
            st.metric(label, f"{float(value):.2f}" if value is not None and pd.notna(value) else "Unavailable")

    st.caption("All displayed market and options vendor data are research-grade and delayed. Observation timestamps are distinct from ingestion and calculation timestamps.")
