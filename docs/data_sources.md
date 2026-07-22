# Data Sources

| Provider | Working coverage | Frequency | Credentials | Status and limitations | Replacement path |
| --- | --- | --- | --- | --- | --- |
| FRED | Macro, policy rates, Treasury yields, inflation, labour, credit, and reserve/liquidity series | Mixed | `FRED_API_KEY` | Official and delayed; observation dates are not always release timestamps; history is not vintage-safe | ALFRED/vintage-aware official ingestion |
| CFTC Public Reporting | Exact mapped equity-index, Treasury, USD Index, Gold, and WTI contracts | Weekly | None | Official, weekly, and delayed; categories vary by report type | Same official API with expanded reviewed mappings |
| yfinance/Yahoo Finance | Daily OHLCV for SPY, QQQ, IWM, TLT, HYG, GLD, USO, UUP, VIX, SMH, XLF, XLE, XLK | Daily | None | Unofficial, research-grade, delayed, and without an SLA | Licensed market-data vendor |
| yfinance/Yahoo Finance options | Current SPY and QQQ chains saved as timestamped snapshots | Snapshot | None | Unofficial; quotes may be stale, crossed, incomplete, or rate-limited | Licensed historical/realtime options vendor |

The application labels vendor data as research-grade and does not claim institutional-quality coverage.
