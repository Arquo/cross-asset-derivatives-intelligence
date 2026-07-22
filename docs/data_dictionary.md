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

- Raw provider snapshots are saved as Parquet under `data/raw/fred/` and `data/raw/market/`.
- Each run uses a unique pipeline-run subdirectory.
- Raw snapshots are preserved even when later validation fails.

