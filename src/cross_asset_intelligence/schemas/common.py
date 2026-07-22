"""Common observation schema used across the project."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cross_asset_intelligence.core.constants import AssetClass, Frequency, QualityStatus, SourceType


def _ensure_timezone_aware(value: datetime, field_name: str) -> datetime:
    """Reject naive datetimes so timestamps always carry timezone information."""

    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be timezone-aware.")
    return value


class StandardObservation(BaseModel):
    """Canonical observation record shared by all data providers."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    dataset_id: str
    provider: str
    source_type: SourceType
    symbol: str
    provider_symbol: str
    asset_class: AssetClass
    observation_ts: datetime
    available_ts: datetime
    ingested_ts: datetime
    frequency: Frequency
    timezone: str
    value: Any
    unit: str
    is_adjusted: bool
    is_estimated: bool
    is_revised: bool
    quality_status: QualityStatus
    quality_flags: list[str] = Field(default_factory=list)
    source_reference: str
    pipeline_run_id: str

    @field_validator("record_id", "dataset_id", "provider", "symbol", "provider_symbol", "timezone")
    @classmethod
    def _reject_blank_strings(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Field cannot be blank.")
        return value

    @field_validator("observation_ts", "available_ts", "ingested_ts")
    @classmethod
    def _reject_naive_datetimes(cls, value: datetime, info) -> datetime:
        return _ensure_timezone_aware(value, info.field_name)

    @model_validator(mode="after")
    def _check_temporal_relationships(self) -> "StandardObservation":
        if self.ingested_ts < self.available_ts:
            raise ValueError("ingested_ts cannot be earlier than available_ts.")
        if self.available_ts < self.observation_ts and not self.is_revised:
            raise ValueError(
                "available_ts cannot be earlier than observation_ts unless the record is revised."
            )
        if self.source_type == SourceType.estimated and not self.is_estimated:
            raise ValueError("Estimated records must set is_estimated to True.")
        if self.is_estimated and self.source_type not in {SourceType.estimated, SourceType.calculated}:
            raise ValueError(
                "Estimated records must use source_type=estimated or source_type=calculated."
            )
        return self

