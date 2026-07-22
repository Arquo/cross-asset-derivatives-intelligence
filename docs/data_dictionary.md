# Data Dictionary

## Canonical observation fields

The project keeps a shared observation shape so provider output can be normalized before validation and storage.

| Field | Meaning |
| --- | --- |
| record_id | Stable unique record identifier |
| dataset_id | Stable dataset identifier |
| provider | Human-readable provider name |
| source_type | SourceType enum value |
| observation_ts | Economic or market observation timestamp |
| available_ts | Earliest time the platform could have known the record |
| ingested_ts | Time the platform retrieved or stored the record |
| frequency | Observation frequency |
| value | Observation value |
| quality_status | QualityStatus enum value |
| quality_flags | Free-form quality notes or rule flags |

## DuckDB tables

### pipeline_runs

Pipeline-level metadata for each provider run.

Key fields:

- `pipeline_run_id`
- `pipeline_name`
- `provider`
- `started_at`
- `completed_at`
- `requested_start_date`
- `requested_end_date`
- `status`
- `records_received`
- `records_validated`
- `records_rejected`
- `warning_count`
- `error_message`
- `raw_snapshot_location`

### macro_observations

Validated FRED observations stored at the `series_id + observation_ts` natural key.

### market_observations

Validated market rows stored at the `symbol + observation_ts` natural key.

Key fields include:

- `open`
- `high`
- `low`
- `close`
- `adjusted_close`
- `adjusted_close_status`
- `volume`

### cftc_positioning_observations

Official weekly CFTC records at contract, report date, report type, and participant-category grain. Separate fields retain report, publication/availability, and ingestion timestamps.

### option_contract_snapshots

Immutable option-chain contracts at snapshot and contract-symbol grain. Important fields include `snapshot_id`, `symbol`, `underlying_price`, `quote_timestamp`, `expiration`, `strike`, `option_type`, bid/ask/last, implied volatility, volume, open interest, in-the-money status, source label, and raw snapshot location.

### screener_results

Latest per-asset screener metrics, classifications, Market Pressure Score, freshness, serialized component audit trail, and missing components. Natural key: `symbol + observation_ts`.

### market_pressure_scores

Persisted -100 to +100 descriptive scores with label, confidence, base/effective component weights, contributions, missing components, and available coverage weight.

### liquidity_analytics

Daily per-asset liquidity proxy history. Stores dollar/relative volume, realized volatility, intraday range, ATR, Amihud level/percentile, volume shock, price impact, drawdown, HYG/VIX stress, composite score/regime, confidence, contributions, and missing inputs.

### positioning_analytics

Per-contract/category/report-date CFTC calculations: gross/net exposure, changes, net/open-interest, percentiles, z-score, reversal, crowding, divergence, liquidation/squeeze flags, confidence, and source reference.

### option_analytics

Per snapshot, expiration, and gamma-assumption summary. Stores general chain totals, volatility comparisons, expected move, 25-delta skew, OI structure, Estimated Gamma Exposure, gamma-flip/sensitivity, deterministic condition evidence, assumptions, confidence, and limitations.

### cross_module_summaries

One deterministic market-setup payload per analytics data cutoff, including market-pressure/liquidity/volatility conditions, positioning risk, SPY/QQQ options conditions, confirmation/contradiction lists, limitations, five monitor indicators, confidence, and source timestamps.

### analytics_runs

Execution metadata for persisted calculation runs, including requested modules, calculated row counts, warnings, missing/stale datasets, status, and data cutoff.

### data_quality_events

Validation warnings and rejections with human-readable messages.

Key fields:

- `event_id`
- `pipeline_run_id`
- `dataset_id`
- `record_id`
- `severity`
- `rule_id`
- `message`

### dataset_catalog

Freshness and status summary for each configured dataset.

Key fields:

- `dataset_id`
- `dataset_name`
- `provider`
- `expected_publication_delay_days`
- `latest_observation_ts`
- `latest_ingestion_ts`
- `age_days`
- `freshness_status`
- `quality_status`
- `record_count`
- `latest_pipeline_status`
- `warning_message`

## Timestamp meaning

- `observation_ts` is the market or economic time represented by the value.
- `available_ts` is when the platform could have known the value.
- `ingested_ts` is when the platform retrieved or stored the value.

## Freshness categories

- `Current`
- `Delayed as expected`
- `Stale`
- `Missing`
- `Failed`

## Validation notes

- Missing required fields are rejected and flagged.
- Duplicate symbol/date or series/date rows are rejected.
- Stale rows are retained with warning flags when appropriate.
- Large daily market moves produce warnings rather than automatic rejection.

## Raw storage

- Raw provider snapshots are saved under `data/raw/fred/`, `data/raw/market/`, `data/raw/cftc/`, and `data/raw/options/`.
- Each run uses a unique pipeline-run subdirectory.
- Option snapshots use an immutable symbol/snapshot-ID path and are never overwritten by later retrievals.
- Raw snapshots are preserved even when later validation or analytics fail.

