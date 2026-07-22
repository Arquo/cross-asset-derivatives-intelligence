"""Official CFTC positioning analytics page."""

from __future__ import annotations

from pathlib import Path
import os

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from dashboard.components.empty_states import render_pipeline_empty_state
from dashboard.components.freshness import format_utc_timestamp
from dashboard.components.layout import render_page_header, render_section_heading
from cross_asset_intelligence.services.intelligence_service import CFTC_MARKET_MAP, MarketIntelligenceService


DATABASE_PATH = Path(os.getenv("CROSS_ASSET_DATABASE_PATH", "data/database/cross_asset.duckdb"))
CFTC_COMMAND = "python scripts/ingest_data.py --provider cftc"
ANALYTICS_COMMAND = "python scripts/run_analytics.py"


@st.cache_data(ttl=600, show_spinner=False)
def load_positioning(database_path: str) -> dict[str, pd.DataFrame]:
    service = MarketIntelligenceService(Path(database_path))
    return {
        "positioning": service.positioning_history(),
        "raw": service.raw_positioning_history(),
        "market": service.market_history(),
        "pipeline_attempt": service.latest_pipeline_attempt("CFTC"),
        "analytics_runs": service.latest_runs(),
    }


def _fmt(value: object, pattern: str = ",.0f") -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return "Unavailable" if pd.isna(numeric) else format(float(numeric), pattern)


def render() -> None:
    render_page_header(
        "CFTC Positioning",
        "Mapped weekly futures positioning, crowding, reversals, and descriptive risk flags.",
        badges=["Official CFTC", "Weekly and delayed"],
    )
    st.warning("CFTC reports describe Tuesday positions and are normally published later in the week. Crowding, liquidation, and squeeze flags are risk conditions, not predictions.")
    state = load_positioning(str(DATABASE_PATH))
    frame = state["positioning"]
    if frame.empty:
        if state["raw"].empty:
            render_pipeline_empty_state(
                title="Mapped CFTC observations are required",
                dataset="Official weekly CFTC positioning records",
                command=CFTC_COMMAND,
                latest_attempt=state["pipeline_attempt"],
            )
        else:
            render_pipeline_empty_state(
                title="Positioning analytics have not been persisted",
                dataset="CFTC changes, percentiles, z-scores, crowding, and risk flags",
                command=ANALYTICS_COMMAND,
                latest_attempt=state["analytics_runs"],
            )
        return

    selector_col, category_col = st.columns(2)
    asset_id = selector_col.selectbox("Contract", sorted(frame["internal_asset_id"].unique()))
    categories = sorted(frame[frame["internal_asset_id"] == asset_id]["participant_category"].unique())
    category = category_col.selectbox("Participant category", categories, index=categories.index("Leveraged funds") if "Leveraged funds" in categories else 0)
    history = frame[(frame["internal_asset_id"] == asset_id) & (frame["participant_category"] == category)].sort_values("report_date")
    latest = history.iloc[-1]

    st.caption(
        f"Report date: {format_utc_timestamp(latest['report_date'], date_only=True)} | "
        f"Publication date: {format_utc_timestamp(latest['publication_date'], date_only=True)} | "
        f"Ingested: {format_utc_timestamp(latest['ingested_ts'])} | Source: official CFTC public reporting"
    )
    metrics = st.columns(6)
    metrics[0].metric("Gross long", _fmt(latest["gross_long"]))
    metrics[1].metric("Gross short", _fmt(latest["gross_short"]))
    metrics[2].metric("Net position", _fmt(latest["net_position"]))
    metrics[3].metric("1-week change", _fmt(latest["one_week_net_change"]))
    metrics[4].metric("4-week change", _fmt(latest["four_week_net_change"]))
    metrics[5].metric("Net / open interest", _fmt(latest["net_pct_open_interest"], ".1%"))
    second = st.columns(5)
    second[0].metric("52-week percentile", _fmt(latest["percentile_52w"], ".1%"))
    second[1].metric("3-year percentile", _fmt(latest["percentile_3y"], ".1%"))
    second[2].metric("Rolling z-score", _fmt(latest["rolling_zscore"], ".2f"))
    second[3].metric("Open-interest change", _fmt(latest["open_interest_change"]))
    second[4].metric("Condition", str(latest["crowding_condition"]))

    chart_left, chart_right = st.columns(2)
    with chart_left:
        fig = go.Figure(go.Scatter(x=history["report_date"], y=history["net_position"], mode="lines", name="Net position"))
        fig.add_hline(y=0, line_dash="dot")
        fig.update_layout(title="Historical net position", height=330)
        st.plotly_chart(fig, use_container_width=True)
    with chart_right:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=history["report_date"], y=history["gross_long"], mode="lines", name="Gross long"))
        fig.add_trace(go.Scatter(x=history["report_date"], y=history["gross_short"], mode="lines", name="Gross short"))
        fig.update_layout(title="Long versus short", height=330)
        st.plotly_chart(fig, use_container_width=True)

    chart_left, chart_right = st.columns(2)
    with chart_left:
        fig = go.Figure(go.Scatter(x=history["report_date"], y=history["percentile_52w"], mode="lines", name="52-week percentile"))
        fig.add_hline(y=0.9, line_dash="dot")
        fig.add_hline(y=0.1, line_dash="dot")
        fig.update_layout(title="Positioning percentile", height=330, yaxis_tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)
    with chart_right:
        fig = go.Figure(go.Scatter(x=history["report_date"], y=history["open_interest"], mode="lines", name="Open interest"))
        fig.update_layout(title="Open interest", height=330)
        st.plotly_chart(fig, use_container_width=True)

    market_symbol = CFTC_MARKET_MAP.get(asset_id)
    market = state["market"]
    market = market[market["symbol"] == market_symbol].sort_values("observation_ts") if market_symbol else pd.DataFrame()
    if not market.empty:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=market["observation_ts"], y=market["adjusted_close"], name=market_symbol), secondary_y=False)
        fig.add_trace(go.Scatter(x=history["report_date"], y=history["net_position"], name="Net positioning"), secondary_y=True)
        fig.update_layout(title=f"{market_symbol} price versus {category} positioning", height=360)
        st.plotly_chart(fig, use_container_width=True)

    render_section_heading("Risk flags", "Flags identify current conditions; they do not forecast price direction.")
    flags = st.columns(4)
    flags[0].metric("Positioning reversal", "Flagged" if bool(latest["positioning_reversal"]) else "Not flagged")
    flags[1].metric("Price-positioning divergence", "Flagged" if bool(latest["price_positioning_divergence"]) else "Not flagged")
    flags[2].metric("Long-liquidation risk", "Flagged" if bool(latest["long_liquidation_risk"]) else "Not flagged")
    flags[3].metric("Short-squeeze risk", "Flagged" if bool(latest["short_squeeze_risk"]) else "Not flagged")

    render_section_heading("Supporting calculations")
    st.dataframe(
        history.tail(52)[
            [
                "report_date",
                "publication_date",
                "gross_long",
                "gross_short",
                "net_position",
                "one_week_net_change",
                "four_week_net_change",
                "net_pct_open_interest",
                "percentile_52w",
                "percentile_3y",
                "rolling_zscore",
                "open_interest",
                "open_interest_change",
                "crowding_condition",
                "confidence",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )
    with st.expander("Methodology and mapping controls"):
        st.markdown(
            "Contracts are selected only through explicit configuration and exact official CFTC identifiers or names. The pipeline rejects ambiguous mappings. "
            "Net position equals gross long minus gross short. Percentiles compare each participant category with its own rolling history."
        )
