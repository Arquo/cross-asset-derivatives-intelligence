"""Official FRED provider implementation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any
import json
import time
from urllib.parse import urljoin

import pandas as pd
import requests

from cross_asset_intelligence.core.constants import AssetClass, Frequency, QualityStatus, SourceType
from cross_asset_intelligence.core.exceptions import ConfigurationError, ProviderError
from cross_asset_intelligence.pipelines.normalization import ensure_utc_timestamp, make_record_id, normalized_quality_flags

from .base import DataProvider


FRED_API_BASE = "https://api.stlouisfed.org/fred/"


@dataclass(frozen=True)
class FredSeriesResult:
    """Normalized FRED series result."""

    series_id: str
    metadata: dict[str, Any]
    observations: pd.DataFrame


@dataclass(frozen=True)
class FredFetchResult:
    """Result of a FRED provider run."""

    successful: list[FredSeriesResult]
    failed: list[dict[str, Any]]
    rows_fetched: int


class FredProvider(DataProvider):
    """Official FRED provider."""

    def __init__(
        self,
        api_key: str | None,
        series_configs: list[dict[str, Any]],
        timeout: int = 30,
        retry_count: int = 3,
        session: requests.Session | None = None,
        raw_output_dir: Path | None = None,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.series_configs = series_configs
        self.timeout = timeout
        self.retry_count = retry_count
        self.session = session or requests.Session()
        self.raw_output_dir = raw_output_dir

    @property
    def provider_name(self) -> str:
        return "FRED"

    def validate_configuration(self) -> None:
        if not self.api_key:
            raise ConfigurationError("FRED_API_KEY is missing.")

    def health_check(self) -> bool:
        return bool(self.api_key)

    def _request_json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        url = urljoin(FRED_API_BASE, endpoint.lstrip("/"))
        last_error: Exception | None = None
        for attempt in range(self.retry_count + 1):
            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code == 429 or 500 <= response.status_code < 600:
                last_error = ProviderError(f"Temporary FRED error {response.status_code} for {params.get('series_id')}.")
                if attempt < self.retry_count:
                    time.sleep(min(2 ** attempt, 10))
                    continue
                raise last_error
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise ProviderError(f"FRED request failed for {params.get('series_id')}.") from exc
            return response.json()
        raise last_error or ProviderError("FRED request failed.")

    def _download_series_metadata(self, series_id: str) -> dict[str, Any]:
        payload = self._request_json(
            "series",
            {"series_id": series_id, "api_key": self.api_key, "file_type": "json"},
        )
        series = payload.get("seriess", [])
        if not series:
            raise ProviderError(f"No FRED metadata returned for {series_id}.")
        return series[0]

    def _download_series_observations(self, series_id: str, start_date: str, end_date: str | None = None) -> pd.DataFrame:
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start_date,
            "sort_order": "asc",
        }
        if end_date:
            params["observation_end"] = end_date
        payload = self._request_json("series/observations", params)
        rows = payload.get("observations", [])
        frame = pd.DataFrame(rows)
        if frame.empty:
            return frame
        frame["value"] = frame["value"].replace(".", pd.NA)
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
        frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
        return frame.sort_values("date").reset_index(drop=True)

    def fetch(self) -> FredFetchResult:
        self.validate_configuration()
        successful: list[FredSeriesResult] = []
        failed: list[dict[str, Any]] = []
        rows_fetched = 0
        for series in self.series_configs:
            if not series.get("enabled", True):
                continue
            series_id = series["series_id"]
            try:
                metadata = self._download_series_metadata(series_id)
                observations = self._download_series_observations(series_id, series.get("start_date", "2015-01-01"), series.get("end_date"))
                rows_fetched += len(observations)
                successful.append(FredSeriesResult(series_id=series_id, metadata=metadata, observations=observations))
            except Exception as exc:
                failed.append({"series_id": series_id, "error": str(exc)})
        return FredFetchResult(successful=successful, failed=failed, rows_fetched=rows_fetched)

    def normalize(self, observations):  # pragma: no cover - concrete normalization happens in pipeline helpers
        return observations

