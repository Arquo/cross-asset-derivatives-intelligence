"""Freshness-related helpers."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.components.cards import render_status_badge


def format_utc_timestamp(timestamp, *, date_only: bool = False) -> str:
    value = pd.to_datetime(timestamp, utc=True, errors="coerce")
    if pd.isna(value):
        return "Unavailable"
    return value.strftime("%Y-%m-%d" if date_only else "%Y-%m-%d %H:%M UTC")


def render_last_updated_label(timestamp) -> None:
    if timestamp is None or pd.isna(timestamp):
        st.caption("Last updated: not available")
    else:
        st.caption(f"Last updated: {format_utc_timestamp(timestamp)}")


def render_freshness_badge(label: str) -> None:
    render_status_badge(label)
