# Limitations

- The platform is an end-of-day or delayed research system, not a real-time trading terminal.
- yfinance/Yahoo Finance is a replaceable research-grade source without an institutional SLA.
- Option quotes can be delayed, stale, crossed, incomplete, or temporarily unavailable.
- Historical options analytics begin with locally collected snapshots; no free institutional history is backfilled.
- Public option chains do not reveal dealer inventory. Gamma signs and gamma-flip calculations are assumption-sensitive estimates.
- CFTC reports are weekly and delayed. Participant definitions differ between TFF, disaggregated, and legacy reports.
- Exact CFTC mappings reduce ambiguity but do not make futures positioning a direct ETF ownership measure.
- FRED observation timestamps are not always release timestamps and current history is not ALFRED vintage-safe.
- Daily-bar liquidity proxies do not observe order-book depth, effective spreads, realized spreads, hidden liquidity, or exchange fragmentation.
- Amihud and price-impact proxies can be unstable for index values or very low-volume assets.
- Market Pressure Score, options conditions, crowding, squeeze, liquidation, and divergence flags are descriptive, not buy/sell signals or forecasts.
- Missing inputs reduce confidence and are not converted to zero, but proxy-model risk remains even with full coverage.
- No machine learning, LLM, authentication, execution, portfolio sizing, or live alerting is included.
