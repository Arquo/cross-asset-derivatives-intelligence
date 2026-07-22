"""Evidence and packet models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any

from cross_asset_intelligence.core.constants import ConfidenceLevel


def _stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))


@dataclass(frozen=True)
class EvidenceRecord:
    """Traceable evidence for a signal or conclusion."""

    evidence_id: str
    signal_id: str
    indicator_id: str
    record_ids: list[str]
    observation_timestamps: list[str]
    availability_timestamps: list[str]
    quality_status: str
    assumptions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    source_reference: str | None = None


@dataclass(frozen=True)
class MarketContextPacket:
    """Deterministic analytics packet."""

    packet_id: str
    as_of_timestamp: str
    data_cutoff_timestamp: str
    generated_timestamp: str
    module_summaries: dict[str, Any]
    signals: list[dict[str, Any]]
    supporting_signal_ids: list[str]
    contradicting_signal_ids: list[str]
    evidence_map: dict[str, dict[str, Any]]
    dataset_freshness: dict[str, Any]
    missing_critical_datasets: list[str]
    stale_critical_datasets: list[str]
    assumptions: list[str]
    limitations: list[str]
    overall_confidence: ConfidenceLevel
    packet_version: str
    input_data_hash: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        confidence = self.overall_confidence
        data["overall_confidence"] = confidence.value if hasattr(confidence, "value") else str(confidence)
        return data

    def stable_hash(self) -> str:
        return sha256(_stable_json(self.to_dict()).encode("utf-8")).hexdigest()
