"""Evidence display helpers."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def render_evidence_table(frame: pd.DataFrame) -> None:
    """Render a compact evidence table."""

    if frame.empty:
        st.info("No evidence records are available yet.")
        return
    display = frame.copy()
    for column in ["observation_timestamps", "availability_timestamps", "record_ids"]:
        if column in display.columns:
            display[column] = display[column].apply(lambda value: ", ".join(value) if isinstance(value, list) else value)
    st.dataframe(display, use_container_width=True, hide_index=True)

