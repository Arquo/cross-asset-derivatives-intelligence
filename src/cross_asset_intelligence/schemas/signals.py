"""Signal record schema."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cross_asset_intelligence.core.constants import ConfidenceLevel, SignalDirection

from .common import _ensure_timezone_aware


class SignalRecord(BaseModel):
    """Derived signal contract used for evidence and reporting."""

    model_config = ConfigDict(extra="forbid")

    signal_id: str
    indicator_id: str
    module: str
    calculation_ts: datetime
    raw_value: Any
    normalized_value: Any
    score: float = Field(ge=-1.0, le=1.0)
    direction: SignalDirection
    strength: float | str | None = None
    interpretation: str
    confidence: ConfidenceLevel
    freshness: str
    evidence_record_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    failure_cases: list[str] = Field(default_factory=list)
    contradicting_signal_ids: list[str] = Field(default_factory=list)

    @field_validator("calculation_ts")
    @classmethod
    def _reject_naive_calculation_ts(cls, value: datetime) -> datetime:
        return _ensure_timezone_aware(value, "calculation_ts")

