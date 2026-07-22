"""Persisted market-intelligence analytics orchestration and read models."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from uuid import uuid4

import pandas as pd

from cross_asset_intelligence.analytics.liquidity.indicators import build_liquidity_analytics
from cross_asset_intelligence.analytics.options.calculations import analyze_options_snapshots
from cross_asset_intelligence.analytics.positioning.indicators import compute_positioning_metrics
from cross_asset_intelligence.analytics.screener.metrics import build_screener
from cross_asset_intelligence.analytics.summary import build_cross_module_summary
from cross_asset_intelligence.core.config import load_pipeline_config
from cross_asset_intelligence.pipelines.normalization import make_record_id
from cross_asset_intelligence.storage.repositories import DuckDBRepository


CFTC_MARKET_MAP = {
    "sp500": "SPY",
    "nasdaq": "QQQ",
    "russell_2000": "IWM",
    "us_2y": "TLT",
    "us_5y": "TLT",
    "us_10y": "TLT",
    "us_long_bond": "TLT",
    "dxy": "UUP",
    "gold": "GLD",
    "crude_oil": "USO",
}


@dataclass(frozen=True)
class IntelligenceSnapshot:
    analytics_run_id: str
    screener: pd.DataFrame
    liquidity: pd.DataFrame
    positioning: pd.DataFrame
    options: pd.DataFrame
    summary: pd.DataFrame


class MarketIntelligenceService:
    """Calculate, persist, and query the useful market-intelligence slice."""

    def __init__(self, database_path: Path, root_dir: Path | None = None) -> None:
        self.repository = DuckDBRepository(database_path)
        self.root_dir = root_dir or Path.cwd()

    @staticmethod
    def _as_utc(value: object | None) -> pd.Timestamp | None:
        if value is None:
            return None
        timestamp = pd.Timestamp(value)
        return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")

    def _market_history(self, as_of: pd.Timestamp | None) -> pd.DataFrame:
        if as_of is None:
            return self.repository.fetch_dataframe("SELECT * FROM market_observations ORDER BY symbol, observation_ts")
        return self.repository.fetch_dataframe(
            "SELECT * FROM market_observations WHERE observation_ts <= ? ORDER BY symbol, observation_ts",
            (as_of,),
        )

    def _positioning_history(self, as_of: pd.Timestamp | None) -> pd.DataFrame:
        if as_of is None:
            return self.repository.fetch_dataframe("SELECT * FROM cftc_positioning_observations ORDER BY internal_asset_id, participant_category, report_date")
        return self.repository.fetch_dataframe(
            "SELECT * FROM cftc_positioning_observations WHERE available_ts <= ? ORDER BY internal_asset_id, participant_category, report_date",
            (as_of,),
        )

    def _latest_option_contracts(self, as_of: pd.Timestamp | None) -> pd.DataFrame:
        where = "" if as_of is None else "WHERE quote_timestamp <= ?"
        params = () if as_of is None else (as_of,)
        return self.repository.fetch_dataframe(
            f"""
            WITH snapshots AS (
                SELECT DISTINCT symbol, snapshot_id, quote_timestamp
                FROM option_contract_snapshots
                {where}
            ), latest AS (
                SELECT symbol, snapshot_id
                FROM snapshots
                QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY quote_timestamp DESC) = 1
            )
            SELECT contracts.*
            FROM option_contract_snapshots contracts
            INNER JOIN latest USING (symbol, snapshot_id)
            ORDER BY symbol, expiration, option_type, strike
            """,
            params,
        )

    @staticmethod
    def _positioning_price_history(market: pd.DataFrame) -> pd.DataFrame:
        frames = []
        for asset_id, symbol in CFTC_MARKET_MAP.items():
            subset = market[market["symbol"] == symbol].copy()
            if subset.empty:
                continue
            subset["asset_id"] = asset_id
            frames.append(subset)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    @staticmethod
    def _prepare_positioning_for_storage(frame: pd.DataFrame, analytics_run_id: str) -> pd.DataFrame:
        if frame.empty:
            return frame
        output = frame.rename(
            columns={
                "historical_percentile_52w": "percentile_52w",
                "historical_percentile_3y": "percentile_3y",
            }
        ).copy()
        output["analytics_run_id"] = analytics_run_id
        columns = [
            "analytics_run_id",
            "internal_asset_id",
            "participant_category",
            "contract_name",
            "report_date",
            "publication_date",
            "ingested_ts",
            "calculation_ts",
            "gross_long",
            "gross_short",
            "net_position",
            "one_week_net_change",
            "four_week_net_change",
            "net_pct_open_interest",
            "percentile_52w",
            "percentile_3y",
            "rolling_zscore",
            "open_interest",
            "open_interest_change",
            "positioning_reversal",
            "crowding_condition",
            "price_positioning_divergence",
            "long_liquidation_risk",
            "short_squeeze_risk",
            "confidence",
            "source_reference",
        ]
        for column in columns:
            if column not in output.columns:
                output[column] = pd.NA
        return output[columns]

    @staticmethod
    def _positioning_lookup(positioning: pd.DataFrame) -> dict[str, dict[str, object]]:
        if positioning.empty:
            return {}
        latest = positioning.sort_values("report_date").groupby(["internal_asset_id", "participant_category"], sort=False).tail(1)
        lookup: dict[str, dict[str, object]] = {}
        for asset_id, symbol in CFTC_MARKET_MAP.items():
            rows = latest[latest["internal_asset_id"] == asset_id]
            if rows.empty:
                continue
            preferred = rows[rows["participant_category"].isin(["Leveraged funds", "Managed money"])]
            row = preferred.iloc[0] if not preferred.empty else rows.iloc[0]
            percentile = pd.to_numeric(pd.Series([row.get("percentile_52w")]), errors="coerce").iloc[0]
            lookup[symbol] = {
                "classification": row.get("crowding_condition", "Unavailable"),
                "score": None if pd.isna(percentile) else float((percentile - 0.5) * 200.0),
            }
        return lookup

    @staticmethod
    def _option_lookup(options: pd.DataFrame) -> dict[str, dict[str, object]]:
        lookup: dict[str, dict[str, object]] = {}
        if options.empty:
            return lookup
        default = options[options["assumption_set"] == "calls_positive_puts_negative"].copy()
        for symbol, rows in default.groupby("symbol", sort=False):
            eligible = rows[pd.to_numeric(rows["days_to_expiration"], errors="coerce") >= 7]
            row = (eligible if not eligible.empty else rows).sort_values("days_to_expiration").iloc[0]
            lookup[str(symbol)] = {"classification": row.get("condition_label", "Unavailable")}
        return lookup

    def run(self, *, as_of: object | None = None) -> IntelligenceSnapshot:
        """Run all calculations once and persist their prepared outputs."""

        self.repository.initialize()
        started_at = pd.Timestamp.now(tz="UTC")
        as_of_ts = self._as_utc(as_of)
        analytics_run_id = uuid4().hex
        market = self._market_history(as_of_ts)
        cftc = self._positioning_history(as_of_ts)
        option_contracts = self._latest_option_contracts(as_of_ts)
        config = load_pipeline_config(self.root_dir)
        asset_classes = {item.internal_symbol: item.asset_class for item in config.market_symbols if item.enabled}

        positioning_metrics = compute_positioning_metrics(cftc, price_history=self._positioning_price_history(market))
        positioning = self._prepare_positioning_for_storage(positioning_metrics, analytics_run_id)
        options = analyze_options_snapshots(option_contracts, market, analytics_run_id=analytics_run_id)
        liquidity = build_liquidity_analytics(market, analytics_run_id=analytics_run_id, reference_time=as_of_ts)
        screener = build_screener(
            market,
            asset_classes=asset_classes,
            positioning=self._positioning_lookup(positioning),
            options=self._option_lookup(options),
            reference_time=as_of_ts,
            analytics_run_id=analytics_run_id,
        )

        if not screener.empty:
            pressure = screener[
                [
                    "analytics_run_id",
                    "symbol",
                    "observation_ts",
                    "calculation_ts",
                    "market_pressure_score",
                    "pressure_label",
                    "pressure_confidence",
                    "score_components",
                    "missing_components",
                    "source_label",
                ]
            ].rename(
                columns={
                    "market_pressure_score": "score",
                    "pressure_label": "label",
                    "pressure_confidence": "confidence",
                    "score_components": "components",
                }
            )
            pressure["available_weight"] = pressure["components"].apply(
                lambda value: sum(item.get("base_weight", 0.0) for item in json.loads(value or "[]"))
            )
            pressure = pressure[
                [
                    "analytics_run_id",
                    "symbol",
                    "observation_ts",
                    "calculation_ts",
                    "score",
                    "label",
                    "confidence",
                    "components",
                    "missing_components",
                    "available_weight",
                    "source_label",
                ]
            ]
        else:
            pressure = pd.DataFrame()

        summary_payload = build_cross_module_summary(screener, liquidity, positioning, options)
        data_cutoff_candidates = []
        for frame, column in [(market, "observation_ts"), (cftc, "available_ts"), (option_contracts, "quote_timestamp")]:
            if not frame.empty and column in frame.columns:
                data_cutoff_candidates.append(pd.to_datetime(frame[column], utc=True, errors="coerce").max())
        data_cutoff = max((value for value in data_cutoff_candidates if pd.notna(value)), default=as_of_ts or started_at)
        summary_id = make_record_id("cross_module_summary", data_cutoff.isoformat(), json.dumps(summary_payload, sort_keys=True, default=str))
        summary = pd.DataFrame(
            [
                {
                    "summary_id": summary_id,
                    "analytics_run_id": analytics_run_id,
                    "as_of_timestamp": as_of_ts or data_cutoff,
                    "generated_timestamp": pd.Timestamp.now(tz="UTC"),
                    "overall_market_pressure_regime": summary_payload["overall_market_pressure_regime"],
                    "liquidity_condition": summary_payload["liquidity_condition"],
                    "volatility_condition": summary_payload["volatility_condition"],
                    "major_positioning_risk": summary_payload["major_positioning_risk"],
                    "spy_options_condition": summary_payload["spy_options_condition"],
                    "qqq_options_condition": summary_payload["qqq_options_condition"],
                    "market_setup": json.dumps(summary_payload["market_setup"], sort_keys=True),
                    "supporting_signals": json.dumps(summary_payload["supporting_signals"]),
                    "contradicting_signals": json.dumps(summary_payload["contradicting_signals"]),
                    "data_limitations": json.dumps(summary_payload["data_limitations"]),
                    "indicators_to_monitor": json.dumps(summary_payload["indicators_to_monitor"]),
                    "confidence": summary_payload["confidence"],
                    "source_timestamps": json.dumps(summary_payload["source_timestamps"], sort_keys=True),
                }
            ]
        )

        if not liquidity.empty:
            self.repository.insert_liquidity_analytics(liquidity)
        if not positioning.empty:
            self.repository.insert_positioning_analytics(positioning)
        if not options.empty:
            self.repository.insert_option_analytics(options)
        if not screener.empty:
            self.repository.insert_screener_results(screener)
        if not pressure.empty:
            self.repository.insert_market_pressure_scores(pressure)
        self.repository.insert_cross_module_summaries(summary)

        warnings = []
        if market.empty:
            warnings.append("market observations missing")
        if cftc.empty:
            warnings.append("CFTC observations missing")
        if option_contracts.empty:
            warnings.append("option snapshots missing")
        completed_at = pd.Timestamp.now(tz="UTC")
        self.repository.insert_analytics_runs(
            pd.DataFrame(
                [
                    {
                        "analytics_run_id": analytics_run_id,
                        "as_of_timestamp": as_of_ts or data_cutoff,
                        "data_cutoff_timestamp": data_cutoff,
                        "started_at": started_at,
                        "completed_at": completed_at,
                        "modules_requested": "screener,liquidity,positioning,options,summary",
                        "indicators_calculated": len(screener) + len(liquidity) + len(positioning) + len(options),
                        "signals_produced": len(screener),
                        "warnings": json.dumps(warnings),
                        "missing_critical_datasets": json.dumps(warnings),
                        "stale_critical_datasets": json.dumps([]),
                        "overall_status": "completed_with_warnings" if warnings else "completed",
                        "error_message": None,
                    }
                ]
            )
        )
        return IntelligenceSnapshot(analytics_run_id, screener, liquidity, positioning, options, summary)

    def latest_screener(self) -> pd.DataFrame:
        return self.repository.fetch_dataframe("SELECT * FROM screener_results ORDER BY market_pressure_score DESC NULLS LAST")

    def liquidity_history(self) -> pd.DataFrame:
        return self.repository.fetch_dataframe("SELECT * FROM liquidity_analytics ORDER BY symbol, observation_ts")

    def positioning_history(self) -> pd.DataFrame:
        return self.repository.fetch_dataframe("SELECT * FROM positioning_analytics ORDER BY internal_asset_id, participant_category, report_date")

    def raw_positioning_history(self) -> pd.DataFrame:
        return self._positioning_history(None)

    def latest_option_analytics(self) -> pd.DataFrame:
        return self.repository.fetch_dataframe(
            """
            SELECT * FROM option_analytics
            WHERE snapshot_id IN (
                SELECT snapshot_id FROM (
                    SELECT DISTINCT symbol, snapshot_id, quote_timestamp FROM option_analytics
                    QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY quote_timestamp DESC) = 1
                )
            )
            ORDER BY symbol, expiration, assumption_set
            """
        )

    def latest_option_contracts(self) -> pd.DataFrame:
        return self._latest_option_contracts(None)

    def latest_summary(self) -> pd.DataFrame:
        return self.repository.fetch_dataframe("SELECT * FROM cross_module_summaries ORDER BY generated_timestamp DESC LIMIT 1")

    def latest_runs(self) -> pd.DataFrame:
        return self.repository.fetch_dataframe("SELECT * FROM analytics_runs ORDER BY completed_at DESC LIMIT 10")

    def market_history(self) -> pd.DataFrame:
        return self._market_history(None)

    def latest_pipeline_attempt(self, provider: str) -> pd.DataFrame:
        return self.repository.fetch_dataframe(
            "SELECT * FROM pipeline_runs WHERE provider = ? ORDER BY started_at DESC LIMIT 1",
            (provider,),
        )
