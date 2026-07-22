from __future__ import annotations

from pathlib import Path
import os

import pandas as pd
import streamlit as st

from dashboard.components.styles import inject_dashboard_styles
from dashboard.pages.data_freshness import render as render_data_freshness
from dashboard.pages.liquidity import render as render_liquidity
from dashboard.pages.macro_regime import render as render_macro_regime
from dashboard.pages.market_overview import render as render_market_overview
from dashboard.pages.market_summary import render as render_market_summary
from dashboard.pages.positioning import render as render_positioning
from dashboard.pages.methodology import render as render_methodology
from dashboard.pages.options import render as render_options
from dashboard.pages.screener import render as render_screener
from cross_asset_intelligence.core.config import load_pipeline_config
from cross_asset_intelligence.services.data_status_service import DataStatusService
from cross_asset_intelligence.services.market_data_service import MarketDataService
from cross_asset_intelligence.services.intelligence_service import MarketIntelligenceService


DATABASE_PATH = Path(os.getenv("CROSS_ASSET_DATABASE_PATH", "data/database/cross_asset.duckdb"))
INGEST_COMMAND = "python scripts/ingest_data.py --provider all"
INIT_COMMAND = "python scripts/initialize_database.py"


st.set_page_config(
    page_title="Cross-Asset Derivatives Intelligence Platform",
    page_icon="CA",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_dashboard_styles()


@st.cache_data(ttl=3600, show_spinner=False)
def load_configuration() -> dict[str, object]:
    config = load_pipeline_config(Path.cwd())
    return {
        "fred_series": [item.series_id for item in config.fred_series if item.enabled],
        "market_symbols": [item.internal_symbol for item in config.market_symbols if item.enabled],
    }


@st.cache_data(ttl=600, show_spinner=False)
def load_dashboard_state(database_path: str) -> dict[str, object]:
    path = Path(database_path)
    status_service = DataStatusService(path)
    market_service = MarketDataService(path)
    summary = status_service.get_summary()
    config = load_configuration()
    market_symbols = config["market_symbols"]
    fred_series = config["fred_series"]
    market_history = market_service.recent_market_history(market_symbols, limit=2000)
    macro_history_frame = market_service.recent_macro_history(fred_series, limit=4000)
    macro_history = {series_id: frame.reset_index(drop=True) for series_id, frame in macro_history_frame.groupby("series_id")} if not macro_history_frame.empty else {}
    yield_history = summary.macro_observations[summary.macro_observations["series_id"].isin(["DGS2", "DGS10", "T10Y2Y"])].copy() if not summary.macro_observations.empty else pd.DataFrame()
    latest_success = pd.NaT
    if not summary.pipeline_runs.empty:
        completed = summary.pipeline_runs[summary.pipeline_runs["status"].isin(["completed", "completed_with_warnings", "success", "partial_success"])].copy()
        if not completed.empty:
            latest_success = pd.to_datetime(completed.iloc[0]["completed_at"], utc=True, errors="coerce")
    return {
        "summary": summary,
        "latest_market": status_service.market_latest_table(),
        "latest_macro": status_service.fred_latest_table(),
        "market_history": market_history,
        "macro_history": macro_history,
        "yield_history": yield_history,
        "vix_history": market_service.recent_market_history(["VIX"], limit=252),
        "latest_refresh": latest_success,
        "has_database": status_service.has_database(),
    }


def _render_home(state: dict[str, object]) -> None:
    render_market_overview(
        latest_market=state["latest_market"],
        latest_macro=state["latest_macro"],
        market_history=state["market_history"],
        yield_history=state["yield_history"],
        vix_history=state["vix_history"],
        database_command=INGEST_COMMAND,
        latest_refresh_timestamp=state["latest_refresh"],
        overall_health=state["summary"].overall_health,
    )


def _render_freshness(state: dict[str, object]) -> None:
    render_data_freshness(
        freshness_summary=state["summary"].freshness_summary,
        pipeline_runs=state["summary"].pipeline_runs,
        overall_health=state["summary"].overall_health,
        refresh_command=INGEST_COMMAND,
    )


def _render_methodology(state: dict[str, object]) -> None:
    render_methodology()


PAGES = {
    "Market Overview": _render_home,
    "Macro Regime": lambda _state: render_macro_regime(),
    "Positioning": lambda _state: render_positioning(),
    "Liquidity & Market-Structure Proxies": lambda _state: render_liquidity(),
    "Cross-Asset Screener": lambda _state: render_screener(),
    "SPY & QQQ Options": lambda _state: render_options(),
    "Evidence-Based Market Summary": lambda _state: render_market_summary(),
    "Data Freshness": _render_freshness,
    "Methodology": _render_methodology,
}


st.sidebar.title("Navigation")
selected_page = st.sidebar.radio("Go to", list(PAGES.keys()), index=0)
if st.sidebar.button("Analyze Today's Market", help="Recalculate analytics from observations already stored in DuckDB."):
    try:
        with st.spinner("Calculating and storing deterministic analytics..."):
            MarketIntelligenceService(DATABASE_PATH).run()
        st.cache_data.clear()
        st.sidebar.success("Stored analytics updated.")
        st.rerun()
    except Exception as exc:
        st.sidebar.error(f"Analytics failed: {exc}")
        st.sidebar.code("python scripts/run_analytics.py")
st.sidebar.caption("Data retrieval remains explicit through the ingestion commands; this button only analyzes stored observations.")

state = load_dashboard_state(str(DATABASE_PATH))

if not state["has_database"]:
    st.warning("No local DuckDB database has been initialized yet.")
    st.code(INIT_COMMAND)

PAGES[selected_page](state)
