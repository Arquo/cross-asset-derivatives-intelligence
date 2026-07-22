"""Shared enums and small constants for the project."""

from enum import Enum


class SourceType(str, Enum):
    """Where a record came from."""

    official = "official"
    vendor = "vendor"
    calculated = "calculated"
    estimated = "estimated"
    manual = "manual"


class QualityStatus(str, Enum):
    """Quality state for a record or output."""

    valid = "valid"
    warning = "warning"
    stale = "stale"
    missing = "missing"
    rejected = "rejected"


class Frequency(str, Enum):
    """Observation frequency."""

    intraday = "intraday"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    quarterly = "quarterly"


class AssetClass(str, Enum):
    """Primary asset classification."""

    equity = "equity"
    etf = "etf"
    rate = "rate"
    future = "future"
    option = "option"
    macro = "macro"
    volatility = "volatility"
    commodity = "commodity"
    currency = "currency"
    credit = "credit"


class SignalDirection(str, Enum):
    """Direction of a derived signal."""

    bullish = "bullish"
    bearish = "bearish"
    neutral = "neutral"
    mixed = "mixed"
    unknown = "unknown"


class ConfidenceLevel(str, Enum):
    """Simple confidence scale used by reports and signals."""

    low = "low"
    medium = "medium"
    high = "high"

