"""Positioning observation schema."""

from __future__ import annotations

from datetime import date

from pydantic import ConfigDict

from .common import StandardObservation


class PositioningObservation(StandardObservation):
    """Lightweight positioning observation contract."""

    model_config = ConfigDict(extra="forbid")

    contract_code: str | None = None
    report_date: date | None = None
    publication_date: date | None = None
    participant_category: str | None = None
    long_contracts: int | None = None
    short_contracts: int | None = None
    open_interest: int | None = None

