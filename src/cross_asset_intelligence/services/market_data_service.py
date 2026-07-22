"""Service layer for stored market data."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from cross_asset_intelligence.storage.repositories import DuckDBRepository


def calculate_daily_returns(frame: pd.DataFrame, value_column: str = "adjusted_close") -> pd.DataFrame:
    """Calculate percentage daily returns for a price series."""

    if frame.empty:
        return frame.copy()
    working = frame.copy()
    working["observation_ts"] = pd.to_datetime(working["observation_ts"], utc=True, errors="coerce")
    working = working.sort_values(["symbol", "observation_ts"]).reset_index(drop=True)
    working["daily_return"] = (working.groupby("symbol")[value_column].pct_change() * 100.0).round(6)
    return working


def normalize_performance(frame: pd.DataFrame, value_column: str = "adjusted_close") -> pd.DataFrame:
    """Normalize each symbol to 100 at the first available observation."""

    if frame.empty:
        return frame.copy()
    working = frame.copy()
    working["observation_ts"] = pd.to_datetime(working["observation_ts"], utc=True, errors="coerce")
    working = working.sort_values(["symbol", "observation_ts"]).reset_index(drop=True)
    normalized_rows = []
    for symbol, subset in working.groupby("symbol", sort=False):
        subset = subset.copy()
        base_value = subset[value_column].dropna().iloc[0] if not subset[value_column].dropna().empty else pd.NA
        subset["normalized_value"] = ((subset[value_column] / base_value) * 100.0).round(6) if pd.notna(base_value) and base_value != 0 else pd.NA
        normalized_rows.append(subset)
    return pd.concat(normalized_rows, ignore_index=True)


class MarketDataService:
    """Read-only service over stored market observations."""

    def __init__(self, database_path: Path) -> None:
        self.repository = DuckDBRepository(database_path)

    def has_database(self) -> bool:
        return self.repository.database_path.exists()

    def latest_market_observation(self, symbol: str) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        return self.repository.fetch_dataframe(
            """
            SELECT *
            FROM market_observations
            WHERE symbol = ?
            ORDER BY observation_ts DESC
            LIMIT 1
            """,
            (symbol,),
        )

    def recent_market_history(self, symbols: Iterable[str], limit: int = 252) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        symbols = list(symbols)
        if not symbols:
            return pd.DataFrame()
        placeholders = ",".join(["?"] * len(symbols))
        return self.repository.fetch_dataframe(
            f"""
            SELECT *
            FROM market_observations
            WHERE symbol IN ({placeholders})
            ORDER BY observation_ts DESC
            LIMIT ?
            """,
            (*symbols, int(limit)),
        )

    def daily_returns(self, symbol: str, limit: int = 252) -> pd.DataFrame:
        history = self.recent_market_history([symbol], limit=limit)
        if history.empty:
            return history
        return calculate_daily_returns(history)

    def normalized_performance(self, symbols: Iterable[str], limit: int = 252) -> pd.DataFrame:
        history = self.recent_market_history(symbols, limit=limit)
        if history.empty:
            return history
        return normalize_performance(history)

    def latest_macro_observation(self, series_id: str) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        return self.repository.fetch_dataframe(
            """
            SELECT *
            FROM macro_observations
            WHERE series_id = ?
            ORDER BY observation_ts DESC
            LIMIT 1
            """,
            (series_id,),
        )

    def recent_macro_history(self, series_ids: Iterable[str], limit: int = 252) -> pd.DataFrame:
        if not self.has_database():
            return pd.DataFrame()
        series_ids = list(series_ids)
        if not series_ids:
            return pd.DataFrame()
        placeholders = ",".join(["?"] * len(series_ids))
        return self.repository.fetch_dataframe(
            f"""
            SELECT *
            FROM macro_observations
            WHERE series_id IN ({placeholders})
            ORDER BY observation_ts DESC
            LIMIT ?
            """,
            (*series_ids, int(limit)),
        )
