from __future__ import annotations

import pandas as pd
import pytest

from cross_asset_intelligence.analytics.options.calculations import (
    black_scholes_delta,
    black_scholes_gamma,
    expected_move_from_iv,
    expected_move_from_straddle,
    gamma_assumption_sensitivity,
    gamma_exposure_by_strike,
    gamma_flip_estimate,
    mid_price,
    open_interest_concentration,
    put_call_ratio,
    risk_reversal,
    select_25_delta_contract,
    select_atm_contract,
)


def _chain() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"strike": 90.0, "option_type": "put", "implied_volatility": 0.30, "open_interest": 100, "contract_multiplier": 100},
            {"strike": 100.0, "option_type": "put", "implied_volatility": 0.22, "open_interest": 200, "contract_multiplier": 100},
            {"strike": 100.0, "option_type": "call", "implied_volatility": 0.20, "open_interest": 300, "contract_multiplier": 100},
            {"strike": 110.0, "option_type": "call", "implied_volatility": 0.25, "open_interest": 150, "contract_multiplier": 100},
        ]
    )


def test_mid_price_calculation():
    assert mid_price(1.0, 1.2, 1.1) == pytest.approx(1.1)


def test_put_call_volume_ratio():
    assert put_call_ratio(200, 100) == 2


def test_put_call_open_interest_ratio():
    assert put_call_ratio(300, 600) == 0.5


def test_atm_option_selection():
    assert select_atm_contract(_chain(), 101, "call")["strike"] == 100


def test_black_scholes_delta():
    assert black_scholes_delta(100, 100, 0.25, 0.20, "call") == pytest.approx(0.5596, rel=1e-3)
    assert black_scholes_delta(100, 100, 0.25, 0.20, "put") < 0


def test_black_scholes_gamma():
    assert black_scholes_gamma(100, 100, 0.25, 0.20) == pytest.approx(0.03945, rel=1e-3)


def test_approximate_25_delta_selection():
    selected = select_25_delta_contract(_chain(), spot=100, time_years=0.25, option_type="call")
    assert selected is not None
    assert selected["delta_difference"] >= 0


def test_risk_reversal():
    assert risk_reversal(0.30, 0.20) == pytest.approx(-0.10)


def test_expected_move_from_straddle():
    assert expected_move_from_straddle(4.0, 5.0) == 9.0


def test_expected_move_from_implied_volatility():
    assert expected_move_from_iv(100, 0.20, 0.25) == pytest.approx(10.0)


def test_open_interest_concentration():
    assert open_interest_concentration(pd.Series([50, 30, 20]), top_n=1) == 0.5


def test_gamma_exposure_by_strike():
    result = gamma_exposure_by_strike(_chain(), spot=100, time_years=0.25)
    assert set(result.columns) == {"strike", "estimated_gamma_exposure"}
    assert result["estimated_gamma_exposure"].notna().all()


def test_gamma_assumption_sensitivity():
    result = gamma_assumption_sensitivity(_chain(), spot=100, time_years=0.25)
    assert result["all_long_gamma"] > 0
    assert result["calls_positive_puts_negative"] != result["all_long_gamma"]


def test_gamma_flip_handling_when_no_crossing():
    result = gamma_flip_estimate(_chain(), spot_scenarios=[90, 100, 110], time_years=0.25, assumption_set="all_long_gamma")
    assert result is None


def test_missing_and_invalid_option_quotes():
    assert mid_price(2.0, 1.0, None) is None
    assert mid_price(None, None, 3.0) == 3.0
    assert put_call_ratio(10, 0) is None
