"""DuckDB persistence helpers."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from typing import Iterator

import duckdb
import pandas as pd


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    pipeline_run_id VARCHAR,
    pipeline_name VARCHAR,
    provider VARCHAR,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR,
    requested_start_date DATE,
    requested_end_date DATE,
    datasets_requested VARCHAR,
    records_received BIGINT,
    records_validated BIGINT,
    records_rejected BIGINT,
    warning_count BIGINT,
    error_message VARCHAR,
    raw_snapshot_location VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS macro_observations (
    record_id VARCHAR,
    dataset_id VARCHAR,
    series_id VARCHAR,
    provider VARCHAR,
    source_type VARCHAR,
    observation_ts TIMESTAMP WITH TIME ZONE,
    available_ts TIMESTAMP WITH TIME ZONE,
    ingested_ts TIMESTAMP WITH TIME ZONE,
    frequency VARCHAR,
    value DOUBLE,
    unit VARCHAR,
    quality_status VARCHAR,
    quality_flags VARCHAR,
    source_reference VARCHAR,
    pipeline_run_id VARCHAR,
    UNIQUE(series_id, observation_ts)
);

CREATE TABLE IF NOT EXISTS market_observations (
    record_id VARCHAR,
    dataset_id VARCHAR,
    symbol VARCHAR,
    provider_symbol VARCHAR,
    provider VARCHAR,
    source_type VARCHAR,
    frequency VARCHAR,
    observation_ts TIMESTAMP WITH TIME ZONE,
    available_ts TIMESTAMP WITH TIME ZONE,
    ingested_ts TIMESTAMP WITH TIME ZONE,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    adjusted_close DOUBLE,
    adjusted_close_status VARCHAR,
    volume BIGINT,
    currency VARCHAR,
    quality_status VARCHAR,
    quality_flags VARCHAR,
    pipeline_run_id VARCHAR,
    UNIQUE(symbol, observation_ts)
);

CREATE TABLE IF NOT EXISTS data_quality_events (
    event_id VARCHAR,
    pipeline_run_id VARCHAR,
    dataset_id VARCHAR,
    record_id VARCHAR,
    severity VARCHAR,
    rule_id VARCHAR,
    message VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS dataset_catalog (
    dataset_id VARCHAR PRIMARY KEY,
    dataset_name VARCHAR,
    provider VARCHAR,
    display_name VARCHAR,
    category VARCHAR,
    frequency VARCHAR,
    expected_publication_delay_days BIGINT,
    unit VARCHAR,
    source_type VARCHAR,
    is_delayed BOOLEAN,
    requires_credentials BOOLEAN,
    last_successful_ingestion TIMESTAMP WITH TIME ZONE,
    latest_ingestion_ts TIMESTAMP WITH TIME ZONE,
    latest_observation_ts TIMESTAMP WITH TIME ZONE,
    age_days DOUBLE,
    freshness_status VARCHAR,
    quality_status VARCHAR,
    record_count BIGINT,
    latest_pipeline_status VARCHAR,
    warning_message VARCHAR
);

CREATE TABLE IF NOT EXISTS cftc_contract_mappings (
    internal_asset_id VARCHAR PRIMARY KEY,
    display_name VARCHAR,
    cftc_contract_market_code VARCHAR,
    official_contract_name VARCHAR,
    report_type VARCHAR,
    exchange VARCHAR,
    asset_class VARCHAR,
    contract_unit VARCHAR,
    preferred_participant_categories VARCHAR,
    active BOOLEAN
);

CREATE TABLE IF NOT EXISTS cftc_positioning_observations (
    record_id VARCHAR,
    internal_asset_id VARCHAR,
    cftc_contract_market_code VARCHAR,
    contract_name VARCHAR,
    exchange VARCHAR,
    report_type VARCHAR,
    report_date TIMESTAMP WITH TIME ZONE,
    publication_date TIMESTAMP WITH TIME ZONE,
    available_ts TIMESTAMP WITH TIME ZONE,
    ingested_ts TIMESTAMP WITH TIME ZONE,
    participant_category VARCHAR,
    long_contracts DOUBLE,
    short_contracts DOUBLE,
    spreading_contracts DOUBLE,
    open_interest DOUBLE,
    trader_count DOUBLE,
    source_reference VARCHAR,
    quality_status VARCHAR,
    quality_flags VARCHAR,
    pipeline_run_id VARCHAR,
    UNIQUE(internal_asset_id, report_date, report_type, participant_category)
);

CREATE TABLE IF NOT EXISTS option_contract_snapshots (
    record_id VARCHAR PRIMARY KEY,
    snapshot_id VARCHAR,
    pipeline_run_id VARCHAR,
    symbol VARCHAR,
    underlying_price DOUBLE,
    quote_timestamp TIMESTAMP WITH TIME ZONE,
    ingested_ts TIMESTAMP WITH TIME ZONE,
    expiration DATE,
    contract_symbol VARCHAR,
    last_trade_timestamp TIMESTAMP WITH TIME ZONE,
    strike DOUBLE,
    option_type VARCHAR,
    contract_multiplier DOUBLE,
    bid DOUBLE,
    ask DOUBLE,
    last_price DOUBLE,
    implied_volatility DOUBLE,
    volume BIGINT,
    open_interest BIGINT,
    in_the_money BOOLEAN,
    source_label VARCHAR,
    quality_status VARCHAR,
    raw_snapshot_location VARCHAR,
    UNIQUE(snapshot_id, contract_symbol)
);

CREATE TABLE IF NOT EXISTS screener_results (
    analytics_run_id VARCHAR,
    symbol VARCHAR,
    asset_class VARCHAR,
    observation_ts TIMESTAMP WITH TIME ZONE,
    calculation_ts TIMESTAMP WITH TIME ZONE,
    latest_close DOUBLE,
    return_1d DOUBLE,
    return_5d DOUBLE,
    return_20d DOUBLE,
    return_60d DOUBLE,
    distance_ma_20d DOUBLE,
    distance_ma_60d DOUBLE,
    realized_vol_20d DOUBLE,
    relative_volume_20d DOUBLE,
    dollar_volume DOUBLE,
    amihud_percentile DOUBLE,
    trend_classification VARCHAR,
    volatility_classification VARCHAR,
    liquidity_classification VARCHAR,
    positioning_classification VARCHAR,
    options_classification VARCHAR,
    market_pressure_score DOUBLE,
    pressure_label VARCHAR,
    pressure_confidence VARCHAR,
    score_components VARCHAR,
    missing_components VARCHAR,
    freshness_status VARCHAR,
    source_label VARCHAR,
    UNIQUE(symbol, observation_ts)
);

CREATE TABLE IF NOT EXISTS market_pressure_scores (
    analytics_run_id VARCHAR,
    symbol VARCHAR,
    observation_ts TIMESTAMP WITH TIME ZONE,
    calculation_ts TIMESTAMP WITH TIME ZONE,
    score DOUBLE,
    label VARCHAR,
    confidence VARCHAR,
    components VARCHAR,
    missing_components VARCHAR,
    available_weight DOUBLE,
    source_label VARCHAR,
    UNIQUE(symbol, observation_ts)
);

CREATE TABLE IF NOT EXISTS liquidity_analytics (
    analytics_run_id VARCHAR,
    symbol VARCHAR,
    observation_ts TIMESTAMP WITH TIME ZONE,
    calculation_ts TIMESTAMP WITH TIME ZONE,
    dollar_volume DOUBLE,
    average_dollar_volume_20d DOUBLE,
    relative_dollar_volume_20d DOUBLE,
    relative_volume_20d DOUBLE,
    realized_volatility_20d DOUBLE,
    intraday_range_pct DOUBLE,
    average_true_range_14d DOUBLE,
    amihud_illiquidity_20d DOUBLE,
    amihud_percentile DOUBLE,
    volume_shock_zscore DOUBLE,
    price_impact_proxy DOUBLE,
    drawdown DOUBLE,
    hyg_stress DOUBLE,
    vix_stress DOUBLE,
    liquidity_stress_score DOUBLE,
    stress_historical_percentile DOUBLE,
    liquidity_regime VARCHAR,
    confidence VARCHAR,
    component_contributions VARCHAR,
    missing_components VARCHAR,
    freshness_status VARCHAR,
    source_label VARCHAR,
    UNIQUE(symbol, observation_ts)
);

CREATE TABLE IF NOT EXISTS positioning_analytics (
    analytics_run_id VARCHAR,
    internal_asset_id VARCHAR,
    participant_category VARCHAR,
    contract_name VARCHAR,
    report_date TIMESTAMP WITH TIME ZONE,
    publication_date TIMESTAMP WITH TIME ZONE,
    ingested_ts TIMESTAMP WITH TIME ZONE,
    calculation_ts TIMESTAMP WITH TIME ZONE,
    gross_long DOUBLE,
    gross_short DOUBLE,
    net_position DOUBLE,
    one_week_net_change DOUBLE,
    four_week_net_change DOUBLE,
    net_pct_open_interest DOUBLE,
    percentile_52w DOUBLE,
    percentile_3y DOUBLE,
    rolling_zscore DOUBLE,
    open_interest DOUBLE,
    open_interest_change DOUBLE,
    positioning_reversal BOOLEAN,
    crowding_condition VARCHAR,
    price_positioning_divergence BOOLEAN,
    long_liquidation_risk BOOLEAN,
    short_squeeze_risk BOOLEAN,
    confidence VARCHAR,
    source_reference VARCHAR,
    UNIQUE(internal_asset_id, participant_category, report_date)
);

CREATE TABLE IF NOT EXISTS option_analytics (
    analytics_run_id VARCHAR,
    snapshot_id VARCHAR,
    symbol VARCHAR,
    expiration DATE,
    assumption_set VARCHAR,
    calculation_ts TIMESTAMP WITH TIME ZONE,
    quote_timestamp TIMESTAMP WITH TIME ZONE,
    underlying_price DOUBLE,
    days_to_expiration DOUBLE,
    total_call_volume DOUBLE,
    total_put_volume DOUBLE,
    put_call_volume_ratio DOUBLE,
    total_call_open_interest DOUBLE,
    total_put_open_interest DOUBLE,
    put_call_open_interest_ratio DOUBLE,
    atm_implied_volatility DOUBLE,
    median_implied_volatility DOUBLE,
    bid_ask_quality VARCHAR,
    realized_volatility_20d DOUBLE,
    implied_minus_realized_volatility DOUBLE,
    term_structure_slope DOUBLE,
    expected_move DOUBLE,
    expected_move_method VARCHAR,
    put_25_delta_iv DOUBLE,
    call_25_delta_iv DOUBLE,
    risk_reversal_25d DOUBLE,
    downside_skew DOUBLE,
    call_oi_concentration DOUBLE,
    put_oi_concentration DOUBLE,
    call_wall DOUBLE,
    put_wall DOUBLE,
    estimated_gamma_exposure DOUBLE,
    gamma_flip DOUBLE,
    gamma_by_strike VARCHAR,
    gamma_sensitivity VARCHAR,
    condition_label VARCHAR,
    supporting_metrics VARCHAR,
    contradicting_metrics VARCHAR,
    assumptions VARCHAR,
    confidence VARCHAR,
    limitations VARCHAR,
    source_label VARCHAR,
    UNIQUE(snapshot_id, expiration, assumption_set)
);

CREATE TABLE IF NOT EXISTS cross_module_summaries (
    summary_id VARCHAR PRIMARY KEY,
    analytics_run_id VARCHAR,
    as_of_timestamp TIMESTAMP WITH TIME ZONE,
    generated_timestamp TIMESTAMP WITH TIME ZONE,
    overall_market_pressure_regime VARCHAR,
    liquidity_condition VARCHAR,
    volatility_condition VARCHAR,
    major_positioning_risk VARCHAR,
    spy_options_condition VARCHAR,
    qqq_options_condition VARCHAR,
    market_setup VARCHAR,
    supporting_signals VARCHAR,
    contradicting_signals VARCHAR,
    data_limitations VARCHAR,
    indicators_to_monitor VARCHAR,
    confidence VARCHAR,
    source_timestamps VARCHAR
);

CREATE TABLE IF NOT EXISTS indicator_values (
    indicator_value_id VARCHAR PRIMARY KEY,
    indicator_id VARCHAR,
    module VARCHAR,
    as_of_timestamp TIMESTAMP WITH TIME ZONE,
    calculation_timestamp TIMESTAMP WITH TIME ZONE,
    raw_value DOUBLE,
    normalized_value DOUBLE,
    score DOUBLE,
    direction VARCHAR,
    strength VARCHAR,
    confidence VARCHAR,
    freshness VARCHAR,
    evidence_record_ids VARCHAR,
    assumptions VARCHAR,
    failure_cases VARCHAR,
    contradicting_signal_ids VARCHAR,
    quality_status VARCHAR
);

CREATE TABLE IF NOT EXISTS signal_records (
    signal_id VARCHAR PRIMARY KEY,
    indicator_id VARCHAR,
    module VARCHAR,
    calculation_ts TIMESTAMP WITH TIME ZONE,
    as_of_timestamp TIMESTAMP WITH TIME ZONE,
    raw_value DOUBLE,
    normalized_value DOUBLE,
    score DOUBLE,
    direction VARCHAR,
    strength VARCHAR,
    interpretation VARCHAR,
    confidence VARCHAR,
    freshness VARCHAR,
    evidence_record_ids VARCHAR,
    assumptions VARCHAR,
    failure_cases VARCHAR,
    contradicting_signal_ids VARCHAR,
    quality_status VARCHAR
);

CREATE TABLE IF NOT EXISTS evidence_links (
    evidence_id VARCHAR PRIMARY KEY,
    signal_id VARCHAR,
    indicator_id VARCHAR,
    record_ids VARCHAR,
    observation_timestamps VARCHAR,
    availability_timestamps VARCHAR,
    quality_status VARCHAR,
    assumptions VARCHAR,
    limitations VARCHAR,
    source_reference VARCHAR
);

CREATE TABLE IF NOT EXISTS market_context_packets (
    packet_id VARCHAR PRIMARY KEY,
    as_of_timestamp TIMESTAMP WITH TIME ZONE,
    data_cutoff_timestamp TIMESTAMP WITH TIME ZONE,
    generated_timestamp TIMESTAMP WITH TIME ZONE,
    module_summaries VARCHAR,
    signals VARCHAR,
    supporting_signal_ids VARCHAR,
    contradicting_signal_ids VARCHAR,
    evidence_map VARCHAR,
    dataset_freshness VARCHAR,
    missing_critical_datasets VARCHAR,
    stale_critical_datasets VARCHAR,
    assumptions VARCHAR,
    limitations VARCHAR,
    overall_confidence VARCHAR,
    packet_version VARCHAR,
    input_data_hash VARCHAR
);

CREATE TABLE IF NOT EXISTS deterministic_reports (
    report_id VARCHAR PRIMARY KEY,
    packet_id VARCHAR,
    report_as_of TIMESTAMP WITH TIME ZONE,
    generated_timestamp TIMESTAMP WITH TIME ZONE,
    json_path VARCHAR,
    markdown_path VARCHAR,
    json_payload VARCHAR,
    markdown_payload VARCHAR,
    confidence VARCHAR
);

CREATE TABLE IF NOT EXISTS analytics_runs (
    analytics_run_id VARCHAR PRIMARY KEY,
    as_of_timestamp TIMESTAMP WITH TIME ZONE,
    data_cutoff_timestamp TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    modules_requested VARCHAR,
    indicators_calculated VARCHAR,
    signals_produced VARCHAR,
    warnings VARCHAR,
    missing_critical_datasets VARCHAR,
    stale_critical_datasets VARCHAR,
    overall_status VARCHAR,
    error_message VARCHAR
);
"""


@contextmanager
def connect_duckdb(database_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(database_path))
    try:
        connection.execute("BEGIN TRANSACTION")
        yield connection
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def initialize_database(connection: duckdb.DuckDBPyConnection) -> None:
    """Create all required tables when missing."""

    connection.execute(SCHEMA_SQL)
    connection.execute("ALTER TABLE IF EXISTS pipeline_runs ADD COLUMN IF NOT EXISTS pipeline_name VARCHAR")
    connection.execute("ALTER TABLE IF EXISTS pipeline_runs ADD COLUMN IF NOT EXISTS records_received BIGINT")
    connection.execute("ALTER TABLE IF EXISTS pipeline_runs ADD COLUMN IF NOT EXISTS records_validated BIGINT")
    connection.execute("ALTER TABLE IF EXISTS pipeline_runs ADD COLUMN IF NOT EXISTS records_rejected BIGINT")
    connection.execute("ALTER TABLE IF EXISTS pipeline_runs ADD COLUMN IF NOT EXISTS raw_snapshot_location VARCHAR")
    connection.execute("ALTER TABLE IF EXISTS market_observations ADD COLUMN IF NOT EXISTS frequency VARCHAR")
    connection.execute("ALTER TABLE IF EXISTS market_observations ADD COLUMN IF NOT EXISTS adjusted_close_status VARCHAR")
    connection.execute("ALTER TABLE IF EXISTS data_quality_events ADD COLUMN IF NOT EXISTS rule_id VARCHAR")
    connection.execute("ALTER TABLE IF EXISTS dataset_catalog ADD COLUMN IF NOT EXISTS dataset_name VARCHAR")
    connection.execute("ALTER TABLE IF EXISTS dataset_catalog ADD COLUMN IF NOT EXISTS expected_publication_delay_days BIGINT")
    connection.execute("ALTER TABLE IF EXISTS dataset_catalog ADD COLUMN IF NOT EXISTS latest_ingestion_ts TIMESTAMP WITH TIME ZONE")
    connection.execute("ALTER TABLE IF EXISTS dataset_catalog ADD COLUMN IF NOT EXISTS age_days DOUBLE")
    connection.execute("ALTER TABLE IF EXISTS dataset_catalog ADD COLUMN IF NOT EXISTS freshness_status VARCHAR")
    connection.execute("ALTER TABLE IF EXISTS dataset_catalog ADD COLUMN IF NOT EXISTS record_count BIGINT")
    connection.execute("ALTER TABLE IF EXISTS dataset_catalog ADD COLUMN IF NOT EXISTS latest_pipeline_status VARCHAR")
    connection.execute("ALTER TABLE IF EXISTS dataset_catalog ADD COLUMN IF NOT EXISTS warning_message VARCHAR")
    connection.execute("ALTER TABLE IF EXISTS cftc_positioning_observations ADD COLUMN IF NOT EXISTS publication_date TIMESTAMP WITH TIME ZONE")
    connection.execute("ALTER TABLE IF EXISTS cftc_positioning_observations ADD COLUMN IF NOT EXISTS available_ts TIMESTAMP WITH TIME ZONE")
    connection.execute("ALTER TABLE IF EXISTS cftc_positioning_observations ADD COLUMN IF NOT EXISTS source_reference VARCHAR")
    connection.execute("ALTER TABLE IF EXISTS cftc_positioning_observations ADD COLUMN IF NOT EXISTS trader_count DOUBLE")
    connection.execute("ALTER TABLE IF EXISTS indicator_values ADD COLUMN IF NOT EXISTS as_of_timestamp TIMESTAMP WITH TIME ZONE")
    connection.execute("ALTER TABLE IF EXISTS indicator_values ADD COLUMN IF NOT EXISTS calculation_timestamp TIMESTAMP WITH TIME ZONE")
    connection.execute("ALTER TABLE IF EXISTS signal_records ADD COLUMN IF NOT EXISTS as_of_timestamp TIMESTAMP WITH TIME ZONE")
    connection.execute("ALTER TABLE IF EXISTS evidence_links ADD COLUMN IF NOT EXISTS source_reference VARCHAR")
    connection.execute("ALTER TABLE IF EXISTS market_context_packets ADD COLUMN IF NOT EXISTS generated_timestamp TIMESTAMP WITH TIME ZONE")
    connection.execute("ALTER TABLE IF EXISTS deterministic_reports ADD COLUMN IF NOT EXISTS generated_timestamp TIMESTAMP WITH TIME ZONE")
    connection.execute("ALTER TABLE IF EXISTS analytics_runs ADD COLUMN IF NOT EXISTS data_cutoff_timestamp TIMESTAMP WITH TIME ZONE")
    connection.execute(
        """
        CREATE OR REPLACE VIEW market_prices AS
        SELECT * FROM market_observations
        """
    )


def df_to_string(frame: pd.DataFrame) -> pd.DataFrame:
    copied = frame.copy()
    for column in copied.columns:
        if copied[column].dtype == "object":
            copied[column] = copied[column].apply(
                lambda value: json.dumps(value, sort_keys=True, default=str)
                if isinstance(value, (dict, list))
                else ("|".join(value) if column == "quality_flags" and isinstance(value, list) else value)
            )
    return copied


def upsert_dataframe(connection: duckdb.DuckDBPyConnection, table: str, frame: pd.DataFrame, unique_columns: list[str] | None = None) -> None:
    if frame.empty:
        return
    frame = df_to_string(frame)
    if unique_columns:
        frame = frame.drop_duplicates(subset=unique_columns, keep="last").reset_index(drop=True)
    temp_name = f"temp_{table}"
    connection.register(temp_name, frame)
    if unique_columns:
        delete_predicate = " AND ".join([f"{table}.{col} = src.{col}" for col in unique_columns])
        connection.execute(f"DELETE FROM {table} USING {temp_name} AS src WHERE {delete_predicate}")
    column_list = ", ".join(frame.columns)
    connection.execute(f"INSERT INTO {table} ({column_list}) SELECT {column_list} FROM {temp_name}")
    connection.unregister(temp_name)
