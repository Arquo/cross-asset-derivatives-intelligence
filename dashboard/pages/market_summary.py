"""Persisted evidence-based deterministic market summary."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.components.empty_states import render_pipeline_empty_state
from dashboard.components.freshness import format_utc_timestamp
from dashboard.components.layout import render_page_header, render_section_heading
from cross_asset_intelligence.services.intelligence_service import MarketIntelligenceService


DATABASE_PATH = Path(os.getenv("CROSS_ASSET_DATABASE_PATH", "data/database/cross_asset.duckdb"))
ANALYTICS_COMMAND = "python scripts/run_analytics.py"


@st.cache_data(ttl=600, show_spinner=False)
def load_summary(database_path: str) -> dict[str, pd.DataFrame]:
    service = MarketIntelligenceService(Path(database_path))
    return {"summary": service.latest_summary(), "analytics_runs": service.latest_runs()}


def render() -> None:
    render_page_header(
        "Evidence-Based Market Summary",
        "Repeatable cross-module conclusions generated from stored calculations without an LLM.",
        badges=["Deterministic", "Evidence retained"],
    )
    state = load_summary(str(DATABASE_PATH))
    if state["summary"].empty:
        render_pipeline_empty_state(
            title="Cross-module analytics have not run",
            dataset="Persisted deterministic market summary",
            command=ANALYTICS_COMMAND,
            latest_attempt=state["analytics_runs"],
        )
        return
    row = state["summary"].iloc[0]
    timestamps = json.loads(row.get("source_timestamps") or "{}")
    st.caption(
        f"Generated: {format_utc_timestamp(row['generated_timestamp'])} | "
        f"Market observation: {timestamps.get('market') or 'Unavailable'} | CFTC report: {timestamps.get('cftc_report') or 'Unavailable'} | "
        f"Options snapshot: {timestamps.get('options') or 'Unavailable'}"
    )
    metrics = st.columns(6)
    metrics[0].metric("Market pressure regime", str(row["overall_market_pressure_regime"]))
    metrics[1].metric("Liquidity", str(row["liquidity_condition"]))
    metrics[2].metric("Volatility", str(row["volatility_condition"]))
    metrics[3].metric("SPY options", str(row["spy_options_condition"]))
    metrics[4].metric("QQQ options", str(row["qqq_options_condition"]))
    metrics[5].metric("Confidence", str(row["confidence"]).title())

    render_section_heading("Today's Market Setup", "Every statement below is connected to a stored calculation.")
    setup = json.loads(row.get("market_setup") or "{}")
    for title in ["Price action", "Liquidity", "Positioning", "Options", "Main confirmation", "Main contradiction", "Main risk"]:
        st.markdown(f"**{title}:** {setup.get(title, 'Unavailable')}")

    support_col, contradict_col = st.columns(2)
    with support_col:
        render_section_heading("Confirming signals")
        supporting = json.loads(row.get("supporting_signals") or "[]")
        st.write(supporting if supporting else ["No strong confirming signal is available."])
    with contradict_col:
        render_section_heading("Contradicting signals")
        contradicting = json.loads(row.get("contradicting_signals") or "[]")
        st.write(contradicting if contradicting else ["No major contradiction is currently flagged."])

    render_section_heading("Main positioning risk")
    st.warning(str(row["major_positioning_risk"]))
    monitor_col, limitation_col = st.columns(2)
    with monitor_col:
        render_section_heading("Five indicators to monitor")
        st.write(json.loads(row.get("indicators_to_monitor") or "[]"))
    with limitation_col:
        render_section_heading("Data limitations")
        limitations = json.loads(row.get("data_limitations") or "[]")
        st.write(limitations if limitations else ["No critical missing input was detected for this summary."])

    with st.expander("How this summary distinguishes market setups"):
        st.markdown(
            "Positive price pressure receives stronger confirmation when liquidity is abundant or normal, volatility is not elevated, and positioning is not extreme. "
            "The same positive trend is treated more cautiously when liquidity tightens, volatility rises, long positioning is crowded, or downside skew becomes expensive. "
            "The summary retains both confirming and contradicting evidence instead of collapsing them into a hidden score."
        )
