"""Data freshness page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.cards import render_status_badge
from dashboard.components.layout import render_empty_state, render_page_header, render_section_heading


def render(*, freshness_summary: pd.DataFrame, pipeline_runs: pd.DataFrame, overall_health: dict, refresh_command: str) -> None:
    render_page_header("Data Freshness", "Control panel for observation age, pipeline runs, and quality status.", badges=["Freshness", "Phase 2"])

    if st.button("Refresh dashboard data"):
        st.cache_data.clear()
        st.rerun()

    render_section_heading("Overall health", "A quick view of dataset freshness and pipeline state.")
    render_status_badge(overall_health.get("status", "Missing"))
    st.write(f"Current datasets: {overall_health.get('current', 0)}")
    st.write(f"Delayed datasets: {overall_health.get('delayed', 0)}")
    st.write(f"Stale datasets: {overall_health.get('stale', 0)}")
    st.write(f"Missing datasets: {overall_health.get('missing', 0)}")
    st.write(f"Failed datasets: {overall_health.get('failed', 0)}")

    if freshness_summary.empty:
        render_empty_state("No dataset status rows", "Initialize the database and ingest data to populate freshness metrics.", refresh_command)
        return

    render_section_heading("Dataset freshness summary", "Observation and ingestion times are shown separately.")
    display = freshness_summary.copy()
    for column in ["latest_observation_ts", "latest_ingestion_ts", "last_successful_ingestion"]:
        if column in display.columns:
            display[column] = pd.to_datetime(display[column], utc=True, errors="coerce").dt.strftime("%Y-%m-%d %H:%M UTC")
    st.dataframe(
        display[
            [
                col
                for col in [
                    "dataset_name",
                    "dataset_id",
                    "provider",
                    "frequency",
                    "latest_observation_ts",
                    "latest_ingestion_ts",
                    "age_days",
                    "freshness_status",
                    "quality_status",
                    "record_count",
                    "latest_pipeline_status",
                    "warning_message",
                ]
                if col in display.columns
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    render_section_heading("Pipeline runs", "Expandable details for recent runs.")
    if pipeline_runs.empty:
        render_empty_state("No pipeline runs", "Run the ingestion script to create pipeline metadata.", refresh_command)
    else:
        for _, row in pipeline_runs.head(10).iterrows():
            with st.expander(f"{row.get('provider', 'provider')} - {row.get('status', 'unknown')} - {pd.Timestamp(row.get('started_at')).strftime('%Y-%m-%d %H:%M UTC') if pd.notna(row.get('started_at')) else 'N/A'}"):
                st.write(row.to_dict())

