"""Methodology and source disclosure page."""

from __future__ import annotations

import streamlit as st

from dashboard.components.layout import render_page_header, render_section_heading


def render() -> None:
    render_page_header(
        "Methodology",
        "Data provenance, deterministic formulas, assumptions, and known limitations.",
        badges=["Transparent rules", "No LLM"],
    )

    render_section_heading("Data architecture")
    st.markdown(
        "Providers save timestamped raw snapshots, validation writes canonical observations to DuckDB, and `python scripts/run_analytics.py` persists prepared analytics. "
        "Dashboard pages read those stored results and cache database reads for ten minutes."
    )

    render_section_heading("Source and timestamp meanings")
    st.markdown(
        "FRED and CFTC are official public sources. yfinance is a replaceable, research-grade provider for delayed daily bars and current option-chain snapshots. "
        "`observation_ts` describes the market/economic observation, `available_ts` approximates when it became knowable, `ingested_ts` records retrieval, and `calculation_ts` records analytics generation."
    )

    with st.expander("Cross-asset screener and Market Pressure Score", expanded=True):
        st.markdown(
            "Daily returns, moving-average distance, realized volatility, relative volume, dollar volume, and Amihud illiquidity are calculated from stored OHLCV. "
            "The descriptive -100 to +100 score weights trend/momentum 30%, price-volume confirmation 20%, volatility 20%, liquidity 15%, and positioning 15%. "
            "Unavailable components are omitted, remaining weights are redistributed proportionally, and confidence is reduced. It is not a recommendation."
        )

    with st.expander("Liquidity & Market-Structure Proxies"):
        st.markdown(
            "Stress weights are Amihud percentile 25%, realized-volatility percentile 20%, intraday-range percentile 15%, inverse relative dollar volume 15%, HYG stress 15%, and VIX stress 10%. "
            "These daily-bar proxies do not measure order-book depth, effective or realized spreads, or venue fragmentation."
        )

    with st.expander("CFTC positioning"):
        st.markdown(
            "Contracts use explicit exact CFTC mappings; ambiguous mappings are rejected. Net equals gross long minus gross short. Changes, net/open-interest, rolling percentiles, z-scores, reversals, and crowding are category-specific. "
            "CFTC data are weekly and delayed. Crowding, liquidation, squeeze, and divergence flags identify conditions rather than predict outcomes."
        )

    with st.expander("SPY and QQQ options"):
        st.markdown(
            "The module calculates put/call ratios, ATM and median IV, IV-minus-realized volatility, term structure, expected move, approximate 25-delta skew, open-interest concentration, and Black-Scholes delta/gamma. "
            "Expected move uses a valid ATM straddle midpoint and falls back to spot x IV x square-root time. Delta matching reports the closest available contract."
        )

    with st.expander("Estimated Gamma Exposure"):
        st.markdown(
            "Contract gamma is multiplied by open interest, contract multiplier, and spot squared. Public chains do not reveal dealer inventory, so the sign is not observable. "
            "The dashboard exposes alternative call/put sign assumptions, sensitivity, confidence, and a gamma-flip estimate only when scenario totals cross zero."
        )

    with st.expander("Evidence-based summary"):
        st.markdown(
            "The summary combines stored trend, volatility, liquidity, CFTC, options, credit, and rates evidence. It preserves confirming and contradicting metrics, lowers confidence for missing or stale modules, and uses fixed prose rules without machine learning or an LLM."
        )

    render_section_heading("Scope limitations")
    st.markdown(
        "This is a delayed research application, not an institutional feed or execution system. Free-provider options can contain stale, crossed, or incomplete quotes. "
        "Historical options analysis starts with local snapshot collection, FRED history is not vintage-safe, and no score is a buy/sell signal."
    )
