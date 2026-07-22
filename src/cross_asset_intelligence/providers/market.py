"""Free daily market data provider based on yfinance."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from cross_asset_intelligence.core.constants import Frequency, QualityStatus, SourceType
from cross_asset_intelligence.core.exceptions import ProviderError
from cross_asset_intelligence.pipelines.normalization import market_session_close_timestamp, make_record_id, utc_now

from .base import DataProvider


@dataclass(frozen=True)
class MarketFetchResult:
    """Normalized yfinance output."""

    frame: pd.DataFrame
    failed_symbols: list[str]
    source_label: str = "yfinance/Yahoo Finance"


class YFinanceMarketProvider(DataProvider):
    """Historical daily market data provider."""

    def __init__(
        self,
        symbols: list[dict[str, Any]],
        start_date: str,
        end_date: str | None = None,
        timeout: int = 30,
        retry_count: int = 2,
    ) -> None:
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.timeout = timeout
        self.retry_count = retry_count

    @property
    def provider_name(self) -> str:
        return "yfinance"

    def validate_configuration(self) -> None:
        if not self.symbols:
            raise ProviderError("No market symbols configured.")

    def health_check(self) -> bool:
        return True

    def _normalise_download_frame(self, raw: pd.DataFrame, symbol_map: dict[str, str]) -> pd.DataFrame:
        if raw.empty:
            return pd.DataFrame()

        records = []
        if isinstance(raw.columns, pd.MultiIndex):
            provider_symbols = list(raw.columns.get_level_values(1).unique())
            for provider_symbol in provider_symbols:
                if provider_symbol not in symbol_map:
                    continue
                subset = raw.xs(provider_symbol, axis=1, level=1).copy()
                subset = subset.reset_index()
                subset["provider_symbol"] = provider_symbol
                records.extend(self._records_from_subset(subset, symbol_map))
        else:
            provider_symbol = next(iter(symbol_map.keys()))
            subset = raw.reset_index()
            subset["provider_symbol"] = provider_symbol
            records.extend(self._records_from_subset(subset, symbol_map))
        frame = pd.DataFrame(records)
        if frame.empty:
            return frame
        frame = frame.sort_values(["symbol", "observation_ts"]).drop_duplicates(["symbol", "observation_ts"]).reset_index(drop=True)
        return frame

    def _records_from_subset(self, subset: pd.DataFrame, symbol_map: dict[str, str]) -> list[dict[str, Any]]:
        records = []
        for _, row in subset.iterrows():
            provider_symbol = row.get("provider_symbol")
            internal_symbol = symbol_map.get(provider_symbol, provider_symbol)
            trading_date = pd.Timestamp(row.get("Date", row.get("index", row.get("date"))))
            if pd.isna(trading_date):
                continue
            observation_ts = market_session_close_timestamp(trading_date)
            adjusted_close = row.get("Adj Close")
            adjusted_close_status = "adjusted_close"
            if adjusted_close is None or pd.isna(adjusted_close):
                adjusted_close = row.get("Close")
                adjusted_close_status = "close_fallback"
            records.append(
                {
                    "record_id": make_record_id("market", internal_symbol, observation_ts.isoformat()),
                    "dataset_id": f"market_{internal_symbol.lower()}",
                    "symbol": internal_symbol,
                    "provider_symbol": provider_symbol,
                    "provider": "yfinance/Yahoo Finance",
                    "source_type": SourceType.vendor,
                    "observation_ts": observation_ts,
                    "available_ts": observation_ts,
                    "ingested_ts": utc_now(),
                    "frequency": Frequency.daily,
                    "open": row.get("Open"),
                    "high": row.get("High"),
                    "low": row.get("Low"),
                    "close": row.get("Close"),
                    "adjusted_close": adjusted_close,
                    "adjusted_close_status": adjusted_close_status,
                    "volume": row.get("Volume"),
                    "currency": "USD",
                    "quality_status": QualityStatus.valid,
                    "quality_flags": ["historical_data", "yfinance_unofficial"],
                }
            )
        return records

    def fetch(self) -> MarketFetchResult:
        self.validate_configuration()
        symbol_map = {entry["provider_symbol"]: entry["internal_symbol"] for entry in self.symbols if entry.get("enabled", True)}
        try:
            raw = yf.download(
                tickers=list(symbol_map.keys()),
                start=self.start_date,
                end=self.end_date,
                interval="1d",
                auto_adjust=False,
                actions=False,
                progress=False,
                threads=True,
                timeout=self.timeout,
                group_by="column",
            )
        except Exception as exc:
            raise ProviderError("Unable to download market data from yfinance.") from exc
        frame = self._normalise_download_frame(raw, symbol_map)
        present = set(frame["provider_symbol"]) if not frame.empty else set()
        failed = [symbol for symbol in symbol_map if symbol not in present]
        return MarketFetchResult(frame=frame, failed_symbols=failed)

    def normalize(self, observations):  # pragma: no cover - concrete normalization happens in pipeline helpers
        return observations


MarketDataProvider = YFinanceMarketProvider
