# Data Sources

| Provider | Dataset | Coverage | Frequency | Credentials | Cost | Official or unofficial | Delay status | Limitations | Replacement path |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FRED | Macro, rates, credit, liquidity | DFF, DGS2, DGS10, T10Y2Y, DFII10, T10YIE, CPIAUCSL, UNRATE, ICSA, BAMLH0A0HYM2, WALCL, WTREGEN, RRPONTSYD, WRESBAL | Mixed | Yes | Free | Official | Historical / delayed | Observation dates are not release timestamps; historical vintages are not point-in-time safe in Phase 1B | ALFRED vintage support and later ingestion tooling |
| yfinance | Daily market prices | SPY, QQQ, IWM, TLT, HYG, GLD, USO, UUP, VIX | Daily | No | Free | Unofficial | Historical / delayed | Not institutional data; no live feed; options API not used here | Paid market-data vendor with stable licensing and SLA |

