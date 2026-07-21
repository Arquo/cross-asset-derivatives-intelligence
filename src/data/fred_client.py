from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests


FRED_BASE_URL = "https://api.stlouisfed.org/fred"


@dataclass(frozen=True)
class FREDSeriesMetadata:
    series_id: str
    title: str
    frequency: str
    frequency_short: str
    units: str
    units_short: str
    seasonal_adjustment: str
    seasonal_adjustment_short: str
    observation_start: pd.Timestamp | None
    observation_end: pd.Timestamp | None
    last_updated: pd.Timestamp | None
    notes: str | None


def _parse_timestamp(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    return pd.to_datetime(value, errors="coerce")


def _clean_observation_value(value: Any) -> float | None:
    if value in (None, "", "."):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _raise_for_fred_response(response: requests.Response, series_id: str) -> None:
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Unable to download FRED data for {series_id}.") from exc


def fetch_fred_series_metadata(api_key: str, series_id: str, session: requests.Session | None = None) -> FREDSeriesMetadata:
    http = session or requests.Session()
    response = http.get(
        f"{FRED_BASE_URL}/series",
        params={"series_id": series_id, "api_key": api_key, "file_type": "json"},
        timeout=30,
    )
    _raise_for_fred_response(response, series_id)
    payload = response.json()
    series = payload.get("seriess", [])
    if not series:
        raise RuntimeError(f"Series metadata is unavailable for {series_id}.")
    item = series[0]
    return FREDSeriesMetadata(
        series_id=series_id,
        title=item.get("title", series_id),
        frequency=item.get("frequency", "Unknown"),
        frequency_short=item.get("frequency_short", ""),
        units=item.get("units", ""),
        units_short=item.get("units_short", ""),
        seasonal_adjustment=item.get("seasonal_adjustment", ""),
        seasonal_adjustment_short=item.get("seasonal_adjustment_short", ""),
        observation_start=_parse_timestamp(item.get("observation_start")),
        observation_end=_parse_timestamp(item.get("observation_end")),
        last_updated=_parse_timestamp(item.get("last_updated")),
        notes=item.get("notes"),
    )


def fetch_fred_observations(api_key: str, series_id: str, session: requests.Session | None = None) -> pd.DataFrame:
    http = session or requests.Session()
    response = http.get(
        f"{FRED_BASE_URL}/series/observations",
        params={"series_id": series_id, "api_key": api_key, "file_type": "json", "sort_order": "asc"},
        timeout=30,
    )
    _raise_for_fred_response(response, series_id)
    payload = response.json()
    observations = payload.get("observations", [])
    rows: list[dict[str, Any]] = []
    for obs in observations:
        rows.append(
            {
                "date": pd.to_datetime(obs.get("date"), errors="coerce"),
                "value": _clean_observation_value(obs.get("value")),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame = frame.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return frame

