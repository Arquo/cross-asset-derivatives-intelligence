"""Prepared positioning views."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from cross_asset_intelligence.services.analytics_service import AnalyticsService


class PositioningService:
    """Read-only service for CFTC positioning views."""

    def __init__(self, database_path: Path, root_dir: Path | None = None) -> None:
        self.analytics_service = AnalyticsService(database_path, root_dir=root_dir)

    def has_database(self) -> bool:
        return self.analytics_service.has_database()

    def latest_positioning(self, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
        return self.analytics_service.latest_positioning(as_of=as_of)

