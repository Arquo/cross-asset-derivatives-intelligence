"""Deterministic report service."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from cross_asset_intelligence.reporting.report_repository import ReportRepository
from cross_asset_intelligence.services.analytics_service import AnalyticsService


class ReportService:
    """Load and write deterministic market summaries."""

    def __init__(self, database_path: Path, report_directory: Path, root_dir: Path | None = None) -> None:
        self.analytics_service = AnalyticsService(database_path, root_dir=root_dir)
        self.report_repository = ReportRepository(report_directory)

    def generate_report(self, as_of: pd.Timestamp | None = None) -> tuple[Path, Path]:
        snapshot = self.analytics_service.build_snapshot(as_of=as_of)
        if snapshot.packet is None:
            raise ValueError("No analytics packet is available to report.")
        return self.report_repository.save_report(snapshot.packet)

