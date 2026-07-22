"""Deterministic report generation from a MarketContextPacket."""

from __future__ import annotations

from collections.abc import Mapping

from cross_asset_intelligence.evidence.models import MarketContextPacket


def _signal_list(packet: MarketContextPacket, positive: bool) -> list[dict]:
    comparator = (lambda score: score > 0) if positive else (lambda score: score < 0)
    return [signal for signal in packet.signals if comparator(float(signal.get("score") or 0))]


def build_report_payload(packet: MarketContextPacket) -> dict[str, object]:
    """Create a structured report payload."""

    supporting = _signal_list(packet, True)
    contradicting = _signal_list(packet, False)
    overall = "Mixed"
    confidence_value = packet.overall_confidence.value if hasattr(packet.overall_confidence, "value") else str(packet.overall_confidence)
    confidence_value = confidence_value.lower()
    if confidence_value == "high" and supporting and not contradicting:
        overall = "Bullish"
    elif confidence_value == "high" and contradicting and not supporting:
        overall = "Bearish"
    elif packet.missing_critical_datasets:
        overall = "Insufficient data"
    elif packet.stale_critical_datasets:
        overall = "Transitioning"
    confidence = confidence_value.title()
    if packet.missing_critical_datasets:
        confidence = "Low"
    elif packet.stale_critical_datasets and confidence == "High":
        confidence = "Medium"
    return {
        "report_id": packet.packet_id,
        "report_as_of": packet.as_of_timestamp,
        "data_cutoff": packet.data_cutoff_timestamp,
        "overall_regime": overall,
        "confidence": confidence,
        "executive_summary": packet.module_summaries.get("executive_summary", ""),
        "sections": {
            "Macro Regime": packet.module_summaries.get("macro", {}),
            "Positioning": packet.module_summaries.get("positioning", {}),
            "Market Trends": packet.module_summaries.get("market_trends", {}),
            "Liquidity & Market-Structure Proxies": packet.module_summaries.get("liquidity", {}),
            "Cross-Asset Relationships": packet.module_summaries.get("cross_asset", {}),
            "Supporting Evidence": supporting,
            "Contradicting Evidence": contradicting,
            "Key Risks": packet.module_summaries.get("key_risks", []),
            "Data Limitations": packet.limitations,
            "Indicators to Monitor": packet.module_summaries.get("indicators_to_monitor", []),
        },
        "supporting_signals": packet.supporting_signal_ids,
        "contradicting_signals": packet.contradicting_signal_ids,
        "packet_version": packet.packet_version,
        "input_packet_hash": packet.input_data_hash,
    }


def build_report_markdown(packet: MarketContextPacket) -> str:
    """Render a deterministic Markdown report."""

    payload = build_report_payload(packet)
    lines = [
        f"# Deterministic Market Summary",
        "",
        f"- As of: {payload['report_as_of']}",
        f"- Data cutoff: {payload['data_cutoff']}",
        f"- Overall regime: {payload['overall_regime']}",
        f"- Confidence: {payload['confidence']}",
        "",
        "## Executive Summary",
        str(payload["executive_summary"]),
        "",
    ]
    for section_name, section_value in payload["sections"].items():
        lines.extend([f"## {section_name}"])
        if isinstance(section_value, list):
            if not section_value:
                lines.append("- None")
            else:
                for item in section_value:
                    lines.append(f"- {item if isinstance(item, str) else item.get('signal_id', item)}")
        elif isinstance(section_value, Mapping):
            for key, value in section_value.items():
                lines.append(f"- {key}: {value}")
        else:
            lines.append(str(section_value))
        lines.append("")
    return "\n".join(lines).strip() + "\n"
