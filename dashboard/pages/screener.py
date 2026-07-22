"""Populated Cross-Asset Screener page."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.empty_states import render_pipeline_empty_state
from dashboard.components.layout import render_page_header, render_section_heading
from cross_asset_intelligence.analytics.screener.views import VIEW_SORTS, apply_screener_filters, apply_screener_view
from cross_asset_intelligence.services.intelligence_service import MarketIntelligenceService


DATABASE_PATH = Path(os.getenv("CROSS_ASSET_DATABASE_PATH", "data/database/cross_asset.duckdb"))
MARKET_COMMAND = "python scripts/ingest_data.py --provider market"
ANALYTICS_COMMAND = "python scripts/run_analytics.py"


@st.cache_data(ttl=600, show_spinner=False)
def load_screener(database_path: str) -> dict[str, pd.DataFrame]:
    service = MarketIntelligenceService(Path(database_path))
    return {
        "screener": service.latest_screener(),
        "market": service.market_history(),
        "market_attempt": service.latest_pipeline_attempt("yfinance"),
        "analytics_runs": service.latest_runs(),
    }


def _choices(frame: pd.DataFrame, column: str) -> list[str]:
    return sorted(frame[column].dropna().astype(str).unique().tolist()) if column in frame.columns else []


def render() -> None:
    render_page_header(
        "Cross-Asset Screener",
        "Comparable daily-bar conditions and a transparent descriptive Market Pressure Score.",
        badges=["Stored analytics", "End of day"],
    )
    st.caption("Market Pressure Score describes measured pressure from -100 to +100. It is not a trading recommendation.")
    state = load_screener(str(DATABASE_PATH))
    frame = state["screener"]
    if frame.empty:
        if state["market"].empty:
            render_pipeline_empty_state(
                title="Market observations are required",
                dataset="Daily OHLCV for the configured cross-asset universe",
                command=MARKET_COMMAND,
                latest_attempt=state["market_attempt"],
            )
        else:
            render_pipeline_empty_state(
                title="Screener analytics have not been persisted",
                dataset="Screener results and Market Pressure Scores",
                command=ANALYTICS_COMMAND,
                latest_attempt=state["analytics_runs"],
            )
        return

    controls = st.columns([1.3, 1, 1, 1, 1, 1])
    view = controls[0].selectbox("Predefined view", ["All assets", *VIEW_SORTS.keys()])
    asset_class = controls[1].multiselect("Asset class", _choices(frame, "asset_class"))
    trend = controls[2].multiselect("Trend", _choices(frame, "trend_classification"))
    liquidity = controls[3].multiselect("Liquidity", _choices(frame, "liquidity_classification"))
    volatility = controls[4].multiselect("Volatility", _choices(frame, "volatility_classification"))
    freshness = controls[5].multiselect("Freshness", _choices(frame, "freshness_status"))

    secondary = st.columns([1.4, 1.4, 1.2, 0.7])
    positioning = secondary[0].multiselect("Positioning", _choices(frame, "positioning_classification"))
    sort_column = secondary[1].selectbox(
        "Sort numerical column",
        [
            "market_pressure_score",
            "return_1d",
            "return_5d",
            "return_20d",
            "return_60d",
            "realized_vol_20d",
            "relative_volume_20d",
            "dollar_volume",
            "amihud_percentile",
        ],
    )
    selected_asset = secondary[2].selectbox("Asset detail", frame["symbol"].sort_values().tolist())
    ascending = secondary[3].toggle("Ascending", value=False)

    filtered = apply_screener_filters(
        frame,
        {
            "asset_class": asset_class,
            "trend_classification": trend,
            "liquidity_classification": liquidity,
            "volatility_classification": volatility,
            "positioning_classification": positioning,
            "freshness_status": freshness,
        },
    )
    if view != "All assets":
        filtered = apply_screener_view(filtered, view)
    else:
        filtered = filtered.sort_values(sort_column, ascending=ascending, na_position="last")

    display = filtered.rename(
        columns={
            "symbol": "Asset",
            "asset_class": "Asset class",
            "latest_close": "Latest close",
            "observation_ts": "Observation date",
            "return_1d": "1D return",
            "return_5d": "5D return",
            "return_20d": "20D return",
            "return_60d": "60D return",
            "distance_ma_20d": "Distance 20D MA",
            "distance_ma_60d": "Distance 60D MA",
            "realized_vol_20d": "20D realized vol",
            "relative_volume_20d": "20D relative volume",
            "dollar_volume": "Dollar volume",
            "amihud_percentile": "Amihud percentile",
            "trend_classification": "Trend",
            "volatility_classification": "Volatility",
            "liquidity_classification": "Liquidity",
            "positioning_classification": "Positioning",
            "options_classification": "Options",
            "market_pressure_score": "Market Pressure Score",
            "freshness_status": "Freshness",
        }
    )
    visible = [
        "Asset", "Asset class", "Latest close", "Observation date", "1D return", "5D return", "20D return", "60D return",
        "Distance 20D MA", "Distance 60D MA", "20D realized vol", "20D relative volume", "Dollar volume",
        "Amihud percentile", "Trend", "Volatility", "Liquidity", "Positioning", "Options", "Market Pressure Score", "Freshness",
    ]
    st.dataframe(
        display[[column for column in visible if column in display.columns]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "1D return": st.column_config.NumberColumn(format="%.2%%"),
            "5D return": st.column_config.NumberColumn(format="%.2%%"),
            "20D return": st.column_config.NumberColumn(format="%.2%%"),
            "60D return": st.column_config.NumberColumn(format="%.2%%"),
            "Distance 20D MA": st.column_config.NumberColumn(format="%.2%%"),
            "Distance 60D MA": st.column_config.NumberColumn(format="%.2%%"),
            "20D realized vol": st.column_config.NumberColumn(format="%.2%%"),
            "20D relative volume": st.column_config.NumberColumn(format="%.2fx"),
            "Amihud percentile": st.column_config.NumberColumn(format="%.1%%"),
            "Market Pressure Score": st.column_config.ProgressColumn(min_value=-100, max_value=100, format="%.1f"),
        },
    )

    render_section_heading(f"{selected_asset} detail", "Price history and the complete score audit trail.")
    detail_row = frame[frame["symbol"] == selected_asset].iloc[0]
    metrics = st.columns(5)
    metrics[0].metric("Market Pressure Score", f"{detail_row['market_pressure_score']:.1f}" if pd.notna(detail_row["market_pressure_score"]) else "Unavailable")
    metrics[1].metric("Pressure label", str(detail_row["pressure_label"]))
    metrics[2].metric("Confidence", str(detail_row["pressure_confidence"]).title())
    metrics[3].metric("Trend", str(detail_row["trend_classification"]))
    metrics[4].metric("Freshness", str(detail_row["freshness_status"]))

    chart_col, component_col = st.columns([1.6, 1])
    with chart_col:
        history = state["market"][state["market"]["symbol"] == selected_asset].sort_values("observation_ts")
        fig = go.Figure(go.Scatter(x=history["observation_ts"], y=history["adjusted_close"], mode="lines", name=selected_asset))
        fig.update_layout(title=f"{selected_asset} adjusted close", height=360, yaxis_title="Price")
        st.plotly_chart(fig, use_container_width=True)
    with component_col:
        components = pd.DataFrame(json.loads(detail_row.get("score_components") or "[]"))
        if not components.empty:
            fig = go.Figure(go.Bar(x=components["normalized_contribution"], y=components["component"], orientation="h"))
            fig.update_layout(title="Score contributions", height=360, xaxis_title="Points")
            st.plotly_chart(fig, use_container_width=True)

    if not components.empty:
        explanation = components.rename(
            columns={
                "component": "Component",
                "raw_score": "Normalized score",
                "base_weight": "Base weight",
                "effective_weight": "Redistributed weight",
                "normalized_contribution": "Score contribution",
            }
        )
        st.dataframe(explanation, use_container_width=True, hide_index=True)
    missing = json.loads(detail_row.get("missing_components") or "[]")
    st.caption(f"Missing components: {', '.join(missing) if missing else 'None'}. Available weights are redistributed proportionally and shown above.")
    with st.expander("Methodology and interpretation"):
        st.markdown(
            "The score combines trend/momentum (30%), price-volume confirmation (20%), volatility (20%), liquidity (15%), and mapped CFTC positioning (15%). "
            "A missing component is excluded rather than set to zero. The remaining weights are normalized to 100%, and confidence falls with coverage."
        )
