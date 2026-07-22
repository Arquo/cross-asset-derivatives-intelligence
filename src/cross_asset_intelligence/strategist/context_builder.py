"""Build deterministic market context packets."""

from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
from typing import Any

import pandas as pd

from cross_asset_intelligence.core.constants import ConfidenceLevel, SignalDirection
from cross_asset_intelligence.evidence.mapper import build_evidence_map, validate_evidence_map
from cross_asset_intelligence.evidence.models import EvidenceRecord, MarketContextPacket
from cross_asset_intelligence.indicators.normalization import bounded_score, signal_strength
from cross_asset_intelligence.indicators.thresholds import SignalThresholds


def _stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))


def _confidence_from_signals(signals: list[dict[str, Any]], missing: list[str], stale: list[str]) -> ConfidenceLevel:
    if not signals or len(missing) > 2:
        return ConfidenceLevel.low
    score = sum(abs(float(signal.get("score", 0.0))) for signal in signals if signal.get("score") is not None) / max(len(signals), 1)
    if stale:
        score -= 0.2
    if score >= 0.67:
        return ConfidenceLevel.high
    if score >= 0.33:
        return ConfidenceLevel.medium
    return ConfidenceLevel.low


def build_market_context_packet(
    *,
    as_of_timestamp: pd.Timestamp,
    data_cutoff_timestamp: pd.Timestamp,
    generated_timestamp: pd.Timestamp,
    module_summaries: dict[str, Any],
    signal_rows: list[dict[str, Any]],
    evidence_records: list[EvidenceRecord],
    dataset_freshness: dict[str, Any],
    missing_critical_datasets: list[str],
    stale_critical_datasets: list[str],
    assumptions: list[str],
    limitations: list[str],
    packet_version: str,
) -> MarketContextPacket:
    """Create a deterministic market-context packet."""

    evidence_map = build_evidence_map(evidence_records)
    valid_record_ids = {record_id for record in evidence_map.values() for record_id in record.get("record_ids", [])}
    validate_evidence_map(evidence_map, valid_record_ids)
    sorted_signals = sorted(signal_rows, key=lambda item: item["signal_id"])
    packet_hash = sha256(_stable_json({"signals": sorted_signals, "evidence": evidence_map, "freshness": dataset_freshness}).encode("utf-8")).hexdigest()
    packet = MarketContextPacket(
        packet_id=sha256(f"{as_of_timestamp.isoformat()}|{data_cutoff_timestamp.isoformat()}|{packet_version}".encode("utf-8")).hexdigest()[:32],
        as_of_timestamp=as_of_timestamp.isoformat(),
        data_cutoff_timestamp=data_cutoff_timestamp.isoformat(),
        generated_timestamp=generated_timestamp.isoformat(),
        module_summaries=module_summaries,
        signals=sorted_signals,
        supporting_signal_ids=[signal["signal_id"] for signal in sorted_signals if float(signal.get("score") or 0) > 0],
        contradicting_signal_ids=[signal["signal_id"] for signal in sorted_signals if float(signal.get("score") or 0) < 0],
        evidence_map=evidence_map,
        dataset_freshness=dataset_freshness,
        missing_critical_datasets=sorted(missing_critical_datasets),
        stale_critical_datasets=sorted(stale_critical_datasets),
        assumptions=sorted(set(assumptions)),
        limitations=sorted(set(limitations)),
        overall_confidence=_confidence_from_signals(sorted_signals, missing_critical_datasets, stale_critical_datasets),
        packet_version=packet_version,
        input_data_hash=packet_hash,
    )
    return packet

