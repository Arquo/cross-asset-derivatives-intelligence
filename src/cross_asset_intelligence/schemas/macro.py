"""Macro observation schema."""

from __future__ import annotations

from pydantic import ConfigDict

from .common import StandardObservation


class MacroObservation(StandardObservation):
    """Lightweight macro observation contract."""

    model_config = ConfigDict(extra="forbid")

    series_id: str | None = None
    category: str | None = None
    release_name: str | None = None
    reference_period: str | None = None
    revision_number: int | None = None

