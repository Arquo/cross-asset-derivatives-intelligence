"""Macro snapshot page."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.cards import render_metric_cards
from dashboard.components.layout import render_empty_state, render_page_header, render_section_heading, render_warning_panel


def _latest(frame: pd.DataFrame, series_id: str) -> pd.Series | None:
    if frame.empty:
        return None
    subset = frame[frame["series_id"] == series_id]
    if subset.empty:
        return None
    return subset.sort_values("observation_ts").iloc[-1]


def render(*, macro_latest: pd.DataFrame, macro_history: dict[str, pd.DataFrame], database_command: str) -> None:
    render_page_header(
        "Macro Snapshot",
        "End-of-day FRED macro and rates monitoring.",
        badges=["Macro", "Phase 2"],
    )
    st.caption("Different macro series have different release frequencies, so the latest date can vary by indicator.")

    if macro_latest.empty:
        render_empty_state("No macro data available yet", "Run the ingestion command to populate FRED observations.", database_command)
        return

    latest_map = {row["series_id"]: row for _, row in macro_latest.iterrows()}

    metric_pairs = [
        ("DFF", "Effective fed-funds rate"),
        ("DGS2", "2-year Treasury yield"),
        ("DGS10", "10-year Treasury yield"),
        ("T10Y2Y", "10Y minus 2Y spread"),
        ("DFII10", "10-year real yield"),
        ("T10YIE", "10-year breakeven inflation"),
        ("CPIAUCSL", "CPI"),
        ("CPILFESL", "Core CPI"),
    ]
    metrics = []
    for series_id, label in metric_pairs:
        row = latest_map.get(series_id)
        metrics.append({"label": label, "value": "Not available" if row is None or pd.isna(row.get("latest_value")) else f"{row.get('latest_value'):,.2f}"})
    render_metric_cards(metrics)

    render_section_heading("Rates", "Latest values and recent line charts.")
    col1, col2 = st.columns(2)
    with col1:
        rates = [("DFF", "Fed funds"), ("DGS2", "2Y"), ("DGS10", "10Y"), ("T10Y2Y", "10Y-2Y"), ("DFII10", "Real 10Y"), ("T10YIE", "Breakeven")]
        fig = go.Figure()
        for series_id, label in rates:
            frame = macro_history.get(series_id, pd.DataFrame())
            if frame.empty:
                continue
            fig.add_trace(go.Scatter(x=frame["observation_ts"], y=frame["value"], mode="lines", name=label))
        if fig.data:
            fig.update_layout(title="Rates and curve series", xaxis_title="Date", yaxis_title="Value", height=360)
            st.plotly_chart(fig, use_container_width=True)
        else:
            render_empty_state("Rates chart", "No stored rate history yet.")
    with col2:
        table = macro_latest[macro_latest["series_id"].isin(["DFF", "DGS2", "DGS10", "T10Y2Y", "DFII10", "T10YIE"])].copy()
        if table.empty:
            render_empty_state("Latest rates table", "No rate rows available.")
        else:
            st.dataframe(table[["series_id", "series_name", "latest_value", "latest_observation_date", "frequency"]], use_container_width=True, hide_index=True)

    render_section_heading("Inflation", "CPI, core CPI, and breakeven inflation.")
    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure()
        for series_id, label in [("CPIAUCSL", "CPI"), ("CPILFESL", "Core CPI"), ("T10YIE", "Breakeven")]:
            frame = macro_history.get(series_id, pd.DataFrame())
            if frame.empty:
                continue
            fig.add_trace(go.Scatter(x=frame["observation_ts"], y=frame["value"], mode="lines", name=label))
        if fig.data:
            fig.update_layout(title="Inflation inputs", xaxis_title="Date", yaxis_title="Value", height=360)
            st.plotly_chart(fig, use_container_width=True)
        else:
            render_empty_state("Inflation chart", "No stored inflation data yet.")
    with col2:
        table = macro_latest[macro_latest["series_id"].isin(["CPIAUCSL", "CPILFESL", "T10YIE"])].copy()
        if table.empty:
            render_empty_state("Latest inflation table", "No inflation rows available.")
        else:
            st.dataframe(table[["series_id", "series_name", "latest_value", "latest_observation_date", "frequency"]], use_container_width=True, hide_index=True)

    render_section_heading("Labour", "Unemployment and claims.")
    col1, col2 = st.columns(2)
    with col1:
        frame = macro_history.get("UNRATE", pd.DataFrame())
        if frame.empty:
            render_empty_state("Labour chart", "No unemployment data stored yet.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=frame["observation_ts"], y=frame["value"], mode="lines", name="Unemployment"))
            fig.update_layout(title="Unemployment rate", xaxis_title="Date", yaxis_title="Percent", height=360)
            st.plotly_chart(fig, use_container_width=True)
    with col2:
        frame = macro_history.get("ICSA", pd.DataFrame())
        if frame.empty:
            render_empty_state("Initial claims", "No claims data stored yet.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=frame["observation_ts"], y=frame["value"], mode="lines", name="Initial claims"))
            fig.update_layout(title="Initial jobless claims", xaxis_title="Date", yaxis_title="Claims", height=360)
            st.plotly_chart(fig, use_container_width=True)

    render_section_heading("Liquidity inputs", "Federal Reserve balance-sheet proxies.")
    col1, col2 = st.columns(2)
    with col1:
        fig = go.Figure()
        for series_id, label in [("WALCL", "Fed assets"), ("RRPONTSYD", "Reverse repo"), ("WTREGEN", "TGA")]:
            frame = macro_history.get(series_id, pd.DataFrame())
            if frame.empty:
                continue
            fig.add_trace(go.Scatter(x=frame["observation_ts"], y=frame["value"], mode="lines", name=label))
        if fig.data:
            fig.update_layout(title="Liquidity inputs", xaxis_title="Date", yaxis_title="Value", height=360)
            st.plotly_chart(fig, use_container_width=True)
        else:
            render_empty_state("Liquidity chart", "No liquidity observations stored yet.")
    with col2:
        table = macro_latest[macro_latest["series_id"].isin(["WALCL", "RRPONTSYD", "WTREGEN"])]
        if table.empty:
            render_empty_state("Latest liquidity table", "No liquidity rows available.")
        else:
            st.dataframe(table[["series_id", "series_name", "latest_value", "latest_observation_date", "frequency"]], use_container_width=True, hide_index=True)

