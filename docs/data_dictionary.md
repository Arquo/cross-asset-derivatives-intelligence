# Data Dictionary

## StandardObservation Fields

| Field | Meaning |
| --- | --- |
| record_id | Stable unique record identifier |
| dataset_id | Stable dataset identifier |
| provider | Human-readable provider name |
| source_type | SourceType enum value |
| symbol | Canonical internal symbol |
| provider_symbol | Original provider symbol |
| asset_class | AssetClass enum value |
| observation_ts | Time represented by the value |
| available_ts | Earliest time the system could have known the value |
| ingested_ts | Time the application retrieved or stored the value |
| frequency | Frequency enum value |
| timezone | Timezone label for the timestamps |
| value | Observation value |
| unit | Unit of measure |
| is_adjusted | Whether the value was adjusted |
| is_estimated | Whether the value is estimated |
| is_revised | Whether the value is a revision |
| quality_status | QualityStatus enum value |
| quality_flags | Free-form quality notes or flags |
| source_reference | Link or reference to the source record |
| pipeline_run_id | Ingestion run identifier |

## New Tables

### pipeline_runs

Stores provider-level run metadata, counts, and status.

### macro_observations

Validated FRED observations with stable logical keys based on `series_id + observation_ts`.

### market_prices

Validated daily market rows with stable logical keys based on `symbol + observation_ts`.

### data_quality_events

Warnings and rejection events emitted by validation rules.

### dataset_catalog

Current dataset metadata, freshness, and status summary.

## Enums

### SourceType

- official
- vendor
- calculated
- estimated
- manual

### QualityStatus

- valid
- warning
- stale
- missing
- rejected

### Frequency

- intraday
- daily
- weekly
- monthly
- quarterly

### AssetClass

- equity
- etf
- rate
- future
- option
- macro
- volatility
- commodity
- currency
- credit

### SignalDirection

- bullish
- bearish
- neutral
- mixed
- unknown

### ConfidenceLevel

- low
- medium
- high

## Timestamp Meaning

- `observation_ts` is the market or economic time represented by the value.
- `available_ts` is the earliest time the value could have been known.
- `ingested_ts` is when the application retrieved or stored the value.

## Data-Quality Statuses

- `valid`: record is acceptable for analysis
- `warning`: record is usable but has caveats
- `stale`: data is old relative to the configured freshness window
- `missing`: expected data is absent
- `rejected`: data failed validation and should not be used

## Estimated-Data Labeling

Estimated or proxy data must be clearly labeled with source type, quality flags, and documentation. Phase 1B uses `historical_data` and `yfinance_unofficial` flags for market data.

## Look-Ahead-Bias Protection

The separation between observation time, availability time, and ingestion time prevents the application from treating a later-known value as if it were available earlier. Phase 1B uses `available_ts = ingested_ts` for FRED as a conservative current-state proxy and explicitly does not claim vintage-safe history.
