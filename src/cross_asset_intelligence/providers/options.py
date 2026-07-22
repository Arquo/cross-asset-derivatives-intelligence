"""Replaceable research-grade options provider backed by yfinance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd
import yfinance as yf

from cross_asset_intelligence.core.exceptions import ProviderError
from cross_asset_intelligence.pipelines.normalization import make_record_id

from .base import DataProvider


SOURCE_LABEL = "yfinance/Yahoo Finance (research-grade, replaceable)"


@dataclass(frozen=True)
class OptionSymbolSnapshot:
    """One timestamped option-chain retrieval for an underlying."""

    symbol: str
    snapshot_id: str
    quote_timestamp: pd.Timestamp
    underlying_price: float
    frame: pd.DataFrame


@dataclass(frozen=True)
class OptionsFetchResult:
    """Options retrieval results and symbol/expiration failures."""

    successful: list[OptionSymbolSnapshot]
    failed: list[dict[str, str]]
    rows_fetched: int


class YFinanceOptionsProvider(DataProvider):
    """Current SPY/QQQ option chains from a replaceable free provider."""

    def __init__(
        self,
        symbols: list[str],
        *,
        ticker_factory: Callable[[str], Any] = yf.Ticker,
    ) -> None:
        self.symbols = [symbol.upper() for symbol in symbols]
        self.ticker_factory = ticker_factory

    @property
    def provider_name(self) -> str:
        return "yfinance-options"

    def validate_configuration(self) -> None:
        unsupported = sorted(set(self.symbols) - {"SPY", "QQQ"})
        if unsupported:
            raise ProviderError(f"Options coverage is limited to SPY and QQQ: {', '.join(unsupported)}")
        if not self.symbols:
            raise ProviderError("No option symbols configured.")

    def health_check(self) -> bool:
        return bool(self.symbols)

    @staticmethod
    def _underlying_price(ticker: Any) -> float:
        try:
            value = ticker.fast_info.get("last_price")
            if value is not None and pd.notna(value) and float(value) > 0:
                return float(value)
        except Exception:
            pass
        history = ticker.history(period="5d", auto_adjust=False)
        close = pd.to_numeric(history.get("Close"), errors="coerce").dropna()
        if close.empty:
            raise ProviderError("Underlying price is unavailable.")
        return float(close.iloc[-1])

    @staticmethod
    def _normalize_side(
        frame: pd.DataFrame,
        *,
        symbol: str,
        option_type: str,
        expiration: str,
        snapshot_id: str,
        quote_timestamp: pd.Timestamp,
        underlying_price: float,
    ) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame()
        renamed = frame.rename(
            columns={
                "contractSymbol": "contract_symbol",
                "lastTradeDate": "last_trade_timestamp",
                "lastPrice": "last_price",
                "impliedVolatility": "implied_volatility",
                "openInterest": "open_interest",
                "inTheMoney": "in_the_money",
            }
        ).copy()
        expiration_date = pd.Timestamp(expiration).date()
        renamed["snapshot_id"] = snapshot_id
        renamed["symbol"] = symbol
        renamed["underlying_price"] = underlying_price
        renamed["quote_timestamp"] = quote_timestamp
        renamed["ingested_ts"] = quote_timestamp
        renamed["expiration"] = expiration_date
        renamed["option_type"] = option_type
        renamed["contract_multiplier"] = 100.0
        renamed["source_label"] = SOURCE_LABEL
        renamed["quality_status"] = "valid"
        renamed["record_id"] = renamed.apply(
            lambda row: make_record_id(
                "option",
                snapshot_id,
                row.get("contract_symbol", ""),
                option_type,
                row.get("strike", ""),
            ),
            axis=1,
        )
        columns = [
            "record_id",
            "snapshot_id",
            "symbol",
            "underlying_price",
            "quote_timestamp",
            "ingested_ts",
            "expiration",
            "contract_symbol",
            "last_trade_timestamp",
            "strike",
            "option_type",
            "contract_multiplier",
            "bid",
            "ask",
            "last_price",
            "implied_volatility",
            "volume",
            "open_interest",
            "in_the_money",
            "source_label",
            "quality_status",
        ]
        for column in columns:
            if column not in renamed.columns:
                renamed[column] = pd.NA
        renamed["last_trade_timestamp"] = pd.to_datetime(renamed["last_trade_timestamp"], utc=True, errors="coerce")
        for column in ["strike", "bid", "ask", "last_price", "implied_volatility", "volume", "open_interest"]:
            renamed[column] = pd.to_numeric(renamed[column], errors="coerce")
        return renamed[columns]

    def fetch(self) -> OptionsFetchResult:
        self.validate_configuration()
        successful: list[OptionSymbolSnapshot] = []
        failed: list[dict[str, str]] = []
        total_rows = 0
        for symbol in self.symbols:
            quote_timestamp = pd.Timestamp.now(tz="UTC")
            snapshot_id = make_record_id("options_snapshot", symbol, quote_timestamp.isoformat())
            try:
                ticker = self.ticker_factory(symbol)
                underlying_price = self._underlying_price(ticker)
                expirations = list(ticker.options)
                if not expirations:
                    raise ProviderError("No expirations were returned.")
                frames: list[pd.DataFrame] = []
                for expiration in expirations:
                    try:
                        chain = ticker.option_chain(expiration)
                        frames.append(
                            self._normalize_side(
                                chain.calls,
                                symbol=symbol,
                                option_type="call",
                                expiration=expiration,
                                snapshot_id=snapshot_id,
                                quote_timestamp=quote_timestamp,
                                underlying_price=underlying_price,
                            )
                        )
                        frames.append(
                            self._normalize_side(
                                chain.puts,
                                symbol=symbol,
                                option_type="put",
                                expiration=expiration,
                                snapshot_id=snapshot_id,
                                quote_timestamp=quote_timestamp,
                                underlying_price=underlying_price,
                            )
                        )
                    except Exception as exc:
                        failed.append({"symbol": symbol, "expiration": expiration, "error": str(exc)})
                combined = pd.concat([frame for frame in frames if not frame.empty], ignore_index=True) if frames else pd.DataFrame()
                if combined.empty:
                    raise ProviderError("All option-chain expiration downloads failed.")
                total_rows += len(combined)
                successful.append(
                    OptionSymbolSnapshot(
                        symbol=symbol,
                        snapshot_id=snapshot_id,
                        quote_timestamp=quote_timestamp,
                        underlying_price=underlying_price,
                        frame=combined,
                    )
                )
            except Exception as exc:
                failed.append({"symbol": symbol, "expiration": "all", "error": str(exc)})
        return OptionsFetchResult(successful=successful, failed=failed, rows_fetched=total_rows)

    def normalize(self, observations):  # pragma: no cover - fetch returns canonical frames
        return observations


OptionsProvider = YFinanceOptionsProvider
