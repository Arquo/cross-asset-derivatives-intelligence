"""Freshness-related helpers."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.cards import render_status_badge


def render_last_updated_label(timestamp) -> None:
    if timestamp is None or pd.isna(timestamp):
        st.caption("Last updated: not available")
    else:
        st.caption(f"Last updated: {pd.Timestamp(timestamp).strftime('%Y-%m-%d %H:%M UTC')}")


def render_freshness_badge(label: str) -> None:
    render_status_badge(label)
