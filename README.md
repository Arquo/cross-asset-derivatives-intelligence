# Cross-Asset Derivatives Intelligence Platform

A portfolio-grade, deterministic research dashboard for delayed cross-asset market data, liquidity proxies, CFTC positioning, and SPY/QQQ options. The application persists provider observations and calculated analytics in DuckDB so Streamlit can render useful results without recomputing every metric on each rerun.

This is a research project, not a live feed, institutional data product, trade recommendation, or execution system.

## Working Modules

- Market Overview with a deterministic "Today's Market Setup"
- Macro Regime using official FRED observations
- Cross-Asset Screener for 13 configured assets
- Market Pressure Score with component-level weights and contributions
- Liquidity & Market-Structure Proxies
- Official CFTC positioning, crowding, reversal, and risk flags
- SPY and QQQ options conditions, skew, expected move, open interest, and estimated gamma
- Evidence-Based Market Summary with confirmations, contradictions, confidence, and limitations
- Data Freshness and Methodology pages

## Data Sources

- FRED: official macro, rates, credit, and reserve/liquidity series; requires `FRED_API_KEY`.
- CFTC Public Reporting: official weekly, delayed Commitments of Traders data with exact configured contract codes.
- yfinance/Yahoo Finance: replaceable, research-grade delayed daily OHLCV and current option-chain snapshots.

Configured market universe: SPY, QQQ, IWM, TLT, HYG, GLD, USO, UUP, `^VIX` (stored as VIX), SMH, XLF, XLE, and XLK.

## Setup

PowerShell:

```powershell
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create `.env` locally:

```env
FRED_API_KEY=your_fred_api_key_here
```

The secret is ignored by Git and is never printed by the application.

## Run the Product

Initialize DuckDB:

```powershell
python scripts/initialize_database.py
```

Retrieve the required datasets:

```powershell
python scripts/ingest_data.py --provider market
python scripts/ingest_data.py --provider cftc
python scripts/ingest_data.py --provider options --symbols SPY QQQ
```

FRED can be refreshed separately:

```powershell
python scripts/ingest_data.py --provider fred
```

Calculate and persist analytics:

```powershell
python scripts/run_analytics.py
```

Launch Streamlit:

```powershell
python -m streamlit run app.py
```

Run offline tests:

```powershell
python -m pytest
```

Tests use synthetic data and do not call live providers.

## Screener Methodology

Daily-bar features include 1/5/20/60-day returns, 20/60-day moving-average distance, 20-day annualized realized volatility, relative volume, dollar volume, and rolling Amihud illiquidity percentile.

The Market Pressure Score ranges from -100 to +100:

- Trend and momentum: 30%
- Relative volume and price-volume confirmation: 20%
- Volatility condition: 20%
- Liquidity condition: 15%
- CFTC positioning condition: 15%

Missing components are excluded rather than converted to zero. Available weights are redistributed proportionally, every contribution is stored, and confidence falls as coverage declines. The score is descriptive, not a buy or sell signal. See [docs/screener_methodology.md](docs/screener_methodology.md).

## Liquidity Methodology

The 0-100 stress proxy weights Amihud percentile (25%), realized-volatility percentile (20%), intraday-range percentile (15%), inverse relative dollar volume (15%), HYG stress (15%), and VIX stress (10%). It uses daily bars and cannot observe full order-book or transaction-cost conditions. See [docs/liquidity_proxy_methodology.md](docs/liquidity_proxy_methodology.md).

## CFTC Methodology

The pipeline uses exact official CFTC contract codes and rejects ambiguous mappings. Calculations are participant-category specific and include net position, weekly/four-week changes, net/open-interest, rolling percentiles and z-score, reversal, crowding, divergence, and descriptive liquidation/squeeze risks. Reports are weekly and delayed. See [docs/cftc_methodology.md](docs/cftc_methodology.md).

## Options and Gamma Methodology

Every SPY/QQQ retrieval is stored as an immutable timestamped snapshot. Analytics include put/call ratios, ATM and median IV, realized-versus-implied volatility, term structure, expected move, approximate 25-delta skew, open-interest concentration, and Black-Scholes Greeks.

Estimated Gamma Exposure is `gamma x open interest x contract multiplier x spot^2`. Public chains do not reveal dealer inventory, so call/put signs are explicit user-selectable assumptions and sensitivity is shown. See [docs/options_methodology.md](docs/options_methodology.md) and [docs/gamma_methodology.md](docs/gamma_methodology.md).

## Storage

- Raw snapshots: `data/raw/{fred,market,cftc,options}/`
- DuckDB: `data/database/cross_asset.duckdb`
- Reports: `data/reports/`
- Pipeline diagnostics: `pipeline_runs` and `data_quality_events`
- Prepared outputs: screener, pressure, liquidity, positioning, options, analytics-run, and cross-module summary tables

Generated data, databases, reports, local secrets, and virtual environments are excluded from Git.

## Known Limitations

- Market and options vendor data are free, delayed/research-grade, and replaceable.
- Option quotes can be stale, crossed, incomplete, or missing; snapshot history starts locally.
- Gamma signs are assumptions, not observed dealer inventory.
- CFTC data are weekly and delayed; category definitions differ by report type.
- FRED observation dates are not always release timestamps, and history is not vintage-safe.
- Daily-bar liquidity proxies do not measure order-book depth, effective spreads, realized spreads, or exchange fragmentation.
- No score or flag is a directional prediction or recommendation.

See [docs/limitations.md](docs/limitations.md) for the full list.

## Screenshots

Screenshot placeholders for the portfolio presentation:

- `docs/screenshots/market-overview.png`
- `docs/screenshots/cross-asset-screener.png`
- `docs/screenshots/options-analysis.png`

Add screenshots after reviewing the populated application locally.
