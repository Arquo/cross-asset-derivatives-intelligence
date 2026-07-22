"""Normalization helpers for CFTC raw observations."""

from __future__ import annotations

from typing import Any

import pandas as pd

from cross_asset_intelligence.analytics.common import ensure_datetime_column
from cross_asset_intelligence.core.config import CFTCContractConfig
from cross_asset_intelligence.core.constants import QualityStatus
from cross_asset_intelligence.pipelines.normalization import make_record_id, utc_now
from cross_asset_intelligence.providers.cftc import cftc_release_timestamp


PARTICIPANT_COLUMN_MAP = {
    "tff": [
        ("Dealer or intermediary", "dealer_positions_long_all", "dealer_positions_short_all", "dealer_positions_spread_all", "dealer_traders_tot_all"),
        ("Asset manager or institutional", "asset_mgr_positions_long", "asset_mgr_positions_short", "asset_mgr_positions_spread", "asset_mgr_traders_tot_all"),
        ("Leveraged funds", ("lev_money_positions_long", "lev_money_positions_long_all"), ("lev_money_positions_short", "lev_money_positions_short_all"), ("lev_money_positions_spread", "lev_money_positions_spread_all"), "lev_money_traders_tot_all"),
        ("Other reportable", ("other_rept_positions_long", "other_rept_positions_long_all"), ("other_rept_positions_short", "other_rept_positions_short_all"), ("other_rept_positions_spread", "other_rept_positions_spread_all"), "other_rept_traders_tot_all"),
        ("Non-reportable", "nonrept_positions_long_all", "nonrept_positions_short_all", None, "nonrept_traders_tot_all"),
    ],
    "disaggregated": [
        ("Swap dealers", "swap_positions_long_all", ("swap__positions_short_all", "swap_positions_short_all"), ("swap__positions_spread_all", "swap_positions_spread_all"), "swap_traders_tot_all"),
        ("Producer/Merchant/Processor/User", ("prod_merc_positions_long", "prod_merc_positions_long_all"), ("prod_merc_positions_short", "prod_merc_positions_short_all"), None, "prod_merc_traders_tot_all"),
        ("Managed money", "m_money_positions_long_all", "m_money_positions_short_all", ("m_money_positions_spread", "m_money_positions_spread_all"), "m_money_traders_tot_all"),
        ("Other reportable", ("other_rept_positions_long", "other_rept_positions_long_all"), ("other_rept_positions_short", "other_rept_positions_short_all"), ("other_rept_positions_spread", "other_rept_positions_spread_all"), "other_rept_traders_tot_all"),
        ("Non-reportable", "nonrept_positions_long_all", "nonrept_positions_short_all", None, "nonrept_traders_tot_all"),
    ],
    "legacy": [
        ("Dealer or intermediary", "comm_positions_long_all", "comm_positions_short_all", "comm_positions_spread_all", "comm_traders_tot_all"),
        ("Leveraged funds", "noncomm_positions_long_all", "noncomm_positions_short_all", "noncomm_positions_spread_all", "noncomm_traders_tot_all"),
        ("Non-reportable", "nonrept_positions_long_all", "nonrept_positions_short_all", None, "nonrept_traders_tot_all"),
    ],
}


def _resolve_column(frame: pd.DataFrame, candidates: str | tuple[str, ...] | None) -> str | None:
    if candidates is None:
        return None
    names = (candidates,) if isinstance(candidates, str) else candidates
    return next((name for name in names if name in frame.columns), None)


def _publication_date(report_date: pd.Timestamp) -> pd.Timestamp:
    """Approximate the public availability date from the Tuesday report date."""

    ts = pd.Timestamp(report_date)
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    publication = (ts.normalize() + pd.offsets.BDay(3)).tz_localize("UTC") if (ts.normalize() + pd.offsets.BDay(3)).tzinfo is None else ts.normalize() + pd.offsets.BDay(3)
    return publication


def _normalize_contract_frame(contract: CFTCContractConfig, frame: pd.DataFrame, pipeline_run_id: str, source_reference: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    working = frame.copy()
    working = ensure_datetime_column(working, "report_date_as_yyyy_mm_dd")
    working["report_date"] = working["report_date_as_yyyy_mm_dd"].dt.tz_convert("UTC")
    working["publication_date"] = working["report_date"].apply(_publication_date)
    working["available_ts"] = working["publication_date"].apply(cftc_release_timestamp)
    working["ingested_ts"] = utc_now()
    working["pipeline_run_id"] = pipeline_run_id
    working["internal_asset_id"] = contract.internal_asset_id
    working["contract_name"] = working.get("contract_market_name", contract.official_contract_name)
    working["exchange"] = working.get("market_and_exchange_names", contract.exchange)
    working["report_type"] = contract.report_type
    if "cftc_contract_market_code" not in working.columns:
        working["cftc_contract_market_code"] = contract.cftc_contract_market_code
    working["source_reference"] = source_reference
    return working


def normalize_cftc_fetch_result(result, pipeline_run_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize downloaded CFTC rows into canonical positioning observations."""

    rows: list[pd.DataFrame] = []
    warnings: list[dict[str, Any]] = []
    for contract_frame in result.successful:
        contract = contract_frame.contract
        frame = _normalize_contract_frame(contract, contract_frame.frame, pipeline_run_id, contract_frame.source_url)
        categories = PARTICIPANT_COLUMN_MAP.get(contract.report_type.lower(), [])
        if not categories:
            warnings.append({"internal_asset_id": contract.internal_asset_id, "message": f"Unsupported report type {contract.report_type}."})
            continue
        for participant_category, long_col, short_col, spread_col, trader_col in categories:
            resolved_long = _resolve_column(frame, long_col)
            resolved_short = _resolve_column(frame, short_col)
            resolved_spread = _resolve_column(frame, spread_col)
            resolved_trader = _resolve_column(frame, trader_col)
            if resolved_long is None or resolved_short is None:
                warnings.append({"internal_asset_id": contract.internal_asset_id, "message": f"Missing participant columns for {participant_category}."})
                continue
            subset = frame.copy()
            subset["participant_category"] = participant_category
            subset["long_contracts"] = pd.to_numeric(subset[resolved_long], errors="coerce")
            subset["short_contracts"] = pd.to_numeric(subset[resolved_short], errors="coerce")
            subset["spreading_contracts"] = pd.to_numeric(subset[resolved_spread], errors="coerce") if resolved_spread else pd.NA
            subset["open_interest"] = pd.to_numeric(subset.get("open_interest_all"), errors="coerce")
            subset["trader_count"] = pd.to_numeric(subset[resolved_trader], errors="coerce") if resolved_trader else pd.NA
            subset["record_id"] = subset.apply(
                lambda row: make_record_id(
                    contract.internal_asset_id,
                    row["report_date"].isoformat() if pd.notna(row["report_date"]) else None,
                    contract.report_type,
                    participant_category,
                ),
                axis=1,
            )
            subset["quality_flags"] = subset.apply(
                lambda row: [
                    flag
                    for flag in [
                        "missing_long" if pd.isna(row["long_contracts"]) else None,
                        "missing_short" if pd.isna(row["short_contracts"]) else None,
                        "missing_open_interest" if pd.isna(row["open_interest"]) else None,
                        "weekly_delayed_data",
                    ]
                    if flag
                ],
                axis=1,
            )
            subset["quality_status"] = subset["quality_flags"].apply(lambda flags: QualityStatus.warning.value if flags else QualityStatus.valid.value)
            rows.append(
                subset[
                    [
                        "record_id",
                        "internal_asset_id",
                        "cftc_contract_market_code",
                        "contract_name",
                        "exchange",
                        "report_type",
                        "report_date",
                        "publication_date",
                        "available_ts",
                        "ingested_ts",
                        "participant_category",
                        "long_contracts",
                        "short_contracts",
                        "spreading_contracts",
                        "open_interest",
                        "trader_count",
                        "source_reference",
                        "quality_status",
                        "quality_flags",
                        "pipeline_run_id",
                    ]
                ]
            )
    normalized = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    warnings_frame = pd.DataFrame(warnings)
    return normalized, warnings_frame
