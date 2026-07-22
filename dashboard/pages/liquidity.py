"""Liquidity & Market-Structure Proxies page."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.empty_states import render_pipeline_empty_state
from dashboard.components.freshness import format_utc_timestamp
from dashboard.components.layout import render_page_header, render_section_heading
from cross_asset_intelligence.services.intelligence_service import MarketIntelligenceService


DATABASE_PATH = Path(os.getenv("CROSS_ASSET_DATABASE_PATH", "data/database/cross_asset.duckdb"))
MARKET_COMMAND = "python scripts/ingest_data.py --provider market"
ANALYTICS_COMMAND = "python scripts/run_analytics.py"


@st.cache_data(ttl=600, show_spinner=False)
def load_liquidity(database_path: str) -> dict[str, pd.DataFrame]:
    service = MarketIntelligenceService(Path(database_path))
    return {
        "liquidity": service.liquidity_history(),
        "market": service.market_history(),
        "market_attempt": service.latest_pipeline_attempt("yfinance"),
        "analytics_runs": service.latest_runs(),
    }


def _fmt(value: object, pattern: str = ".2f") -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return "Unavailable" if pd.isna(numeric) else format(float(numeric), pattern)


def _line_chart(frame: pd.DataFrame, column: str, title: str, y_title: str = "") -> go.Figure:
    fig = go.Figure(go.Scatter(x=frame["observation_ts"], y=frame[column], mode="lines", name=title))
    fig.update_layout(title=title, height=310, yaxis_title=y_title)
    return fig


def render() -> None:
    render_page_header(
        "Liquidity & Market-Structure Proxies",
        "Transparent daily-bar stress measures with auditable component contributions.",
        badges=["Bar-data proxies", "Stored analytics"],
    )
    st.warning(
        "This module uses bar-data proxies. It does not measure full order-book depth, effective spreads, realized spreads, or exchange fragmentation."
    )
    state = load_liquidity(str(DATABASE_PATH))
    frame = state["liquidity"]
    if frame.empty:
        if state["market"].empty:
            render_pipeline_empty_state(
                title="Daily market observations are required",
                dataset="OHLCV inputs for liquidity proxies",
                command=MARKET_COMMAND,
                latest_attempt=state["market_attempt"],
            )
        else:
            render_pipeline_empty_state(
                title="Liquidity analytics have not been persisted",
                dataset="Liquidity stress history and component contributions",
                command=ANALYTICS_COMMAND,
                latest_attempt=state["analytics_runs"],
            )
        return

    symbol = st.selectbox("Market asset", sorted(frame["symbol"].unique()), index=sorted(frame["symbol"].unique()).index("SPY") if "SPY" in frame["symbol"].unique() else 0)
    history = frame[frame["symbol"] == symbol].sort_values("observation_ts")
    latest = history.iloc[-1]
    st.caption(
        f"Source: {latest['source_label']} | Latest observation: {format_utc_timestamp(latest['observation_ts'])} | "
        f"Freshness: {latest['freshness_status']} | Confidence: {str(latest['confidence']).title()}"
    )

    metrics = st.columns(6)
    metrics[0].metric("Liquidity stress", _fmt(latest["liquidity_stress_score"], ".1f"))
    metrics[1].metric("Historical percentile", _fmt(latest["stress_historical_percentile"], ".1%"))
    metrics[2].metric("Regime", str(latest["liquidity_regime"]))
    relative_dollar = _fmt(latest["relative_dollar_volume_20d"], ".2f")
    metrics[3].metric("Relative dollar volume", f"{relative_dollar}x" if relative_dollar != "Unavailable" else relative_dollar)
    metrics[4].metric("20D realized volatility", _fmt(latest["realized_volatility_20d"], ".1%"))
    metrics[5].metric("Amihud percentile", _fmt(latest["amihud_percentile"], ".1%"))

    contributions = pd.DataFrame(json.loads(latest.get("component_contributions") or "[]"))
    render_section_heading("Stress components", "Base and redistributed weights are shown explicitly.")
    if not contributions.empty:
        fig = go.Figure(go.Bar(x=contributions["contribution"], y=contributions["component"], orientation="h"))
        fig.update_layout(height=320, xaxis_title="Stress-score points")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(contributions, use_container_width=True, hide_index=True)
    missing = json.loads(latest.get("missing_components") or "[]")
    st.caption(f"Missing components: {', '.join(missing) if missing else 'None'}. Missing weights are redistributed among available components.")

    render_section_heading("Proxy history", f"Stored daily calculations for {symbol}.")
    charts = [
        ("liquidity_stress_score", "Composite liquidity stress", "Score (0-100)"),
        ("amihud_illiquidity_20d", "Amihud illiquidity", "Absolute return / dollar volume"),
        ("dollar_volume", "Dollar volume", "USD proxy"),
        ("relative_volume_20d", "Relative volume", "Multiple"),
        ("realized_volatility_20d", "Realized volatility", "Annualized"),
        ("intraday_range_pct", "Intraday range", "Range / close"),
        ("hyg_stress", "HYG stress", "Normalized stress"),
        ("vix_stress", "VIX stress", "Historical percentile"),
    ]
    for start in range(0, len(charts), 2):
        columns = st.columns(2)
        for column, (field, title, unit) in zip(columns, charts[start : start + 2], strict=False):
            with column:
                st.plotly_chart(_line_chart(history, field, title, unit), use_container_width=True)

    render_section_heading("Latest cross-asset liquidity table")
    latest_all = frame.sort_values("observation_ts").groupby("symbol", sort=False).tail(1)
    st.dataframe(
        latest_all[
            [
                "symbol",
                "observation_ts",
                "dollar_volume",
                "average_dollar_volume_20d",
                "relative_volume_20d",
                "realized_volatility_20d",
                "intraday_range_pct",
                "average_true_range_14d",
                "amihud_percentile",
                "volume_shock_zscore",
                "price_impact_proxy",
                "drawdown",
                "liquidity_stress_score",
                "liquidity_regime",
                "freshness_status",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )
    with st.expander("Methodology and limitations"):
        st.markdown(
            "The score uses Amihud illiquidity percentile (25%), realized-volatility percentile (20%), intraday-range percentile (15%), "
            "inverse relative dollar volume (15%), HYG stress (15%), and VIX stress (10%). It is a market-liquidity proxy, not a transaction-cost model."
        )
