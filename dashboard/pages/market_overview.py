"""Market overview page."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.cards import render_coming_soon_cards, render_metric_cards, render_status_badge
from dashboard.components.layout import render_empty_state, render_page_header, render_section_heading, render_warning_panel
from cross_asset_intelligence.services.market_data_service import calculate_daily_returns, normalize_performance


def _latest_value(frame: pd.DataFrame, symbol: str, column: str = "adjusted_close"):
    subset = frame[frame["symbol"] == symbol] if not frame.empty and "symbol" in frame.columns else pd.DataFrame()
    if subset.empty:
        return None, None
    row = subset.sort_values("observation_ts").iloc[-1]
    return row.get(column), row.get("observation_ts")


def _format_value(value: object) -> str:
    if value is None or pd.isna(value):
        return "Not available"
    if isinstance(value, (int, float)):
        return f"{value:,.2f}"
    return str(value)


def render(
    *,
    latest_market: pd.DataFrame,
    latest_macro: pd.DataFrame,
    market_history: pd.DataFrame,
    yield_history: pd.DataFrame,
    vix_history: pd.DataFrame,
    database_command: str,
    latest_refresh_timestamp,
    overall_health: dict,
) -> None:
    render_page_header(
        "Cross-Asset Derivatives Intelligence Platform",
        "End-of-day cross-asset research platform",
        badges=["Market Overview", "Phase 2"],
    )
    st.caption(f"Latest successful refresh: {pd.Timestamp(latest_refresh_timestamp).strftime('%Y-%m-%d %H:%M UTC') if latest_refresh_timestamp is not None and pd.notna(latest_refresh_timestamp) else 'Not available'}")
    render_status_badge(overall_health.get("status", "Missing"))

    if latest_market.empty:
        render_empty_state(
            "No market data available yet",
            "The dashboard is ready, but the local DuckDB database does not contain market observations yet.",
            database_command,
        )
    else:
        market_lookup = {row.symbol: row for row in latest_market.itertuples(index=False)} if not latest_market.empty else {}
        macro_lookup = {row.series_id: row for row in latest_macro.itertuples(index=False)} if not latest_macro.empty else {}
        return_frame = calculate_daily_returns(market_history) if not market_history.empty else pd.DataFrame()
        latest_return_lookup = {}
        if not return_frame.empty:
            latest_return_lookup = {
                row.symbol: row.daily_return
                for row in return_frame.sort_values("observation_ts").groupby("symbol", sort=False).tail(1).itertuples(index=False)
            }

        def market_value_for(symbol: str, column: str = "adjusted_close"):
            row = market_lookup.get(symbol)
            if row is None:
                return None
            mapped_column = column
            if column == "adjusted_close" and hasattr(row, "latest_adjusted_close"):
                mapped_column = "latest_adjusted_close"
            elif column == "close" and hasattr(row, "latest_close"):
                mapped_column = "latest_close"
            return getattr(row, mapped_column, None)

        def macro_value_for(series_id: str):
            row = macro_lookup.get(series_id)
            return getattr(row, "latest_value", None) if row else None

        def pct_change(symbol: str) -> str:
            value = latest_return_lookup.get(symbol)
            if value is None or pd.isna(value):
                return "Not available"
            return f"{value:.2f}%"

        metrics = [
            {"label": "SPY latest close", "value": _format_value(market_value_for("SPY"))},
            {"label": "SPY daily return", "value": pct_change("SPY")},
            {"label": "QQQ latest close", "value": _format_value(market_value_for("QQQ"))},
            {"label": "QQQ daily return", "value": pct_change("QQQ")},
            {"label": "VIX latest close", "value": _format_value(market_value_for("VIX"))},
            {"label": "10Y Treasury yield", "value": _format_value(macro_value_for("DGS10"))},
            {"label": "2Y Treasury yield", "value": _format_value(macro_value_for("DGS2"))},
            {"label": "10Y-2Y spread", "value": _format_value(macro_value_for("T10Y2Y"))},
        ]
        render_metric_cards(metrics)

    render_section_heading("What the dashboard currently does", "Phase 2 is an ingestion, validation, storage, and descriptive monitoring layer.")
    st.markdown(
        """
        - It ingests official FRED series and delayed daily market data.
        - It stores raw snapshots and validated observations locally in DuckDB.
        - It reports freshness and pipeline status.
        - It does not produce regime calls, trade recommendations, or AI summaries yet.
        """,
    )

    st.divider()
    render_section_heading("Market charts", "Prepared from stored daily observations.")

    perf_frame = normalize_performance(market_history) if not market_history.empty else market_history
    ret_frame = calculate_daily_returns(market_history) if not market_history.empty else market_history

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        if perf_frame.empty:
            render_empty_state("Normalized performance", "No stored market history yet.")
        else:
            fig = go.Figure()
            for symbol in ["SPY", "QQQ", "IWM", "TLT", "HYG", "GLD", "USO"]:
                subset = perf_frame[perf_frame["symbol"] == symbol]
                if subset.empty:
                    continue
                fig.add_trace(go.Scatter(x=subset["observation_ts"], y=subset["normalized_value"], mode="lines", name=symbol))
            fig.update_layout(title="Normalized performance", xaxis_title="Date", yaxis_title="Index (start = 100)", height=360)
            st.plotly_chart(fig, use_container_width=True)
    with chart_col2:
        if yield_history.empty:
            render_empty_state("Treasury yields", "No yield observations stored yet.")
        else:
            fig = go.Figure()
            for symbol in ["DGS2", "DGS10"]:
                subset = yield_history[yield_history["series_id"] == symbol]
                if subset.empty:
                    continue
                fig.add_trace(go.Scatter(x=subset["observation_ts"], y=subset["value"], mode="lines", name=symbol))
            fig.update_layout(title="Recent Treasury yields", xaxis_title="Date", yaxis_title="Yield", height=360)
            st.plotly_chart(fig, use_container_width=True)

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        if ret_frame.empty:
            render_empty_state("Daily returns", "No market history available for return comparison.")
        else:
            fig = go.Figure()
            for symbol in ["SPY", "QQQ", "IWM", "TLT", "HYG", "GLD", "USO"]:
                subset = ret_frame[ret_frame["symbol"] == symbol]
                if subset.empty:
                    continue
                fig.add_trace(go.Scatter(x=subset["observation_ts"], y=subset["daily_return"], mode="lines", name=symbol))
            fig.update_layout(title="Cross-asset daily-return comparison", xaxis_title="Date", yaxis_title="Daily return (%)", height=360)
            st.plotly_chart(fig, use_container_width=True)
    with chart_col2:
        if vix_history.empty:
            render_empty_state("Volatility panel", "No VIX observations stored yet.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=vix_history["observation_ts"], y=vix_history["adjusted_close"], mode="lines", name="VIX"))
            fig.update_layout(title="Recent volatility panel", xaxis_title="Date", yaxis_title="VIX", height=360)
            st.plotly_chart(fig, use_container_width=True)

    render_section_heading("Coming later", "These modules are intentionally shown as future work.")
    render_coming_soon_cards(
        [
            {"title": "Positioning", "description": "Coming later. CFTC positioning and futures open-interest analytics are not part of Phase 2."},
            {"title": "Options", "description": "Coming later. Options chains, gamma, skew, and volatility surfaces are not yet implemented."},
            {"title": "Market Structure", "description": "Coming later. Microstructure and market-depth analysis will be added in a future phase."},
            {"title": "Liquidity", "description": "Coming later. Liquidity analytics will expand beyond basic reserve and balance-sheet proxies."},
            {"title": "Cross-Asset", "description": "Coming later. Relative-value and cross-market relationship analysis will be added later."},
        ]
    )
