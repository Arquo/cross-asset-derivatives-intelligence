from __future__ import annotations

import pandas as pd

from cross_asset_intelligence.analytics.positioning.classification import classify_positioning_bucket, classify_positioning_risk
from cross_asset_intelligence.analytics.positioning.indicators import compute_positioning_metrics


def _history() -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=60, freq="W-TUE", tz="UTC")
    return pd.DataFrame(
        {
            "internal_asset_id": "sp500",
            "participant_category": "Leveraged funds",
            "contract_name": "S&P 500",
            "report_date": dates,
            "publication_date": dates + pd.Timedelta(days=3),
            "ingested_ts": dates + pd.Timedelta(days=3, hours=1),
            "long_contracts": range(100, 160),
            "short_contracts": [80] * 60,
            "open_interest": [1_000] * 60,
            "source_reference": "CFTC",
        }
    )


def test_net_position():
    result = compute_positioning_metrics(_history())
    assert result.iloc[0]["net_position"] == 20


def test_one_week_change():
    result = compute_positioning_metrics(_history())
    assert result.iloc[1]["one_week_net_change"] == 1


def test_four_week_change():
    result = compute_positioning_metrics(_history())
    assert result.iloc[4]["four_week_net_change"] == 4


def test_net_position_divided_by_open_interest():
    result = compute_positioning_metrics(_history())
    assert result.iloc[0]["net_pct_open_interest"] == 0.02


def test_positioning_percentile():
    result = compute_positioning_metrics(_history())
    assert result.iloc[-1]["historical_percentile_52w"] == 1.0


def test_positioning_zscore():
    result = compute_positioning_metrics(_history())
    assert result.iloc[-1]["rolling_zscore"] > 1


def test_crowding_classifications():
    assert classify_positioning_bucket(0.7, 0.95, 1.5, 52) == "Crowded long"
    assert classify_positioning_bucket(-0.7, 0.05, -1.5, 52) == "Crowded short"


def test_long_liquidation_risk():
    result = classify_positioning_risk(0.7, -0.05, 0.95)
    assert result["long_liquidation_risk"] is True


def test_short_squeeze_risk():
    result = classify_positioning_risk(-0.7, 0.05, 0.05)
    assert result["short_squeeze_risk"] is True


def test_price_positioning_divergence():
    assert classify_positioning_risk(0.3, -0.01, 0.7)["positioning_price_divergence"] is True
