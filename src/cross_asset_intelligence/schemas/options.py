"""Options observation schema."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import ConfigDict, field_validator

from .common import StandardObservation, _ensure_timezone_aware


class OptionContractObservation(StandardObservation):
    """Lightweight options observation contract."""

    model_config = ConfigDict(extra="forbid")

    underlying_symbol: str | None = None
    underlying_spot: float | None = None
    quote_timestamp: datetime | None = None
    expiration: date | None = None
    contract_symbol: str | None = None
    strike: float | None = None
    option_type: str | None = None
    contract_multiplier: float | None = None
    bid: float | None = None
    ask: float | None = None
    last_price: float | None = None
    implied_volatility: float | None = None
    volume: int | None = None
    open_interest: int | None = None
    in_the_money: bool | None = None

    @field_validator("quote_timestamp")
    @classmethod
    def _reject_naive_quote_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        return _ensure_timezone_aware(value, "quote_timestamp")

