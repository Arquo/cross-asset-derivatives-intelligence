from __future__ import annotations

import os

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from dotenv import load_dotenv

from src.analytics.macro_regime import SERIES_IDS, build_macro_regime_result, build_series_snapshot


load_dotenv()


st.set_page_config(
    page_title="Cross-Asset Derivatives Intelligence Platform",
    page_icon="📈",
    layout="wide",
)


def format_value(value: float | None, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:,.2f}{suffix}"


def format_timestamp(value: pd.Timestamp | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    if getattr(value, "tzinfo", None) is not None:
        value = value.tz_convert(None)
    return value.strftime("%Y-%m-%d")


def format_datetime(value: pd.Timestamp | None) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    if getattr(value, "tzinfo", None) is not None:
        value = value.tz_convert(None)
    return value.strftime("%Y-%m-%d %H:%M UTC")


def macro_regime_badge(label: str) -> str:
    color = {
        "Goldilocks": "#166534",
        "Reflation": "#92400e",
        "Disinflationary slowdown": "#1d4ed8",
        "Stagflation risk": "#b91c1c",
        "Mixed / transitioning": "#4b5563",
        "Insufficient data": "#6b7280",
    }.get(label, "#4b5563")
    return f"<span style='display:inline-block;padding:0.35rem 0.8rem;border-radius:999px;background:{color};color:white;font-weight:600'>{label}</span>"


def latest_series_value(series_id: str):
    match = macro_result.series_table.loc[macro_result.series_table["FRED series ID"] == series_id, "Latest value"]
    if match.empty:
        return None
    return match.iloc[0]


@st.cache_data(ttl=21600, show_spinner="Loading FRED macro series...")
def load_macro_data(api_key: str):
    with requests.Session() as session:
        snapshots = {
            series_id: build_series_snapshot(series_id, api_key, session=session)
            for series_id in SERIES_IDS
        }
    return build_macro_regime_result(snapshots)


st.markdown(
    """
    <style>
    .hero {
        padding: 1.5rem 0 0.5rem 0;
    }
    .hero h1 {
        font-size: 2.6rem;
        margin-bottom: 0.35rem;
    }
    .hero p {
        color: #4b5563;
        font-size: 1.05rem;
        max-width: 980px;
    }
    .section-card {
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 1rem 1.1rem;
        background: white;
        box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
    }
    .module-chip {
        display: inline-block;
        padding: 0.35rem 0.7rem;
        border-radius: 999px;
        background: #eef2ff;
        color: #3730a3;
        font-size: 0.82rem;
        font-weight: 600;
        margin-right: 0.35rem;
        margin-bottom: 0.35rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <h1>Cross-Asset Derivatives Intelligence Platform</h1>
        <p>
            A focused dashboard for market regime analysis across rates, inflation, labour,
            and the Treasury curve using official FRED data.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

api_key = os.getenv("FRED_API_KEY", "").strip()

if not api_key:
    st.error("FRED_API_KEY is missing. Add it to your local .env file using .env.example as the template.")
    st.stop()

try:
    macro_result = load_macro_data(api_key)
except Exception:
    st.error("Unable to load Macro Regime data from FRED right now. Please check your API key and network connection.")
    st.stop()

retrieved_at = pd.Timestamp.utcnow()

st.markdown(
    f"""
    <div class="section-card">
        <div style="margin-bottom:0.75rem">
            <span class="module-chip">Macro Regime</span>
            <span class="module-chip">Official FRED API</span>
        </div>
        <div>{macro_regime_badge(macro_result.overall_macro_regime)}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.write("")
st.subheader("Regime Labels")
regime_cols = st.columns(5)
regime_cards = [
    ("Overall", macro_result.overall_macro_regime),
    ("Inflation", macro_result.inflation_regime),
    ("Labour", macro_result.labour_regime),
    ("Policy", macro_result.policy_regime),
    ("Yield curve", macro_result.yield_curve_regime),
]
for col, (label, value) in zip(regime_cols, regime_cards):
    with col:
        st.metric(label, value)

st.write("")
info_cols = st.columns(2)
with info_cols[0]:
    st.metric("Latest economic observation date", format_timestamp(macro_result.latest_observation_timestamp))
with info_cols[1]:
    st.metric("Data retrieved at", format_datetime(retrieved_at))

st.write("")
st.subheader("Main Indicators")
metrics = [
    ("Effective Fed Funds Rate", macro_result.indicators["FFR 3m change"], format_value(latest_series_value("DFF"), "%"), "3m change"),
    ("2Y Treasury Yield", macro_result.indicators["2Y change 20d"], format_value(latest_series_value("DGS2"), "%"), "20d change"),
    ("10Y Treasury Yield", macro_result.indicators["10Y change 20d"], format_value(latest_series_value("DGS10"), "%"), "20d change"),
    ("Yield Curve Slope", None, format_value(macro_result.indicators["Latest yield-curve slope"], "%"), "10Y - 2Y"),
    ("10Y Real Yield", macro_result.indicators["10Y real yield change 20d"], format_value(latest_series_value("DFII10"), "%"), "20d change"),
    ("Breakeven Inflation", None, format_value(latest_series_value("T10YIE"), "%"), "latest"),
    ("CPI YoY Inflation", None, format_value(macro_result.indicators["CPI YoY %"], "%"), "year-over-year"),
    ("Unemployment Rate", macro_result.indicators["Unemployment 3m change"], format_value(latest_series_value("UNRATE"), "%"), "3m change"),
]

for idx in range(0, len(metrics), 4):
    row = metrics[idx : idx + 4]
    cols = st.columns(len(row))
    for col, (label, delta, value, delta_label) in zip(cols, row):
        with col:
            st.metric(label, value, delta=None if delta is None else format_value(delta, "%"), help=delta_label)

st.write("")
st.subheader("Macro Regime Charts")
chart_left, chart_right = st.columns(2)

with chart_left:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=macro_result.treasury_yield_data["date"], y=macro_result.treasury_yield_data["2Y"], name="2Y Treasury", mode="lines"))
    fig.add_trace(go.Scatter(x=macro_result.treasury_yield_data["date"], y=macro_result.treasury_yield_data["10Y"], name="10Y Treasury", mode="lines"))
    fig.update_layout(
        title="Treasury Yields",
        xaxis_title="Observation date",
        yaxis_title="Yield (%)",
        margin=dict(l=10, r=10, t=50, b=10),
        legend_title_text="Series",
        height=360,
    )
    st.plotly_chart(fig, use_container_width=True)

with chart_right:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=macro_result.yield_curve_chart_data["date"], y=macro_result.yield_curve_chart_data["spread"], name="10Y - 2Y Spread", mode="lines"))
    fig.update_layout(
        title="Yield Curve Spread",
        xaxis_title="Observation date",
        yaxis_title="Percentage points",
        margin=dict(l=10, r=10, t=50, b=10),
        height=360,
    )
    st.plotly_chart(fig, use_container_width=True)

chart_left, chart_right = st.columns(2)

with chart_left:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=macro_result.inflation_chart_data["date"], y=macro_result.inflation_chart_data["CPI"], name="CPI", mode="lines"))
    fig.update_layout(
        title="Inflation: CPI Level",
        xaxis_title="Observation date",
        yaxis_title="Index",
        margin=dict(l=10, r=10, t=50, b=10),
        height=360,
    )
    st.plotly_chart(fig, use_container_width=True)

with chart_right:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=macro_result.unemployment_chart_data["date"], y=macro_result.unemployment_chart_data["Unemployment rate"], name="Unemployment", mode="lines"))
    fig.update_layout(
        title="Labour Market: Unemployment Rate",
        xaxis_title="Observation date",
        yaxis_title="Percent",
        margin=dict(l=10, r=10, t=50, b=10),
        height=360,
    )
    st.plotly_chart(fig, use_container_width=True)

st.write("")
st.subheader("Series Snapshot")
table = macro_result.series_table.copy()
table["Latest observation date"] = table["Latest observation date"].apply(format_timestamp)
table["Latest value"] = table["Latest value"].apply(lambda value: "N/A" if pd.isna(value) else f"{value:,.2f}")
st.dataframe(table, use_container_width=True, hide_index=True)

st.caption(
    "Economic observation date is the latest FRED data date shown above. Data retrieved at shows when this app last loaded the series."
)
