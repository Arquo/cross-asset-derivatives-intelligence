"""Evidence mapping and validation utilities."""

from __future__ import annotations

from collections.abc import Iterable

from cross_asset_intelligence.core.exceptions import DataValidationError

from .models import EvidenceRecord


def build_evidence_map(evidence_records: Iterable[EvidenceRecord]) -> dict[str, dict[str, object]]:
    """Build a deterministic evidence lookup by ID."""

    mapping: dict[str, dict[str, object]] = {}
    for record in evidence_records:
        if record.evidence_id in mapping:
            raise DataValidationError(f"Duplicate evidence record detected: {record.evidence_id}")
        mapping[record.evidence_id] = {
            "evidence_id": record.evidence_id,
            "signal_id": record.signal_id,
            "indicator_id": record.indicator_id,
            "record_ids": list(record.record_ids),
            "observation_timestamps": list(record.observation_timestamps),
            "availability_timestamps": list(record.availability_timestamps),
            "quality_status": record.quality_status,
            "assumptions": list(record.assumptions),
            "limitations": list(record.limitations),
            "source_reference": record.source_reference,
        }
    return mapping


def validate_evidence_map(evidence_map: dict[str, dict[str, object]], valid_record_ids: set[str]) -> None:
    """Ensure every evidence reference points to an existing record."""

    for evidence_id, payload in evidence_map.items():
        for record_id in payload.get("record_ids", []):
            if record_id not in valid_record_ids:
                raise DataValidationError(f"Evidence {evidence_id} references missing record {record_id}.")

