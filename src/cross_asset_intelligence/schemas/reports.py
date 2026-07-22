"""Market report schema."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cross_asset_intelligence.core.constants import ConfidenceLevel, QualityStatus

from .common import _ensure_timezone_aware


class MarketReport(BaseModel):
    """Evidence-based summary report contract."""

    model_config = ConfigDict(extra="forbid")

    report_id: str
    report_as_of: datetime
    data_cutoff: datetime
    overall_regime: str
    confidence: ConfidenceLevel
    supporting_signals: list[str] = Field(default_factory=list)
    contradicting_signals: list[str] = Field(default_factory=list)
    base_scenario: str
    bull_scenario: str
    bear_scenario: str
    catalysts: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    data_limitations: list[str] = Field(default_factory=list)
    missing_modules: list[str] = Field(default_factory=list)
    indicators_to_monitor: list[str] = Field(default_factory=list)
    prompt_version: str
    model_name: str
    input_packet_hash: str
    validation_status: QualityStatus

    @field_validator("report_as_of", "data_cutoff")
    @classmethod
    def _reject_naive_report_timestamps(cls, value: datetime, info) -> datetime:
        return _ensure_timezone_aware(value, info.field_name)

