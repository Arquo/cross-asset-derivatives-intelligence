"""Methodology page."""

from __future__ import annotations

import streamlit as st

from dashboard.components.layout import render_page_header, render_section_heading


def render() -> None:
    render_page_header("Methodology", "How the platform separates raw inputs, validated data, and dashboard output.", badges=["Methodology"])

    render_section_heading("Data architecture")
    st.markdown(
        """
        - Providers fetch source-specific payloads.
        - Raw snapshots are stored immutably as Parquet.
        - Validation determines which records are safe to store in DuckDB.
        - Dashboard pages read from services, not from provider APIs.
        """,
    )

    render_section_heading("Observation time vs availability time")
    st.markdown(
        """
        - `observation_ts` is the economic or market time represented by the record.
        - `available_ts` is the earliest time the platform could have known the record.
        - `ingested_ts` is the time the platform retrieved or stored it.
        """,
    )

    render_section_heading("Raw vs validated data")
    st.markdown(
        """
        - Raw snapshots preserve provider responses for auditability.
        - Validated tables contain the records used by the dashboard.
        - Validation warnings and rejections remain inspectable in `data_quality_events`.
        """,
    )

    render_section_heading("Provider limitations")
    st.markdown(
        """
        - FRED release schedules differ by series.
        - yfinance is a replaceable research-grade vendor source, not an institutional feed.
        - The product is designed for end-of-day or delayed research, not real-time trading.
        """,
    )

    render_section_heading("Planned future modules")
    st.markdown(
        """
        - Positioning
        - Options
        - Market Structure
        - Liquidity
        - Cross-Asset
        - AI Strategist
        """,
    )
