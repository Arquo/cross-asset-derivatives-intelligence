"""Provider interfaces for the project."""

from .base import DataProvider
from .fred import FredProvider
from .market import MarketDataProvider, YFinanceMarketProvider

__all__ = ["DataProvider", "FredProvider", "MarketDataProvider", "YFinanceMarketProvider"]
