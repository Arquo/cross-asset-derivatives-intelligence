import pandas as pd
import pytest

from src.analytics.macro_regime import (
    calculate_cpi_three_month_annualized,
    calculate_cpi_yoy,
    calculate_change_over_period,
    classify_inflation_regime,
    classify_labour_regime,
    classify_overall_macro_regime,
    classify_policy_regime,
    classify_yield_curve_regime,
    clean_observations,
)


def make_frame(values):
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=len(values), freq="D"),
            "value": values,
        }
    )


def test_clean_observations_converts_missing_and_sorts():
    frame = pd.DataFrame(
        {
            "date": ["2024-01-03", "2024-01-01", "2024-01-02"],
            "value": ["3.0", ".", "1.5"],
        }
    )
    cleaned = clean_observations(frame)
    assert cleaned["date"].tolist() == list(pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]))
    assert pd.isna(cleaned.iloc[0]["value"])
    assert cleaned.iloc[2]["value"] == 3.0


def test_cpi_year_over_year_calculation():
    values = list(range(100, 112)) + [112]
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2023-01-01", periods=len(values), freq="MS"),
            "value": values,
        }
    )
    assert calculate_cpi_yoy(frame) == pytest.approx(12.0)


def test_cpi_three_month_annualized_calculation():
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=4, freq="MS"),
            "value": [100, 102, 104, 106],
        }
    )
    expected = ((106 / 100) ** 4 - 1) * 100
    assert calculate_cpi_three_month_annualized(frame) == pytest.approx(expected)


def test_yield_changes():
    frame = make_frame([1, 2, 3, 4, 5, 6])
    assert calculate_change_over_period(frame, 5) == 5.0
    assert calculate_change_over_period(frame, 2) == 2.0


def test_inflation_classification():
    assert classify_inflation_regime(3.0, 3.5) == "Accelerating"
    assert classify_inflation_regime(3.5, 3.0) == "Decelerating"
    assert classify_inflation_regime(2.0, 2.05) == "Stable"
    assert classify_inflation_regime(None, 2.0) == "Insufficient data"


def test_labour_classification():
    assert classify_labour_regime(0.3) == "Weakening"
    assert classify_labour_regime(-0.3) == "Strengthening"
    assert classify_labour_regime(0.0) == "Stable"
    assert classify_labour_regime(None) == "Insufficient data"


def test_policy_classification():
    assert classify_policy_regime(0.5) == "Tightening"
    assert classify_policy_regime(-0.5) == "Easing"
    assert classify_policy_regime(0.0) == "Stable"
    assert classify_policy_regime(None) == "Insufficient data"


def test_yield_curve_classification():
    assert classify_yield_curve_regime(0.3) == "Normal"
    assert classify_yield_curve_regime(-0.2) == "Inverted"
    assert classify_yield_curve_regime(0.1) == "Flat"
    assert classify_yield_curve_regime(None) == "Insufficient data"


def test_overall_macro_regime_classification():
    assert classify_overall_macro_regime("Stable", "Strengthening", "Stable", "Normal") == "Goldilocks"
    assert classify_overall_macro_regime("Accelerating", "Stable", "Tightening", "Normal") == "Reflation"
    assert classify_overall_macro_regime("Decelerating", "Weakening", "Easing", "Flat") == "Disinflationary slowdown"
    assert classify_overall_macro_regime("Accelerating", "Weakening", "Stable", "Inverted") == "Stagflation risk"
    assert classify_overall_macro_regime("Stable", "Stable", "Stable", "Flat") == "Mixed / transitioning"
    assert classify_overall_macro_regime("Stable", "Insufficient data", "Stable", "Normal") == "Insufficient data"
