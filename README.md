# Cross-Asset Derivatives Intelligence Platform

Cross-Asset Derivatives Intelligence Platform is a portfolio project for research and market-monitoring workflows across macro, positioning, options, liquidity, and cross-asset signals.

## Current Status

Phase 1A established the foundation package, schemas, tests, and the original Streamlit MVP.

Phase 1B adds the first free-data pipeline:

- FRED macro and rates ingestion
- yfinance daily market-price ingestion
- Immutable raw snapshots
- Validation and DuckDB storage
- Pipeline-run metadata
- A DuckDB-backed data-status dashboard

## Free Data Sources

- FRED: official macro, rates, credit, and liquidity series
- yfinance: unofficial historical daily market prices

## Setup

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Create a local `.env` file:

```env
FRED_API_KEY=<your key>
```

## Install Dependencies

```powershell
python -m pip install -e .
```

## Pipeline Commands

Run both providers:

```powershell
python -m cross_asset_intelligence.pipelines.run_free_data --start 2015-01-01 --provider all
```

Run only market data:

```powershell
python -m cross_asset_intelligence.pipelines.run_free_data --start 2015-01-01 --provider market
```

Run only FRED:

```powershell
python -m cross_asset_intelligence.pipelines.run_free_data --start 2015-01-01 --provider fred
```

Dry run:

```powershell
python -m cross_asset_intelligence.pipelines.run_free_data --start 2015-01-01 --provider all --dry-run
```

## Launch Streamlit

```powershell
python -m streamlit run app.py
```

## Run Tests

```powershell
python -m pytest
```

## Local Data Directories

- `data/raw/fred/`
- `data/raw/market/`
- `data/processed/`
- `data/sample/`

The DuckDB database is stored at:

```text
data/processed/cross_asset_intelligence.duckdb
```

## Data-Refresh Workflow

1. Run the pipeline.
2. Review the DuckDB tables.
3. Open Streamlit to inspect freshness and provider status.
4. Re-run the pipeline for newer dates when needed.

## Troubleshooting

- Missing FRED API key: market data can still run, but FRED is skipped.
- Empty database: run the pipeline first.
- Stale data: check the provider freshness date in the data-status page.
- Partial success: inspect `data_quality_events` and `pipeline_runs`.

## Limitations

- Market data is historical or delayed, not real time.
- yfinance is unofficial.
- No options, CFTC, AI, or trading logic exists yet.
- Historical FRED data in Phase 1B is not vintage-safe.

## Roadmap

- Week 1: Foundation and data contracts
- Week 2: Deterministic analytics and CFTC positioning
- Week 3: SPY and QQQ options plus structured AI synthesis
- Week 4: Dashboard, testing, case studies, and presentation

## Phase 1 Checklist

- [x] Foundation package
- [x] Standard schemas
- [x] Provider interfaces
- [x] Product docs
- [x] Unit tests
- [x] Free-data pipeline
- [x] DuckDB storage
- [x] Data-status dashboard

