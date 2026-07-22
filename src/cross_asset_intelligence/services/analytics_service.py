"""Prepared analytical views built from validated DuckDB data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from cross_asset_intelligence.analytics.cross_asset.indicators import build_cross_asset_summary
from cross_asset_intelligence.analytics.liquidity.indicators import build_liquidity_components, build_liquidity_summary
from cross_asset_intelligence.analytics.macro.indicators import SeriesSnapshot, build_macro_regime_result
from cross_asset_intelligence.analytics.positioning.indicators import build_positioning_summary, compute_positioning_metrics
from cross_asset_intelligence.core.config import load_phase3_config, load_pipeline_config
from cross_asset_intelligence.core.constants import ConfidenceLevel, SignalDirection, QualityStatus
from cross_asset_intelligence.evidence.models import EvidenceRecord, MarketContextPacket
from cross_asset_intelligence.indicators.normalization import normalize_indicator_value, signal_strength
from cross_asset_intelligence.indicators.registry import load_indicator_registry
from cross_asset_intelligence.pipelines.normalization import make_record_id, utc_now
from cross_asset_intelligence.schemas.signals import SignalRecord
from cross_asset_intelligence.storage.repositories import DuckDBRepository
from cross_asset_intelligence.strategist.context_builder import build_market_context_packet


@dataclass(frozen=True)
class AnalyticsSnapshot:
    """Prepared data for dashboard pages."""

    macro: pd.DataFrame
    positioning: pd.DataFrame
    liquidity: pd.DataFrame
    cross_asset: pd.DataFrame
    signals: pd.DataFrame
    evidence: pd.DataFrame
    packet: MarketContextPacket | None


class AnalyticsService:
    """Read-only service that transforms stored observations into analytics views."""

    def __init__(self, database_path: Path, root_dir: Path | None = None) -> None:
        self.repository = DuckDBRepository(database_path)
        self.root_dir = root_dir or Path.cwd()
        self.pipeline_config = load_pipeline_config(self.root_dir)
        self.phase3_config = load_phase3_config(self.root_dir)
        self.indicator_registry = load_indicator_registry(self.root_dir)

    def has_database(self) -> bool:
        return self.repository.database_path.exists()

    def _as_of_filter(self, column: str, as_of: pd.Timestamp | None) -> tuple[str, tuple]:
        if as_of is None or pd.isna(as_of):
            return "", tuple()
        ts = pd.Timestamp(as_of)
        if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return f" AND {column} <= ?", (ts,)

    def _fetch_filtered(self, query: str, params: Iterable[object] = ()) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        return self.repository.fetch_dataframe(query, tuple(params))

    def market_history(self, symbols: Iterable[str], as_of: pd.Timestamp | None = None) -> pd.DataFrame:
        symbols = list(symbols)
        if not symbols or not self.has_database():
            return pd.DataFrame()
        placeholders = ",".join(["?"] * len(symbols))
        as_of_clause, extra_params = self._as_of_filter("observation_ts", as_of)
        query = f"""
            SELECT *
            FROM market_observations
            WHERE symbol IN ({placeholders})
            {as_of_clause}
            ORDER BY symbol, observation_ts
        """
        return self._fetch_filtered(query, (*symbols, *extra_params))

    def macro_history(self, series_ids: Iterable[str], as_of: pd.Timestamp | None = None) -> pd.DataFrame:
        series_ids = list(series_ids)
        if not series_ids or not self.has_database():
            return pd.DataFrame()
        placeholders = ",".join(["?"] * len(series_ids))
        as_of_clause, extra_params = self._as_of_filter("available_ts", as_of)
        query = f"""
            SELECT *
            FROM macro_observations
            WHERE series_id IN ({placeholders})
            {as_of_clause}
            ORDER BY series_id, observation_ts
        """
        return self._fetch_filtered(query, (*series_ids, *extra_params))

    def cftc_history(self, internal_asset_ids: Iterable[str] | None = None, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        clauses = []
        params: list[object] = []
        if internal_asset_ids:
            internal_asset_ids = list(internal_asset_ids)
            placeholders = ",".join(["?"] * len(internal_asset_ids))
            clauses.append(f"internal_asset_id IN ({placeholders})")
            params.extend(internal_asset_ids)
        as_of_clause, extra_params = self._as_of_filter("available_ts", as_of)
        where = " AND ".join(["1=1", *clauses]) + as_of_clause
        query = f"""
            SELECT *
            FROM cftc_positioning_observations
            WHERE {where}
            ORDER BY internal_asset_id, report_date
        """
        return self._fetch_filtered(query, (*params, *extra_params))

    def latest_macro_regime(self, as_of: pd.Timestamp | None = None) -> dict[str, Any]:
        series_ids = [series.series_id for series in self.pipeline_config.fred_series if series.enabled]
        history = self.macro_history(series_ids, as_of=as_of)
        series_map = {}
        for series_id in series_ids:
            frame = history[history["series_id"] == series_id].copy() if not history.empty else pd.DataFrame()
            series_frame = frame.rename(columns={"observation_ts": "date", "value": "value"})[["date", "value"]] if not frame.empty else pd.DataFrame(columns=["date", "value"])
            date_series = pd.to_datetime(series_frame["date"], utc=True, errors="coerce") if not series_frame.empty else pd.Series(dtype="datetime64[ns, UTC]")
            value_series = pd.to_numeric(series_frame["value"], errors="coerce").dropna() if not series_frame.empty else pd.Series(dtype="float64")
            latest_date = date_series.dropna().max() if not date_series.empty else None
            latest_value = float(value_series.iloc[-1]) if not value_series.empty else None
            series_map[series_id] = SeriesSnapshot(
                series_id=series_id,
                title=series_id,
                frequency="Unknown",
                latest_value=float(latest_value) if latest_value is not None and not pd.isna(latest_value) else None,
                latest_observation_date=pd.Timestamp(latest_date) if latest_date is not None and not pd.isna(latest_date) else None,
                data_status="Available" if not series_frame.empty else "Unavailable",
                frame=series_frame,
                metadata=None,
            )
        if not series_map:
            return {}
        result = build_macro_regime_result(series_map)
        return {
            "result": result,
            "summary": result.summary.to_dict(orient="records"),
            "indicators": result.indicators,
            "latest_timestamp": result.latest_observation_timestamp,
        }

    def latest_positioning(self, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
        frame = self.cftc_history(as_of=as_of)
        if frame.empty:
            return frame
        metrics = compute_positioning_metrics(frame)
        return build_positioning_summary(metrics)

    def latest_liquidity(self, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
        market = self.market_history([symbol.internal_symbol for symbol in self.pipeline_config.market_symbols if symbol.enabled], as_of=as_of)
        macro = self.macro_history([series.series_id for series in self.pipeline_config.fred_series if series.enabled], as_of=as_of)
        return build_liquidity_summary(market, macro)

    def latest_cross_asset(self, left_symbol: str, right_symbol: str, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
        market = self.market_history([left_symbol, right_symbol], as_of=as_of)
        return build_cross_asset_summary(market, market, left_symbol=left_symbol, right_symbol=right_symbol)

    def build_signals(self, as_of: pd.Timestamp | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Build standardized signal and evidence records."""

        signals: list[dict[str, Any]] = []
        evidence: list[EvidenceRecord] = []
        calculation_ts = pd.Timestamp.now(tz="UTC")

        macro = self.latest_macro_regime(as_of=as_of)
        macro_result = macro.get("result")
        if macro_result is not None:
            macro_signal = self._signal_from_text(
                indicator_id="macro_regime",
                module="macro",
                label=macro_result.overall_macro_regime,
                interpretation=f"Macro regime: {macro_result.overall_macro_regime}",
                raw_value=macro_result.overall_macro_regime,
                calculation_ts=calculation_ts,
                evidence_ids=[],
            )
            if macro_signal is not None:
                signals.append(macro_signal.model_dump(mode="json"))

        positioning = self.latest_positioning(as_of=as_of)
        if not positioning.empty and "net_pct_open_interest" in positioning.columns:
            latest = positioning.sort_values("report_date").groupby(["internal_asset_id", "participant_category"], sort=False).tail(1)
            for _, row in latest.iterrows():
                score = float(row.get("net_pct_open_interest") or 0)
                direction = SignalDirection.bullish if score > 0 else SignalDirection.bearish if score < 0 else SignalDirection.neutral
                signal = SignalRecord(
                    signal_id=make_record_id("signal", row["internal_asset_id"], row["participant_category"], row["report_date"]),
                    indicator_id="cftc_crowding_score",
                    module="positioning",
                    calculation_ts=calculation_ts.to_pydatetime(),
                    raw_value=float(row.get("net_pct_open_interest")) if pd.notna(row.get("net_pct_open_interest")) else None,
                    normalized_value=float(row.get("historical_percentile_52w")) if pd.notna(row.get("historical_percentile_52w")) else None,
                    score=max(min(score, 1.0), -1.0),
                    direction=direction,
                    strength=signal_strength(score, self.indicator_registry.thresholds),
                    interpretation=f"{row['internal_asset_id']} {row['participant_category']} positioning is {row.get('crowding_bucket')}",
                    confidence=ConfidenceLevel.medium if pd.notna(row.get("historical_percentile_52w")) else ConfidenceLevel.low,
                    freshness="weekly" if pd.notna(row.get("report_date")) else "missing",
                    evidence_record_ids=[],
                    assumptions=["CFTC availability date approximated from weekly release schedule."],
                    failure_cases=["Insufficient history", "Missing contract mapping"],
                    contradicting_signal_ids=[],
                )
                signals.append(signal.model_dump(mode="json"))
                evidence.append(
                    EvidenceRecord(
                        evidence_id=make_record_id("evidence", signal.signal_id),
                        signal_id=signal.signal_id,
                        indicator_id=signal.indicator_id,
                        record_ids=[str(row["record_id"])],
                        observation_timestamps=[pd.Timestamp(row["report_date"]).isoformat()],
                        availability_timestamps=[pd.Timestamp(row["publication_date"]).isoformat()],
                        quality_status=str(row.get("quality_status", "")),
                        assumptions=["Publication date is modeled from the CFTC weekly release cadence."],
                        limitations=["CFTC data is weekly and delayed."],
                        source_reference=str(row.get("source_reference", "")),
                    )
                )

        liquidity = self.latest_liquidity(as_of=as_of)
        if not liquidity.empty and "liquidity_stress_score" in liquidity.columns:
            row = liquidity.iloc[0]
            signal = self._signal_from_numeric(
                indicator_id="liquidity_proxy",
                module="liquidity",
                raw_value=float(row.get("liquidity_stress_score")) if pd.notna(row.get("liquidity_stress_score")) else None,
                calculation_ts=calculation_ts,
                evidence_ids=[],
                interpretation=f"Liquidity regime: {row.get('liquidity_regime')}",
                freshness="daily",
            )
            if signal is not None:
                signals.append(signal.model_dump(mode="json"))

        signals_frame = pd.DataFrame(signals)
        evidence_frame = pd.DataFrame([{
            "evidence_id": item.evidence_id,
            "signal_id": item.signal_id,
            "indicator_id": item.indicator_id,
            "record_ids": item.record_ids,
            "observation_timestamps": item.observation_timestamps,
            "availability_timestamps": item.availability_timestamps,
            "quality_status": item.quality_status,
            "assumptions": item.assumptions,
            "limitations": item.limitations,
            "source_reference": item.source_reference,
        } for item in evidence])
        return signals_frame, evidence_frame

    def _signal_from_numeric(
        self,
        *,
        indicator_id: str,
        module: str,
        raw_value: float | None,
        calculation_ts: pd.Timestamp,
        evidence_ids: list[str],
        interpretation: str,
        freshness: str,
    ) -> SignalRecord | None:
        if raw_value is None or pd.isna(raw_value):
            return None
        definition = self.indicator_registry.get(indicator_id)
        normalized = normalize_indicator_value(raw_value, definition)
        score = normalized if normalized is not None else 0.0
        direction = SignalDirection.bullish if score > 0 else SignalDirection.bearish if score < 0 else SignalDirection.neutral
        return SignalRecord(
            signal_id=make_record_id("signal", indicator_id, module, calculation_ts.isoformat()),
            indicator_id=indicator_id,
            module=module,
            calculation_ts=calculation_ts.to_pydatetime(),
            raw_value=raw_value,
            normalized_value=normalized,
            score=float(max(min(score, 1.0), -1.0)),
            direction=direction,
            strength=signal_strength(score, self.indicator_registry.thresholds),
            interpretation=interpretation,
            confidence=ConfidenceLevel.medium,
            freshness=freshness,
            evidence_record_ids=evidence_ids,
            assumptions=[],
            failure_cases=list(definition.failure_cases),
            contradicting_signal_ids=[],
        )

    def _signal_from_text(
        self,
        *,
        indicator_id: str,
        module: str,
        label: str,
        interpretation: str,
        raw_value: object,
        calculation_ts: pd.Timestamp,
        evidence_ids: list[str],
    ) -> SignalRecord | None:
        mapping = {
            "Goldilocks": 0.9,
            "Reflation": 0.6,
            "Disinflationary slowdown": -0.6,
            "Stagflation risk": -0.9,
            "Recessionary": -0.8,
            "Liquidity-driven risk-on": 0.7,
            "Liquidity contraction": -0.7,
            "Mixed / transitioning": 0.0,
        }
        score = mapping.get(label)
        if score is None:
            return None
        direction = SignalDirection.bullish if score > 0 else SignalDirection.bearish if score < 0 else SignalDirection.mixed
        return SignalRecord(
            signal_id=make_record_id("signal", indicator_id, module, calculation_ts.isoformat()),
            indicator_id=indicator_id,
            module=module,
            calculation_ts=calculation_ts.to_pydatetime(),
            raw_value=raw_value,
            normalized_value=score,
            score=score,
            direction=direction,
            strength=signal_strength(score, self.indicator_registry.thresholds),
            interpretation=interpretation,
            confidence=ConfidenceLevel.medium,
            freshness="daily",
            evidence_record_ids=evidence_ids,
            assumptions=[],
            failure_cases=[],
            contradicting_signal_ids=[],
        )

    def build_snapshot(self, as_of: pd.Timestamp | None = None) -> AnalyticsSnapshot:
        """Build prepared analytics for the dashboard."""

        macro = self.latest_macro_regime(as_of=as_of)
        positioning = self.latest_positioning(as_of=as_of)
        liquidity = self.latest_liquidity(as_of=as_of)
        cross_asset = self.latest_cross_asset("SPY", "TLT", as_of=as_of)
        signals, evidence = self.build_signals(as_of=as_of)
        packet = None
        if not signals.empty or not evidence.empty:
            as_of_ts = pd.Timestamp(as_of or pd.Timestamp.now(tz="UTC"))
            if as_of_ts.tzinfo is None or as_of_ts.tzinfo.utcoffset(as_of_ts) is None:
                as_of_ts = as_of_ts.tz_localize("UTC")
            else:
                as_of_ts = as_of_ts.tz_convert("UTC")
            packet = build_market_context_packet(
                as_of_timestamp=as_of_ts,
                data_cutoff_timestamp=as_of_ts,
                generated_timestamp=utc_now(),
                module_summaries={
                    "macro": macro.get("summary", []),
                    "positioning": positioning.to_dict(orient="records"),
                    "liquidity": liquidity.to_dict(orient="records"),
                    "cross_asset": cross_asset.to_dict(orient="records"),
                    "executive_summary": "Deterministic summary generated from stored validated observations.",
                    "key_risks": [
                        "CFTC data is weekly and delayed.",
                        "Liquidity and cross-asset modules rely on proxies.",
                    ],
                    "indicators_to_monitor": ["CPI", "UNRATE", "DGS10", "HYG", "VIX"],
                },
                signal_rows=signals.to_dict(orient="records"),
                evidence_records=[
                    EvidenceRecord(
                        evidence_id=row["evidence_id"],
                        signal_id=row["signal_id"],
                        indicator_id=row["indicator_id"],
                        record_ids=list(row["record_ids"]),
                        observation_timestamps=list(row["observation_timestamps"]),
                        availability_timestamps=list(row["availability_timestamps"]),
                        quality_status=row["quality_status"],
                        assumptions=list(row["assumptions"]),
                        limitations=list(row["limitations"]),
                        source_reference=row.get("source_reference"),
                    )
                    for row in evidence.to_dict(orient="records")
                ],
                dataset_freshness=self.repository.fetch_dataframe("SELECT * FROM dataset_catalog ORDER BY dataset_id").to_dict(orient="records"),
                missing_critical_datasets=[],
                stale_critical_datasets=[],
                assumptions=["Historical vintage limitations apply to Phase 2 FRED data."],
                limitations=["No options analytics or AI strategist in this phase."],
                packet_version=self.phase3_config.report_settings.packet_version,
            )
        return AnalyticsSnapshot(
            macro=pd.DataFrame(macro.get("summary", [])),
            positioning=positioning,
            liquidity=liquidity,
            cross_asset=cross_asset,
            signals=signals,
            evidence=evidence,
            packet=packet,
        )
