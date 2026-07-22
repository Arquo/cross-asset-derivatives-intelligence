from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from data.fred_client import FREDSeriesMetadata, fetch_fred_observations, fetch_fred_series_metadata


SERIES_IDS = [
    "DFF",
    "DGS2",
    "DGS10",
    "T10Y2Y",
    "DFII10",
    "T10YIE",
    "CPIAUCSL",
    "UNRATE",
]

YIELD_SERIES_IDS = ["DGS2", "DGS10"]


INFLATION_ACCELERATING_THRESHOLD = 0.2
INFLATION_DECELERATING_THRESHOLD = -0.2
LABOUR_WEAKENING_THRESHOLD = 0.2
LABOUR_STRENGTHENING_THRESHOLD = -0.2
POLICY_TIGHTENING_THRESHOLD = 0.25
POLICY_EASING_THRESHOLD = -0.25
YIELD_CURVE_INVERTED_THRESHOLD = -0.05
YIELD_CURVE_FLAT_ABS_THRESHOLD = 0.15


@dataclass(frozen=True)
class SeriesSnapshot:
    series_id: str
    title: str
    frequency: str
    latest_value: float | None
    latest_observation_date: pd.Timestamp | None
    data_status: str
    frame: pd.DataFrame
    metadata: FREDSeriesMetadata | None


@dataclass(frozen=True)
class MacroRegimeResult:
    summary: pd.DataFrame
    series_table: pd.DataFrame
    yield_curve_chart_data: pd.DataFrame
    inflation_chart_data: pd.DataFrame
    unemployment_chart_data: pd.DataFrame
    latest_observation_timestamp: pd.Timestamp | None
    inflation_regime: str
    labour_regime: str
    policy_regime: str
    yield_curve_regime: str
    overall_macro_regime: str
    treasury_yield_data: pd.DataFrame
    indicators: dict[str, float | None]


def clean_observations(frame: pd.DataFrame) -> pd.DataFrame:
    cleaned = frame.copy()
    if "value" in cleaned.columns:
        cleaned["value"] = cleaned["value"].replace(".", pd.NA)
        cleaned["value"] = pd.to_numeric(cleaned["value"], errors="coerce")
    if "date" in cleaned.columns:
        cleaned["date"] = pd.to_datetime(cleaned["date"], errors="coerce")
    cleaned = cleaned.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return cleaned


def latest_valid_observation(frame: pd.DataFrame) -> tuple[pd.Timestamp | None, float | None]:
    cleaned = clean_observations(frame)
    valid = cleaned.dropna(subset=["value"])
    if valid.empty:
        return None, None
    row = valid.iloc[-1]
    return pd.Timestamp(row["date"]), float(row["value"])


def get_value_near_offset(frame: pd.DataFrame, offset: int) -> float | None:
    cleaned = clean_observations(frame).dropna(subset=["value"])
    if cleaned.empty or len(cleaned) <= offset:
        return None
    return float(cleaned.iloc[-1 - offset]["value"])


def calculate_change_over_period(frame: pd.DataFrame, offset: int) -> float | None:
    cleaned = clean_observations(frame).dropna(subset=["value"])
    if cleaned.empty or len(cleaned) <= offset:
        return None
    latest = float(cleaned.iloc[-1]["value"])
    prior = float(cleaned.iloc[-1 - offset]["value"])
    return latest - prior


def calculate_cpi_yoy(frame: pd.DataFrame) -> float | None:
    cleaned = clean_observations(frame).dropna(subset=["value"])
    if len(cleaned) < 13:
        return None
    latest = float(cleaned.iloc[-1]["value"])
    prior = float(cleaned.iloc[-13]["value"])
    if prior == 0:
        return None
    return (latest / prior - 1.0) * 100.0


def calculate_cpi_three_month_annualized(frame: pd.DataFrame) -> float | None:
    cleaned = clean_observations(frame).dropna(subset=["value"])
    if len(cleaned) < 4:
        return None
    latest = float(cleaned.iloc[-1]["value"])
    prior = float(cleaned.iloc[-4]["value"])
    if prior <= 0:
        return None
    return ((latest / prior) ** 4 - 1.0) * 100.0


def calculate_yield_curve_slope(dgs10: pd.DataFrame, dgs2: pd.DataFrame) -> float | None:
    ten = get_value_near_offset(dgs10, 0)
    two = get_value_near_offset(dgs2, 0)
    if ten is None or two is None:
        return None
    return ten - two


def _series_regime_from_thresholds(
    change: float | None,
    positive_threshold: float,
    negative_threshold: float,
    positive_label: str,
    negative_label: str,
    stable_label: str = "Stable",
) -> str:
    if change is None:
        return "Insufficient data"
    if change >= positive_threshold:
        return positive_label
    if change <= negative_threshold:
        return negative_label
    return stable_label


def classify_inflation_regime(cpi_yoy: float | None, cpi_3m_annualized: float | None) -> str:
    if cpi_yoy is None or cpi_3m_annualized is None:
        return "Insufficient data"
    if cpi_3m_annualized - cpi_yoy >= INFLATION_ACCELERATING_THRESHOLD:
        return "Accelerating"
    if cpi_yoy - cpi_3m_annualized >= abs(INFLATION_DECELERATING_THRESHOLD):
        return "Decelerating"
    return "Stable"


def classify_labour_regime(unemployment_change_3m: float | None) -> str:
    return _series_regime_from_thresholds(
        unemployment_change_3m,
        positive_threshold=LABOUR_WEAKENING_THRESHOLD,
        negative_threshold=LABOUR_STRENGTHENING_THRESHOLD,
        positive_label="Weakening",
        negative_label="Strengthening",
    )


def classify_policy_regime(ffr_change_3m: float | None) -> str:
    return _series_regime_from_thresholds(
        ffr_change_3m,
        positive_threshold=POLICY_TIGHTENING_THRESHOLD,
        negative_threshold=POLICY_EASING_THRESHOLD,
        positive_label="Tightening",
        negative_label="Easing",
    )


def classify_yield_curve_regime(slope: float | None) -> str:
    if slope is None:
        return "Insufficient data"
    if slope <= YIELD_CURVE_INVERTED_THRESHOLD:
        return "Inverted"
    if abs(slope) <= YIELD_CURVE_FLAT_ABS_THRESHOLD:
        return "Flat"
    return "Normal"


def classify_overall_macro_regime(
    inflation_regime: str,
    labour_regime: str,
    policy_regime: str,
    yield_curve_regime: str,
) -> str:
    regimes = {inflation_regime, labour_regime, policy_regime, yield_curve_regime}
    if "Insufficient data" in regimes:
        return "Insufficient data"
    if inflation_regime == "Stable" and labour_regime == "Strengthening" and policy_regime == "Stable" and yield_curve_regime == "Normal":
        return "Goldilocks"
    if inflation_regime == "Accelerating" and policy_regime in {"Tightening", "Stable"} and yield_curve_regime in {"Normal", "Flat"}:
        return "Reflation"
    if inflation_regime == "Decelerating" and labour_regime in {"Weakening", "Stable"} and policy_regime in {"Easing", "Stable"}:
        return "Disinflationary slowdown"
    if inflation_regime == "Accelerating" and labour_regime == "Weakening" and yield_curve_regime == "Inverted":
        return "Stagflation risk"
    return "Mixed / transitioning"


def build_series_snapshot(
    series_id: str,
    api_key: str,
    fetch_metadata: Callable[..., FREDSeriesMetadata] = fetch_fred_series_metadata,
    fetch_observations: Callable[..., pd.DataFrame] = fetch_fred_observations,
    session=None,
) -> SeriesSnapshot:
    metadata = None
    title = series_id
    frequency = "Unknown"
    data_status = "Unavailable"

    def _invoke_fetcher(fetcher, api_key_value: str, series_id_value: str):
        try:
            return fetcher(api_key_value, series_id_value, session=session)
        except TypeError:
            return fetcher(api_key_value, series_id_value)

    try:
        metadata = _invoke_fetcher(fetch_metadata, api_key, series_id)
        title = metadata.title
        frequency = metadata.frequency
    except Exception:
        metadata = None
    try:
        frame = _invoke_fetcher(fetch_observations, api_key, series_id)
        frame = clean_observations(frame)
        latest_date, latest_value = latest_valid_observation(frame)
        data_status = "Available" if latest_value is not None else "No valid data"
        return SeriesSnapshot(
            series_id=series_id,
            title=title,
            frequency=frequency,
            latest_value=latest_value,
            latest_observation_date=latest_date,
            data_status=data_status,
            frame=frame,
            metadata=metadata,
        )
    except Exception:
        empty = pd.DataFrame(columns=["date", "value"])
        return SeriesSnapshot(
            series_id=series_id,
            title=title,
            frequency=frequency,
            latest_value=None,
            latest_observation_date=None,
            data_status=data_status,
            frame=empty,
            metadata=metadata,
        )


def build_macro_regime_result(series_map: dict[str, SeriesSnapshot]) -> MacroRegimeResult:
    cpi = series_map["CPIAUCSL"].frame
    unrate = series_map["UNRATE"].frame
    dff = series_map["DFF"].frame
    dgs2 = series_map["DGS2"].frame
    dgs10 = series_map["DGS10"].frame
    dfii10 = series_map["DFII10"].frame
    t10yie = series_map["T10YIE"].frame
    t10y2y = series_map["T10Y2Y"].frame

    cpi_yoy = calculate_cpi_yoy(cpi)
    cpi_3m = calculate_cpi_three_month_annualized(cpi)
    unemployment_change = calculate_change_over_period(unrate, 3)
    policy_change = calculate_change_over_period(dff, 3)
    slope = calculate_yield_curve_slope(dgs10, dgs2)
    ten_year_change_5d = calculate_change_over_period(dgs10, 5)
    ten_year_change_20d = calculate_change_over_period(dgs10, 20)
    two_year_change_5d = calculate_change_over_period(dgs2, 5)
    two_year_change_20d = calculate_change_over_period(dgs2, 20)
    real_yield_change_20d = calculate_change_over_period(dfii10, 20)

    inflation_regime = classify_inflation_regime(cpi_yoy, cpi_3m)
    labour_regime = classify_labour_regime(unemployment_change)
    policy_regime = classify_policy_regime(policy_change)
    yield_curve_regime = classify_yield_curve_regime(slope)
    overall_macro_regime = classify_overall_macro_regime(
        inflation_regime,
        labour_regime,
        policy_regime,
        yield_curve_regime,
    )

    summary = pd.DataFrame(
        [
            {"label": "Overall macro regime", "value": overall_macro_regime},
            {"label": "Inflation regime", "value": inflation_regime},
            {"label": "Labour regime", "value": labour_regime},
            {"label": "Policy regime", "value": policy_regime},
            {"label": "Yield-curve regime", "value": yield_curve_regime},
        ]
    )

    latest_observation_timestamp = max(
        (snapshot.latest_observation_date for snapshot in series_map.values() if snapshot.latest_observation_date is not None),
        default=None,
    )

    series_table = pd.DataFrame(
        [
            {
                "Series name": snapshot.title,
                "FRED series ID": snapshot.series_id,
                "Latest value": snapshot.latest_value,
                "Latest observation date": snapshot.latest_observation_date,
                "Frequency": snapshot.frequency,
                "Data status": snapshot.data_status,
            }
            for snapshot in series_map.values()
        ]
    )

    treasury_yield_data = (
        dgs10[["date", "value"]]
        .rename(columns={"value": "10Y"})
        .merge(dgs2[["date", "value"]].rename(columns={"value": "2Y"}), on="date", how="outer")
        .sort_values("date")
        .reset_index(drop=True)
    )

    yield_curve_chart_data = pd.DataFrame(
        {
            "date": t10y2y["date"],
            "spread": t10y2y["value"],
        }
    )

    inflation_chart_data = pd.DataFrame(
        {
            "date": cpi["date"],
            "CPI": cpi["value"],
        }
    )

    unemployment_chart_data = pd.DataFrame(
        {
            "date": unrate["date"],
            "Unemployment rate": unrate["value"],
        }
    )

    indicators = {
        "CPI YoY %": cpi_yoy,
        "CPI 3m annualized %": cpi_3m,
        "Unemployment 3m change": unemployment_change,
        "FFR 3m change": policy_change,
        "2Y change 5d": two_year_change_5d,
        "2Y change 20d": two_year_change_20d,
        "10Y change 5d": ten_year_change_5d,
        "10Y change 20d": ten_year_change_20d,
        "10Y real yield change 20d": real_yield_change_20d,
        "Latest yield-curve slope": slope,
        "T10YIE latest": get_value_near_offset(t10yie, 0),
    }

    return MacroRegimeResult(
        summary=summary,
        series_table=series_table,
        yield_curve_chart_data=yield_curve_chart_data,
        inflation_chart_data=inflation_chart_data,
        unemployment_chart_data=unemployment_chart_data,
        latest_observation_timestamp=latest_observation_timestamp,
        inflation_regime=inflation_regime,
        labour_regime=labour_regime,
        policy_regime=policy_regime,
        yield_curve_regime=yield_curve_regime,
        overall_macro_regime=overall_macro_regime,
        treasury_yield_data=treasury_yield_data,
        indicators=indicators,
    )
