"""Market observation schema."""

from __future__ import annotations

from pydantic import ConfigDict

from .common import StandardObservation


class MarketObservation(StandardObservation):
    """Lightweight market observation contract."""

    model_config = ConfigDict(extra="forbid")

    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    adjusted_close: float | None = None
    volume: int | None = None
    currency: str | None = None

