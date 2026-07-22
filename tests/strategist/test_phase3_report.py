from __future__ import annotations

from pathlib import Path

import pandas as pd

from cross_asset_intelligence.core.constants import ConfidenceLevel
from cross_asset_intelligence.evidence.mapper import build_evidence_map, validate_evidence_map
from cross_asset_intelligence.evidence.models import EvidenceRecord, MarketContextPacket
from cross_asset_intelligence.strategist.deterministic_report import build_report_markdown, build_report_payload


def _packet(**overrides) -> MarketContextPacket:
    base = MarketContextPacket(
        packet_id="packet-001",
        as_of_timestamp="2024-01-10T00:00:00+00:00",
        data_cutoff_timestamp="2024-01-10T00:00:00+00:00",
        generated_timestamp="2024-01-10T00:01:00+00:00",
        module_summaries={
            "executive_summary": "Deterministic summary",
            "macro": [{"label": "Overall macro regime", "value": "Goldilocks"}],
            "positioning": [],
            "market_trends": [],
            "liquidity": [],
            "cross_asset": [],
            "key_risks": ["Weekly CFTC delay"],
            "indicators_to_monitor": ["CPI"],
        },
        signals=[
            {
                "signal_id": "sig-001",
                "indicator_id": "macro_regime",
                "module": "macro",
                "calculation_ts": "2024-01-10T00:01:00+00:00",
                "raw_value": "Goldilocks",
                "normalized_value": 0.9,
                "score": 0.9,
                "direction": "bullish",
                "strength": "Strong",
                "interpretation": "Macro is supportive",
                "confidence": "medium",
                "freshness": "daily",
                "evidence_record_ids": ["rec-001"],
                "assumptions": [],
                "failure_cases": [],
                "contradicting_signal_ids": [],
            }
        ],
        supporting_signal_ids=["sig-001"],
        contradicting_signal_ids=[],
        evidence_map={
            "evidence-001": {
                "evidence_id": "evidence-001",
                "signal_id": "sig-001",
                "indicator_id": "macro_regime",
                "record_ids": ["rec-001"],
                "observation_timestamps": ["2024-01-09T00:00:00+00:00"],
                "availability_timestamps": ["2024-01-09T00:00:00+00:00"],
                "quality_status": "valid",
                "assumptions": [],
                "limitations": [],
                "source_reference": "source",
            }
        },
        dataset_freshness={},
        missing_critical_datasets=[],
        stale_critical_datasets=[],
        assumptions=[],
        limitations=[],
        overall_confidence=ConfidenceLevel.high,
        packet_version="phase-3",
        input_data_hash="abc123",
    )
    data = base.to_dict()
    data.update(overrides)
    return MarketContextPacket(**data)


def test_evidence_references_validate_and_reject_broken_links():
    evidence = [
        EvidenceRecord(
            evidence_id="evidence-001",
            signal_id="sig-001",
            indicator_id="macro_regime",
            record_ids=["rec-001"],
            observation_timestamps=["2024-01-09T00:00:00+00:00"],
            availability_timestamps=["2024-01-09T00:00:00+00:00"],
            quality_status="valid",
        )
    ]
    evidence_map = build_evidence_map(evidence)
    validate_evidence_map(evidence_map, {"rec-001"})

    broken = dict(evidence_map)
    broken["evidence-001"] = dict(broken["evidence-001"], record_ids=["missing"])
    try:
        validate_evidence_map(broken, {"rec-001"})
    except Exception as exc:
        assert "missing record" in str(exc)
    else:
        raise AssertionError("Broken evidence reference should be rejected")


def test_same_packet_produces_identical_report_output():
    packet = _packet()
    payload_1 = build_report_payload(packet)
    payload_2 = build_report_payload(packet)
    assert payload_1 == payload_2
    assert packet.stable_hash() == packet.stable_hash()


def test_reports_include_required_sections_and_downgrade_missing_data():
    packet = _packet(missing_critical_datasets=["fred_cpi"], stale_critical_datasets=["market_spy"], overall_confidence=ConfidenceLevel.high)
    payload = build_report_payload(packet)
    markdown = build_report_markdown(packet)
    assert payload["confidence"] == "Low"
    assert "Executive Summary" in markdown
    assert "Supporting Evidence" in markdown
    assert "Contradicting Evidence" in markdown
    assert "Indicators to Monitor" in markdown

