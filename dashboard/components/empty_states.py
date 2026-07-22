"""Actionable empty states for required datasets and analytics."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.layout import render_empty_state


def render_pipeline_empty_state(
    *,
    title: str,
    dataset: str,
    command: str,
    latest_attempt: pd.DataFrame | None = None,
) -> None:
    """Explain what is absent, the latest attempt, and the corrective command."""

    render_empty_state(title, f"Missing dataset: {dataset}", command)
    if latest_attempt is None or latest_attempt.empty:
        st.caption("Last attempted pipeline run: no recorded attempt.")
        st.caption("Failure reason: no pipeline result is available.")
        return
    row = latest_attempt.iloc[0]
    attempted_at = pd.to_datetime(row.get("completed_at", row.get("started_at")), utc=True, errors="coerce")
    attempted_label = attempted_at.strftime("%Y-%m-%d %H:%M UTC") if pd.notna(attempted_at) else "timestamp unavailable"
    st.caption(f"Last attempted pipeline run: {attempted_label} ({row.get('status', 'unknown')}).")
    st.caption(f"Failure reason: {row.get('error_message') or 'the run completed but produced no usable rows.'}")
