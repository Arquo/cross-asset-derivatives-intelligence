"""Normalization helpers for provider output."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
import hashlib

import pandas as pd

from cross_asset_intelligence.core.constants import AssetClass, Frequency, QualityStatus, SourceType


UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")


def utc_now() -> pd.Timestamp:
    """Return the current UTC timestamp."""

    return pd.Timestamp.now(tz=UTC)


def make_record_id(*parts: object) -> str:
    """Create a stable deterministic record identifier."""

    material = "|".join("" if part is None else str(part) for part in parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return digest[:32]


def ensure_utc_timestamp(value: datetime | pd.Timestamp) -> pd.Timestamp:
    """Convert timestamps to UTC and reject naive values."""

    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware.")
    return ts.tz_convert(UTC)


def market_session_close_timestamp(trading_date: pd.Timestamp | str) -> pd.Timestamp:
    """Create a UTC timestamp for a U.S. market close."""

    date_value = pd.Timestamp(trading_date).date()
    local_dt = datetime.combine(date_value, time(16, 0), tzinfo=NEW_YORK)
    return pd.Timestamp(local_dt).tz_convert(UTC)


def source_type_enum(source_type: str | SourceType) -> SourceType:
    return source_type if isinstance(source_type, SourceType) else SourceType(source_type)


def frequency_enum(frequency: str | Frequency) -> Frequency:
    return frequency if isinstance(frequency, Frequency) else Frequency(frequency)


def asset_class_enum(asset_class: str | AssetClass) -> AssetClass:
    return asset_class if isinstance(asset_class, AssetClass) else AssetClass(asset_class)


def quality_status_enum(status: str | QualityStatus) -> QualityStatus:
    return status if isinstance(status, QualityStatus) else QualityStatus(status)


def normalized_quality_flags(*flags: str) -> list[str]:
    """Return a stable list of quality flags with duplicates removed."""

    seen: set[str] = set()
    result: list[str] = []
    for flag in flags:
        if flag and flag not in seen:
            seen.add(flag)
            result.append(flag)
    return result

