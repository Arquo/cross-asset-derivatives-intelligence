"""Macro Regime page."""

from __future__ import annotations

from pathlib import Path
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.cards import render_metric_cards
from dashboard.components.layout import render_empty_state, render_page_header, render_section_heading, render_warning_panel
from dashboard.components.regime import render_regime_cards
from dashboard.components.signals import render_signal_table
from cross_asset_intelligence.services.analytics_service import AnalyticsService


DATABASE_PATH = Path(os.getenv("CROSS_ASSET_DATABASE_PATH", "data/database/cross_asset.duckdb"))


@st.cache_data(ttl=600, show_spinner=False)
def load_snapshot(database_path: str) -> dict[str, object]:
    service = AnalyticsService(Path(database_path))
    snapshot = service.build_snapshot()
    macro = service.latest_macro_regime()
    return {"snapshot": snapshot, "macro": macro}


def render() -> None:
    render_page_header("Macro Regime", "Deterministic macro, rates, inflation, labour, and liquidity context.", badges=["FRED", "Deterministic"])
    st.caption("FRED observations are delayed and current history is not vintage-safe. Observation dates are shown separately from retrieval time.")
    state = load_snapshot(str(DATABASE_PATH))
    snapshot = state["snapshot"]
    macro = state["macro"]
    packet = snapshot.packet
    if packet is None or not macro:
        render_empty_state("No macro analytics available", "Run the FRED ingestion and deterministic analytics commands.", "python scripts/ingest_data.py --provider fred")
        return

    result = macro["result"]
    render_metric_cards(
        [
            {"label": "Overall macro regime", "value": result.overall_macro_regime},
            {"label": "Confidence", "value": packet.overall_confidence.value.title()},
            {"label": "As-of", "value": packet.as_of_timestamp[:19].replace("T", " ")},
            {"label": "Data cutoff", "value": packet.data_cutoff_timestamp[:19].replace("T", " ")},
        ]
    )
    render_regime_cards(
        [
            {"label": "Inflation", "value": result.inflation_regime},
            {"label": "Labour", "value": result.labour_regime},
            {"label": "Policy", "value": result.policy_regime},
            {"label": "Yield curve", "value": result.yield_curve_regime},
        ]
    )

    render_section_heading("Macro charts", "Stored FRED observations, not live data.")
    col1, col2 = st.columns(2)
    with col1:
        if result.treasury_yield_data.empty:
            render_empty_state("Treasury yields", "No stored yield data.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=result.treasury_yield_data["date"], y=result.treasury_yield_data["10Y"], name="10Y"))
            fig.add_trace(go.Scatter(x=result.treasury_yield_data["date"], y=result.treasury_yield_data["2Y"], name="2Y"))
            fig.update_layout(height=320, title="Treasury yields", yaxis_title="Percent")
            st.plotly_chart(fig, use_container_width=True)
    with col2:
        if result.yield_curve_chart_data.empty:
            render_empty_state("Yield curve", "No stored spread data.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=result.yield_curve_chart_data["date"], y=result.yield_curve_chart_data["spread"], name="10Y-2Y Spread"))
            fig.update_layout(height=320, title="Yield-curve spread", yaxis_title="Percentage points")
            st.plotly_chart(fig, use_container_width=True)

    render_section_heading("Evidence table", "Latest indicators with their observation dates.")
    st.dataframe(result.series_table, use_container_width=True, hide_index=True)

    render_section_heading("Signals", "Transparent signal records that support the macro summary.")
    render_signal_table(snapshot.signals)
    if snapshot.evidence.empty:
        render_warning_panel("No evidence records are available yet.")
    else:
        st.dataframe(snapshot.evidence, use_container_width=True, hide_index=True)
