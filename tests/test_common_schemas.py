"""Tests for the core data contracts."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from cross_asset_intelligence.core.constants import (
    AssetClass,
    ConfidenceLevel,
    Frequency,
    QualityStatus,
    SignalDirection,
    SourceType,
)
from cross_asset_intelligence.schemas.common import StandardObservation
from cross_asset_intelligence.schemas.reports import MarketReport
from cross_asset_intelligence.schemas.signals import SignalRecord

from tests.fixtures.sample_records import market_report_data, signal_record_data, standard_observation_data


def test_valid_standard_observation():
    observation = StandardObservation(**standard_observation_data())

    assert observation.record_id == "rec-001"
    assert observation.source_type is SourceType.official
    assert observation.asset_class is AssetClass.equity
    assert observation.frequency is Frequency.daily
    assert observation.quality_status is QualityStatus.valid


def test_blank_record_id_is_rejected():
    payload = standard_observation_data()
    payload["record_id"] = "   "

    with pytest.raises(ValidationError):
        StandardObservation(**payload)


def test_blank_dataset_id_is_rejected():
    payload = standard_observation_data()
    payload["dataset_id"] = ""

    with pytest.raises(ValidationError):
        StandardObservation(**payload)


def test_naive_timestamps_are_rejected():
    payload = standard_observation_data()
    payload["observation_ts"] = datetime(2026, 7, 20, 16, 0)

    with pytest.raises(ValidationError):
        StandardObservation(**payload)


def test_ingested_before_available_is_rejected():
    payload = standard_observation_data()
    payload["ingested_ts"] = payload["available_ts"] - timedelta(minutes=1)

    with pytest.raises(ValidationError):
        StandardObservation(**payload)


def test_valid_enum_parsing():
    observation = StandardObservation(**standard_observation_data())

    assert observation.source_type is SourceType.official
    assert observation.asset_class is AssetClass.equity
    assert observation.frequency is Frequency.daily
    assert observation.quality_status is QualityStatus.valid


def test_invalid_enum_values_are_rejected():
    payload = standard_observation_data()
    payload["source_type"] = "not-a-real-type"

    with pytest.raises(ValidationError):
        StandardObservation(**payload)


def test_quality_flags_default_to_empty_list():
    payload = standard_observation_data()
    payload.pop("quality_flags")

    observation = StandardObservation(**payload)

    assert observation.quality_flags == []


def test_signal_score_minus_one_is_allowed():
    payload = signal_record_data()
    payload["score"] = -1

    signal = SignalRecord(**payload)

    assert signal.score == -1
    assert signal.direction is SignalDirection.bullish
    assert signal.confidence is ConfidenceLevel.high


def test_signal_score_plus_one_is_allowed():
    payload = signal_record_data()
    payload["score"] = 1

    signal = SignalRecord(**payload)

    assert signal.score == 1


def test_signal_score_below_minus_one_is_rejected():
    payload = signal_record_data()
    payload["score"] = -1.1

    with pytest.raises(ValidationError):
        SignalRecord(**payload)


def test_signal_score_above_plus_one_is_rejected():
    payload = signal_record_data()
    payload["score"] = 1.1

    with pytest.raises(ValidationError):
        SignalRecord(**payload)


def test_market_report_schema_accepts_valid_payload():
    report = MarketReport(**market_report_data())

    assert report.validation_status is QualityStatus.valid
    assert report.confidence is ConfidenceLevel.medium

