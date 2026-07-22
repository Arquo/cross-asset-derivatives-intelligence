from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from cross_asset_intelligence.services.data_status_service import DataStatusService


DATABASE_PATH = Path("data/processed/cross_asset_intelligence.duckdb")


st.set_page_config(
    page_title="Cross-Asset Derivatives Intelligence Platform",
    page_icon="CA",
    layout="wide",
)

MODULES = [
    ("Macro", "Macro regime, inflation, labor, and rates context."),
    ("Positioning", "Futures and positioning evidence when the data layer arrives."),
    ("Options", "Volatility, skew, and options structure analysis."),
    ("Market Structure", "Liquidity, trend, and structure proxies."),
    ("Liquidity", "Flow, depth, and stress indicators."),
    ("Cross-Asset", "Relationships across rates, FX, equities, credit, and commodities."),
]


def _card(title: str, description: str) -> str:
    return f"""
    <div class="module-card">
        <h3>{title}</h3>
        <p>{description}</p>
    </div>
    """


def _fmt_dt(value):
    if value is None or pd.isna(value):
        return "N/A"
    return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M UTC")


st.markdown(
    """
    <style>
    .hero {
        padding: 1.75rem 0 0.75rem 0;
    }
    .hero h1 {
        font-size: 2.7rem;
        margin-bottom: 0.4rem;
    }
    .hero p {
        color: #cbd5e1;
        font-size: 1.05rem;
        max-width: 980px;
    }
    .phase-pill {
        display: inline-block;
        padding: 0.35rem 0.8rem;
        border-radius: 999px;
        background: #1f2937;
        color: white;
        font-weight: 600;
        margin-bottom: 0.5rem;
    }
    .module-card {
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 1rem 1.05rem;
        background: #111827;
        box-shadow: 0 2px 10px rgba(15, 23, 42, 0.2);
        min-height: 122px;
    }
    .module-card h3 {
        margin-bottom: 0.35rem;
        font-size: 1.08rem;
        color: #e2e8f0;
    }
    .module-card p {
        margin: 0;
        color: #94a3b8;
        font-size: 0.95rem;
    }
    .status-note {
        padding: 0.9rem 1rem;
        border-radius: 14px;
        background: rgba(59, 130, 246, 0.12);
        color: #bfdbfe;
        border: 1px solid rgba(59, 130, 246, 0.24);
    }
    div.stButton > button {
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
        color: white;
        border: 1px solid rgba(147, 197, 253, 0.35);
        border-radius: 999px;
        padding: 0.6rem 1rem;
        font-weight: 700;
    }
    div.stButton > button:hover {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        border-color: rgba(191, 219, 254, 0.55);
        color: white;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <div class="phase-pill">Phase 1 - Foundation</div>
        <h1>Cross-Asset Derivatives Intelligence Platform</h1>
        <p>
            A research and market-monitoring workspace for combining macro data, positioning,
            options, liquidity, and cross-asset evidence into transparent market views.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.info("Market data is not connected yet. This phase focuses on repository foundation, contracts, docs, and CI.")

if "show_market_analysis" not in st.session_state:
    st.session_state.show_market_analysis = False

if st.button("Analyze Today's Market"):
    st.session_state.show_market_analysis = True

if st.session_state.show_market_analysis:
    st.write("")
    st.info("Market analysis modules are not connected yet.")

st.subheader("Planned Modules")
for start in range(0, len(MODULES), 3):
    cols = st.columns(3)
    for col, (title, description) in zip(cols, MODULES[start : start + 3]):
        with col:
            st.markdown(_card(title, description), unsafe_allow_html=True)

with st.expander("Project methodology"):
    st.markdown(
        """
        - Start with data freshness, observation timestamps, and clear quality flags.
        - Normalize every provider into shared observation and report schemas.
        - Keep deterministic analytics separate from the Streamlit interface.
        - Build evidence packs that include supporting and contradicting signals.
        - Preserve the boundary between validated data and any future AI summary layer.
        - Surface missing data and limitations instead of hiding them.
        """
    )

st.write("")
st.header("Data Status")
st.markdown(
    "<div class='status-note'>Data shown in this phase is historical or delayed and should not be treated as a real-time trading feed.</div>",
    unsafe_allow_html=True,
)

service = DataStatusService(DATABASE_PATH)

if not service.has_database():
    st.warning("No local DuckDB database was found yet.")
    st.code(r"python -m cross_asset_intelligence.pipelines.run_free_data --start 2015-01-01 --provider all")
    st.stop()

summary = service.get_summary()
latest_run = service.latest_pipeline_run()
dataset_status = service.latest_dataset_status()
rows_by_dataset = service.rows_by_dataset()
fred_table = service.fred_latest_table()
market_table = service.market_latest_table()
charts = service.chart_data()

cols = st.columns(4)
with cols[0]:
    st.metric("Latest pipeline status", "N/A" if latest_run.empty else latest_run.iloc[0]["status"])
with cols[1]:
    last_success = pd.NaT
    if not latest_run.empty and latest_run.iloc[0]["status"] in {"success", "partial_success"}:
        last_success = latest_run.iloc[0]["completed_at"]
    st.metric("Last successful ingestion", _fmt_dt(last_success))
with cols[2]:
    st.metric("Rows stored", int(rows_by_dataset["rows_stored"].sum()) if not rows_by_dataset.empty else 0)
with cols[3]:
    if summary.quality_events.empty:
        warnings = rejects = 0
    else:
        warnings = int((summary.quality_events["severity"] == "warning").sum())
        rejects = int((summary.quality_events["severity"].isin(["error", "critical"])).sum())
    st.metric("Warnings / rejects", f"{warnings} / {rejects}")

st.subheader("Provider Status")
if dataset_status.empty:
    st.info("No dataset catalog rows available yet.")
else:
    st.dataframe(
        dataset_status.assign(
            last_successful_ingestion=dataset_status["last_successful_ingestion"].apply(_fmt_dt),
            latest_observation_ts=dataset_status["latest_observation_ts"].apply(_fmt_dt),
        ),
        use_container_width=True,
        hide_index=True,
    )

st.subheader("Rows by Dataset")
st.dataframe(rows_by_dataset, use_container_width=True, hide_index=True)

col1, col2 = st.columns(2)
with col1:
    st.subheader("FRED Series")
    if fred_table.empty:
        st.info("No FRED rows stored yet.")
    else:
        st.dataframe(
            fred_table.assign(
                latest_observation_date=fred_table["latest_observation_date"].apply(_fmt_dt),
                ingestion_date=fred_table["ingestion_date"].apply(_fmt_dt),
            ),
            use_container_width=True,
            hide_index=True,
        )
with col2:
    st.subheader("Market Prices")
    if market_table.empty:
        st.info("No market rows stored yet.")
    else:
        st.dataframe(
            market_table.assign(
                latest_trading_date=market_table["latest_trading_date"].apply(_fmt_dt),
                ingestion_date=market_table["ingestion_date"].apply(_fmt_dt),
            ),
            use_container_width=True,
            hide_index=True,
        )

st.subheader("Raw Data Charts")
chart_col1, chart_col2 = st.columns(2)
with chart_col1:
    if charts.get("spy_qqq", pd.DataFrame()).empty:
        st.info("No SPY/QQQ chart data yet.")
    else:
        fig = go.Figure()
        for symbol in ["SPY", "QQQ"]:
            subset = charts["spy_qqq"][charts["spy_qqq"]["symbol"] == symbol]
            fig.add_trace(go.Scatter(x=subset["observation_ts"], y=subset["adjusted_close"], mode="lines", name=symbol))
        fig.update_layout(title="SPY and QQQ Adjusted Close", height=350, xaxis_title="Date", yaxis_title="Adjusted Close")
        st.plotly_chart(fig, use_container_width=True)
with chart_col2:
    if charts.get("yields", pd.DataFrame()).empty:
        st.info("No Treasury yield data yet.")
    else:
        fig = go.Figure()
        for series_id, label in [("DGS2", "2Y"), ("DGS10", "10Y")]:
            subset = charts["yields"][charts["yields"]["series_id"] == series_id]
            fig.add_trace(go.Scatter(x=subset["observation_ts"], y=subset["value"], mode="lines", name=label))
        fig.update_layout(title="2Y and 10Y Treasury Yields", height=350, xaxis_title="Date", yaxis_title="Yield")
        st.plotly_chart(fig, use_container_width=True)

chart_col1, chart_col2 = st.columns(2)
with chart_col1:
    credit = charts.get("credit", pd.DataFrame())
    if credit.empty:
        st.info("No high-yield spread data yet.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=credit["observation_ts"], y=credit["value"], mode="lines", name="High Yield OAS"))
        fig.update_layout(title="High-Yield Spread", height=350, xaxis_title="Date", yaxis_title="Spread")
        st.plotly_chart(fig, use_container_width=True)
with chart_col2:
    liquidity = charts.get("liquidity", pd.DataFrame())
    if liquidity.empty:
        st.info("No liquidity series data yet.")
    else:
        fig = go.Figure()
        for series_id in ["WALCL", "WTREGEN", "RRPONTSYD", "WRESBAL"]:
            subset = liquidity[liquidity["series_id"] == series_id]
            fig.add_trace(go.Scatter(x=subset["observation_ts"], y=subset["value"], mode="lines", name=series_id))
        fig.update_layout(title="Liquidity Proxies", height=350, xaxis_title="Date", yaxis_title="Value")
        st.plotly_chart(fig, use_container_width=True)
