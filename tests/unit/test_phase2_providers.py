from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pytest
import requests

from cross_asset_intelligence.core.exceptions import ConfigurationError, ProviderError
from cross_asset_intelligence.providers.fred import FredProvider
from cross_asset_intelligence.providers.market import MarketDataProvider


@dataclass
class FakeResponse:
    payload: dict
    status_code: int = 200

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if not self.responses:
            raise AssertionError("Unexpected request")
        return self.responses.pop(0)


def test_fred_cleaning_and_date_parsing():
    responses = [
        FakeResponse({"seriess": [{"title": "Test Series", "frequency": "Monthly"}]}),
        FakeResponse({"observations": [{"date": "2024-01-02", "value": "1.5"}, {"date": "2024-01-01", "value": "."}]}),
    ]
    provider = FredProvider(api_key="test-key", series_configs=[{"series_id": "TEST", "enabled": True, "start_date": "2024-01-01"}], session=FakeSession(responses))

    result = provider.fetch()

    assert len(result.successful) == 1
    frame = result.successful[0].observations
    assert list(frame["date"].dt.strftime("%Y-%m-%d")) == ["2024-01-01", "2024-01-02"]
    assert pd.isna(frame.iloc[0]["value"])
    assert frame.iloc[1]["value"] == pytest.approx(1.5)


def test_fred_missing_api_key_is_clear():
    provider = FredProvider(api_key="   ", series_configs=[{"series_id": "TEST", "enabled": True, "start_date": "2024-01-01"}])

    with pytest.raises(ConfigurationError, match="FRED_API_KEY is missing"):
        provider.fetch()


def test_fred_provider_errors_do_not_look_like_success():
    responses = [FakeResponse({"seriess": []}, status_code=500)]
    provider = FredProvider(api_key="test-key", series_configs=[{"series_id": "TEST", "enabled": True, "start_date": "2024-01-01"}], session=FakeSession(responses))

    result = provider.fetch()

    assert result.successful == []
    assert len(result.failed) == 1
    assert "TEST" in result.failed[0]["series_id"]


def test_market_columns_normalize_correctly(monkeypatch):
    index = pd.to_datetime(["2024-01-02", "2024-01-03"])
    columns = pd.MultiIndex.from_product(
        [["Open", "High", "Low", "Close", "Adj Close", "Volume"], ["SPY", "QQQ"]]
    )
    raw = pd.DataFrame(
        [
            [100, 50, 95, 45, 98, 43, 101, 51, 96, 46, 99, 44],
            [101, 51, 96, 46, 99, 44, 102, 52, 97, 47, 100, 45],
        ],
        index=index,
        columns=columns,
    )

    monkeypatch.setattr("yfinance.download", lambda **kwargs: raw)

    provider = MarketDataProvider(
        symbols=[
            {"internal_symbol": "SPY", "provider_symbol": "SPY", "enabled": True},
            {"internal_symbol": "QQQ", "provider_symbol": "QQQ", "enabled": True},
        ],
        start_date="2024-01-01",
        end_date="2024-01-10",
    )
    result = provider.fetch()

    assert set(result.frame["symbol"]) == {"SPY", "QQQ"}
    assert "adjusted_close_status" in result.frame.columns
    assert set(result.frame["adjusted_close_status"]) == {"adjusted_close"}


def test_market_provider_errors_raise(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("yfinance.download", boom)

    provider = MarketDataProvider(
        symbols=[{"internal_symbol": "SPY", "provider_symbol": "SPY", "enabled": True}],
        start_date="2024-01-01",
        end_date="2024-01-10",
    )

    with pytest.raises(ProviderError, match="Unable to download market data"):
        provider.fetch()
