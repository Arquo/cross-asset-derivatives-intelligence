"""Official CFTC Commitments of Traders provider."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time
from io import StringIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from urllib.parse import urljoin
import time as time_module

import pandas as pd
import requests

from cross_asset_intelligence.core.config import CFTCContractConfig
from cross_asset_intelligence.core.exceptions import ConfigurationError, ProviderError

from .base import DataProvider


PUBLIC_REPORTING_BASE = "https://publicreporting.cftc.gov/resource/"
REPORT_DATASETS = {
    "legacy": "6dca-aqww",
    "disaggregated": "72hh-3qpy",
    "tff": "gpe5-46if",
}

NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class CFTCContractFrame:
    """Downloaded raw rows for one configured contract."""

    contract: CFTCContractConfig
    frame: pd.DataFrame
    source_url: str


@dataclass(frozen=True)
class CFTCFetchResult:
    """Result of a CFTC provider run."""

    successful: list[CFTCContractFrame]
    failed: list[dict[str, Any]]
    rows_fetched: int


def cftc_release_timestamp(publication_date: pd.Timestamp | str) -> pd.Timestamp:
    """Create the platform's availability timestamp proxy for CFTC reports."""

    date_value = pd.Timestamp(publication_date).date()
    local = datetime.combine(date_value, time(15, 30), tzinfo=NEW_YORK)
    return pd.Timestamp(local).tz_convert(UTC)


class CFTCProvider(DataProvider):
    """Official public-reporting CFTC provider."""

    def __init__(
        self,
        contracts: list[CFTCContractConfig],
        start_date: str,
        end_date: str | None = None,
        timeout: int = 30,
        retry_count: int = 3,
        session: requests.Session | None = None,
        raw_output_dir: Path | None = None,
    ) -> None:
        self.contracts = [contract for contract in contracts if contract.active]
        self.start_date = start_date
        self.end_date = end_date
        self.timeout = timeout
        self.retry_count = retry_count
        self.session = session or requests.Session()
        self.raw_output_dir = raw_output_dir

    @property
    def provider_name(self) -> str:
        return "CFTC"

    def validate_configuration(self) -> None:
        if not self.contracts:
            raise ConfigurationError("No CFTC contracts are configured.")

    def health_check(self) -> bool:
        return bool(self.contracts)

    def _request_csv(self, dataset_id: str, params: dict[str, Any]) -> pd.DataFrame:
        url = urljoin(PUBLIC_REPORTING_BASE, f"{dataset_id}.csv")
        last_error: Exception | None = None
        for attempt in range(self.retry_count + 1):
            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code == 429 or 500 <= response.status_code < 600:
                last_error = ProviderError(f"Temporary CFTC error {response.status_code} while downloading data.")
                if attempt < self.retry_count:
                    time_module.sleep(min(2 ** attempt, 10))
                    continue
                raise last_error
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise ProviderError("CFTC request failed.") from exc
            frame = pd.read_csv(StringIO(response.text), dtype={"cftc_contract_market_code": "string"})
            return frame
        raise last_error or ProviderError("CFTC request failed.")

    def _build_where_clause(self, contract: CFTCContractConfig) -> str:
        clauses = [
            f"report_date_as_yyyy_mm_dd >= '{self.start_date}'",
        ]
        if self.end_date:
            clauses.append(f"report_date_as_yyyy_mm_dd <= '{self.end_date}'")
        name = contract.official_contract_name.replace("'", "''")
        if contract.cftc_contract_market_code:
            code = contract.cftc_contract_market_code.replace("'", "''")
            clauses.append(f"upper(cftc_contract_market_code) = upper('{code}')")
        else:
            clauses.append(
                "("
                f"upper(contract_market_name) = upper('{name}') OR "
                f"upper(market_and_exchange_names) = upper('{name}')"
                ")"
            )
        return " AND ".join(clauses)

    def _download_contract(self, contract: CFTCContractConfig) -> CFTCContractFrame:
        dataset_id = REPORT_DATASETS.get(contract.report_type.lower())
        if dataset_id is None:
            raise ProviderError(f"Unsupported CFTC report type: {contract.report_type}")
        params = {
            "$where": self._build_where_clause(contract),
            "$order": "report_date_as_yyyy_mm_dd ASC",
            "$limit": 5000,
        }
        frame = self._request_csv(dataset_id, params)
        if frame.empty:
            raise ProviderError(f"No CFTC rows returned for {contract.display_name}.")
        frame.columns = [column.strip().lower() for column in frame.columns]
        identity_column = "cftc_contract_market_code" if "cftc_contract_market_code" in frame.columns else "contract_market_name"
        if identity_column in frame.columns and frame[identity_column].dropna().astype(str).str.strip().str.upper().nunique() > 1:
            raise ProviderError(f"Ambiguous CFTC mapping for {contract.display_name}.")

        matches = frame.copy()
        if contract.cftc_contract_market_code and "cftc_contract_market_code" in matches.columns:
            configured_code = contract.cftc_contract_market_code.strip().upper()
            matches = matches[matches["cftc_contract_market_code"].astype(str).str.strip().str.upper() == configured_code]
        elif "contract_market_name" in matches.columns:
            configured_name = contract.official_contract_name.strip().upper()
            exact_contract = matches["contract_market_name"].astype(str).str.strip().str.upper() == configured_name
            exact_market = (
                matches["market_and_exchange_names"].astype(str).str.strip().str.upper() == configured_name
                if "market_and_exchange_names" in matches.columns
                else pd.Series(False, index=matches.index)
            )
            matches = matches[exact_contract | exact_market]
        if matches.empty:
            raise ProviderError(f"No exact CFTC mapping returned for {contract.display_name}.")
        matches["report_date_as_yyyy_mm_dd"] = pd.to_datetime(matches["report_date_as_yyyy_mm_dd"], utc=True, errors="coerce")
        matches = matches.dropna(subset=["report_date_as_yyyy_mm_dd"]).reset_index(drop=True)
        if matches.empty:
            raise ProviderError(f"No valid CFTC rows returned for {contract.display_name}.")
        return CFTCContractFrame(contract=contract, frame=matches, source_url=f"{PUBLIC_REPORTING_BASE}{dataset_id}.csv")

    def fetch(self) -> CFTCFetchResult:
        self.validate_configuration()
        successful: list[CFTCContractFrame] = []
        failed: list[dict[str, Any]] = []
        rows_fetched = 0
        for contract in self.contracts:
            try:
                result = self._download_contract(contract)
                rows_fetched += len(result.frame)
                successful.append(result)
            except Exception as exc:
                failed.append({"internal_asset_id": contract.internal_asset_id, "error": str(exc)})
        return CFTCFetchResult(successful=successful, failed=failed, rows_fetched=rows_fetched)

    def normalize(self, observations):  # pragma: no cover - normalization happens in pipeline helpers
        return observations
