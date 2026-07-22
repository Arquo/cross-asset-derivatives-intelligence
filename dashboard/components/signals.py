"""Signal display helpers."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def render_signal_table(frame: pd.DataFrame) -> None:
    """Render a signal table with readable list columns."""

    if frame.empty:
        st.info("No signals have been built yet.")
        return
    display = frame.copy()
    for column in ["evidence_record_ids", "assumptions", "failure_cases", "contradicting_signal_ids"]:
        if column in display.columns:
            display[column] = display[column].apply(lambda value: ", ".join(value) if isinstance(value, list) else value)
    if "raw_value" in display.columns:
        display["raw_value"] = display["raw_value"].apply(lambda value: "" if value is None else str(value))
    st.dataframe(display, use_container_width=True, hide_index=True)
