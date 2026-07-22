"""Cross-Asset page."""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from dashboard.components.layout import render_empty_state, render_page_header, render_section_heading
from cross_asset_intelligence.services.analytics_service import AnalyticsService


DATABASE_PATH = Path("data/database/cross_asset.duckdb")


@st.cache_data(ttl=21600, show_spinner=False)
def load_cross_asset(database_path: str) -> dict[str, object]:
    service = AnalyticsService(Path(database_path))
    snapshot = service.build_snapshot()
    return {"cross_asset": snapshot.cross_asset, "signals": snapshot.signals}


def render() -> None:
    render_page_header("Cross-Asset", "Deterministic relationships across equities, rates, credit, and volatility.", badges=["Phase 3"])
    st.caption("Correlation does not prove causation. Relationships can weaken, invert, or become unreliable.")
    state = load_cross_asset(str(DATABASE_PATH))
    frame = state["cross_asset"]
    if frame.empty:
        render_empty_state("No cross-asset data yet", "Run the analytics pipeline after storing enough market history.")
        return
    st.dataframe(frame, use_container_width=True, hide_index=True)
    render_section_heading("Rolling relationships", "Current 20-day and 60-day proxy relationships.")
    if "observation_ts" in frame.columns:
        fig = go.Figure()
        for column in ["corr_20d", "corr_60d", "beta_60d", "spread_zscore"]:
            if column in frame.columns:
                fig.add_trace(go.Scatter(x=frame["observation_ts"], y=frame[column], name=column, mode="lines"))
        fig.update_layout(height=340, title="Cross-asset relationships")
        st.plotly_chart(fig, use_container_width=True)
    if not state["signals"].empty:
        st.dataframe(state["signals"], use_container_width=True, hide_index=True)

