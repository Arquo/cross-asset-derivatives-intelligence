"""Persistence helpers for deterministic reports and packets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
import json

from cross_asset_intelligence.evidence.models import MarketContextPacket
from cross_asset_intelligence.strategist.deterministic_report import build_report_markdown, build_report_payload


@dataclass
class ReportRepository:
    """Filesystem-backed deterministic report writer."""

    report_directory: Path

    def save_packet(self, packet: MarketContextPacket) -> Path:
        self.report_directory.mkdir(parents=True, exist_ok=True)
        path = self.report_directory / f"packet_{packet.packet_id}_{packet.as_of_timestamp.replace(':', '').replace('-', '')}.json"
        path.write_text(json.dumps(packet.to_dict(), indent=2, sort_keys=True, default=str), encoding="utf-8")
        return path

    def save_report(self, packet: MarketContextPacket) -> tuple[Path, Path]:
        self.report_directory.mkdir(parents=True, exist_ok=True)
        payload = build_report_payload(packet)
        json_path = self.report_directory / f"report_{packet.packet_id}_{packet.as_of_timestamp.replace(':', '').replace('-', '')}.json"
        md_path = self.report_directory / f"report_{packet.packet_id}_{packet.as_of_timestamp.replace(':', '').replace('-', '')}.md"
        json_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        md_path.write_text(build_report_markdown(packet), encoding="utf-8")
        return json_path, md_path

