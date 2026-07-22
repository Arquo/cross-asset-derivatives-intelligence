from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from cross_asset_intelligence.core.config import CFTCContractConfig
from cross_asset_intelligence.core.exceptions import ProviderError
from cross_asset_intelligence.pipelines.cftc_normalization import normalize_cftc_fetch_result
from cross_asset_intelligence.providers.cftc import CFTCContractFrame, CFTCProvider
from cross_asset_intelligence.storage.repositories import DuckDBRepository


def _contract() -> CFTCContractConfig:
    return CFTCContractConfig(
        internal_asset_id="sp500",
        display_name="S&P 500",
        cftc_contract_market_code=None,
        official_contract_name="S&P 500 - CHICAGO MERCANTILE EXCHANGE",
        report_type="tff",
        exchange="CHICAGO MERCANTILE EXCHANGE",
        asset_class="equity_index",
        contract_unit="USD per index point",
        preferred_participant_categories=["Dealer or intermediary", "Asset manager or institutional"],
        active=True,
    )


def _raw_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "report_date_as_yyyy_mm_dd": "2024-01-02",
                "contract_market_name": "S&P 500 - CHICAGO MERCANTILE EXCHANGE",
                "market_and_exchange_names": "S&P 500 - CHICAGO MERCANTILE EXCHANGE",
                "open_interest_all": 1000,
                "dealer_positions_long_all": 600,
                "dealer_positions_short_all": 200,
                "dealer_positions_spread_all": 50,
                "asset_mgr_positions_long": 120,
                "asset_mgr_positions_short": 180,
                "asset_mgr_positions_spread": 20,
                "lev_money_positions_long_all": 80,
                "lev_money_positions_short_all": 220,
                "lev_money_positions_spread_all": 10,
                "other_rept_positions_long_all": 40,
                "other_rept_positions_short_all": 30,
                "other_rept_positions_spread_all": 5,
                "nonrept_positions_long_all": 160,
                "nonrept_positions_short_all": 170,
                "nonrept_traders_tot_all": 25,
                "dealer_traders_tot_all": 10,
                "asset_mgr_traders_tot_all": 11,
                "lev_money_traders_tot_all": 12,
                "other_rept_traders_tot_all": 13,
            }
        ]
    )


def test_official_style_columns_normalize_correctly():
    contract = _contract()
    frame = _raw_frame()
    result = SimpleNamespace(successful=[CFTCContractFrame(contract=contract, frame=frame, source_url="https://example.com/cftc.csv")], failed=[], rows_fetched=1)
    normalized, warnings = normalize_cftc_fetch_result(result, "run-1")
    assert warnings.empty
    assert not normalized.empty
    assert set(normalized["participant_category"]) >= {"Dealer or intermediary", "Asset manager or institutional"}
    assert "weekly_delayed_data" in normalized.iloc[0]["quality_flags"]


def test_report_date_and_publication_date_are_distinct():
    contract = _contract()
    result = SimpleNamespace(successful=[CFTCContractFrame(contract=contract, frame=_raw_frame(), source_url="https://example.com/cftc.csv")], failed=[], rows_fetched=1)
    normalized, _ = normalize_cftc_fetch_result(result, "run-1")
    row = normalized.iloc[0]
    assert row["report_date"] != row["publication_date"]
    assert row["available_ts"] > row["report_date"]


def test_duplicate_contract_report_category_records_are_deduplicated(tmp_path):
    repository = DuckDBRepository(tmp_path / "cross_asset.duckdb")
    repository.initialize()
    contract = _contract()
    result = SimpleNamespace(successful=[CFTCContractFrame(contract=contract, frame=_raw_frame(), source_url="https://example.com/cftc.csv")], failed=[], rows_fetched=1)
    normalized, _ = normalize_cftc_fetch_result(result, "run-1")
    repository.insert_cftc_positioning_observations(normalized)
    repository.insert_cftc_positioning_observations(normalized)
    count = repository.fetch_dataframe("SELECT COUNT(*) AS n FROM cftc_positioning_observations").iloc[0]["n"]
    assert count == len(normalized)


def test_missing_participant_categories_are_handled():
    contract = _contract()
    frame = _raw_frame().drop(columns=["asset_mgr_positions_short"])
    result = SimpleNamespace(successful=[CFTCContractFrame(contract=contract, frame=frame, source_url="https://example.com/cftc.csv")], failed=[], rows_fetched=1)
    normalized, warnings = normalize_cftc_fetch_result(result, "run-1")
    assert not normalized.empty
    assert not warnings.empty


def test_ambiguous_mappings_are_rejected(monkeypatch):
    contract = _contract()
    provider = CFTCProvider(contracts=[contract], start_date="2024-01-01")

    def fake_request_csv(dataset_id, params):
        return pd.DataFrame(
            [
                {"report_date_as_yyyy_mm_dd": "2024-01-02", "contract_market_name": "A", "market_and_exchange_names": "A", "open_interest_all": 1, "dealer_positions_long_all": 1, "dealer_positions_short_all": 0},
                {"report_date_as_yyyy_mm_dd": "2024-01-02", "contract_market_name": "B", "market_and_exchange_names": "B", "open_interest_all": 1, "dealer_positions_long_all": 1, "dealer_positions_short_all": 0},
            ]
        )

    monkeypatch.setattr(provider, "_request_csv", fake_request_csv)
    with pytest.raises(ProviderError, match="Ambiguous CFTC mapping"):
        provider._download_contract(contract)


def test_failed_downloads_do_not_look_like_success(monkeypatch):
    contract = _contract()
    provider = CFTCProvider(contracts=[contract], start_date="2024-01-01")

    def boom(*args, **kwargs):
        raise ProviderError("download failed")

    monkeypatch.setattr(provider, "_download_contract", boom)
    result = provider.fetch()
    assert result.successful == []
    assert result.failed

