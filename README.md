# Cross-Asset Derivatives Intelligence Platform

Phase 2 is now the working baseline: data ingestion, validation, raw snapshot storage, DuckDB persistence, freshness reporting, and a professional Streamlit dashboard.

## What works now

- Official FRED macro and rates ingestion
- Replaceable yfinance market ingestion for the MVP asset universe
- Immutable raw Parquet snapshots
- Validated DuckDB tables
- Data-quality events and freshness metadata
- Streamlit pages for:
  - Market Overview
  - Macro Snapshot
  - Data Freshness
  - Methodology

The platform is an end-of-day or delayed-data research system. It is not real time.

## Environment

Create a local `.env` file with:

```env
FRED_API_KEY=your_fred_api_key_here
```

The repository also includes `.env.example` as a template.

## Setup

PowerShell:

```powershell
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Initialize the database

```powershell
python scripts/initialize_database.py
```

This creates the DuckDB file at:

```text
data/database/cross_asset.duckdb
```

## Ingest data

Ingest both providers:

```powershell
python scripts/ingest_data.py --provider all --start-date 2024-01-01
```

Ingest only FRED:

```powershell
python scripts/ingest_data.py --provider fred --start-date 2024-01-01
```

Ingest only market data:

```powershell
python scripts/ingest_data.py --provider market --symbols SPY QQQ --start-date 2024-01-01
```

Dry run:

```powershell
python scripts/ingest_data.py --provider all --start-date 2024-01-01 --dry-run
```

Optional arguments:

- `--end-date`
- `--symbols`
- `--series`

## Launch the dashboard

```powershell
python -m streamlit run app.py
```

## Run tests

```powershell
python -m pytest
```

## Current data sources

- FRED series:
  - DFF
  - DGS2
  - DGS10
  - T10Y2Y
  - DFII10
  - T10YIE
  - CPIAUCSL
  - CPILFESL
  - UNRATE
  - ICSA
  - BAMLH0A0HYM2
  - WALCL
  - RRPONTSYD
  - WTREGEN
- Market symbols:
  - SPY
  - QQQ
  - IWM
  - TLT
  - HYG
  - GLD
  - USO
  - UUP
  - VIX

## Data limitations

- FRED observation dates are not release timestamps.
- yfinance is a replaceable vendor source, not an institutional feed.
- The dashboard is designed for delayed or end-of-day research, not live trading.
- No options, CFTC positioning, AI strategist, or trading workflow is implemented yet.

## Raw storage and DuckDB

- Raw provider snapshots are stored as Parquet under `data/raw/fred/` and `data/raw/market/`.
- Validated tables live in DuckDB.
- Pipeline metadata is stored in `pipeline_runs`.
- Validation issues are stored in `data_quality_events`.
- Dataset freshness is summarized in `dataset_catalog`.

## Current dashboard pages

- Market Overview
- Macro Snapshot
- Data Freshness
- Methodology

## Planned future modules

- Positioning
- Options
- Market Structure
- Liquidity
- Cross-Asset
- AI Strategist

## Screenshots

Add screenshots later once the dashboard styling is finalized. A good place to store them is `docs/screenshots/`.

