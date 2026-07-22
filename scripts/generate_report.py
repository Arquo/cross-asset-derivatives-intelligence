from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from cross_asset_intelligence.reporting.report_repository import ReportRepository
from cross_asset_intelligence.services.analytics_service import AnalyticsService


DEFAULT_DATABASE_PATH = Path("data/database/cross_asset.duckdb")
DEFAULT_REPORT_DIR = Path("data/reports")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate deterministic markdown and JSON market reports.")
    parser.add_argument("--as-of", dest="as_of", default=None)
    parser.add_argument("--database-path", default=str(DEFAULT_DATABASE_PATH))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = parse_args(argv)
    service = AnalyticsService(Path(args.database_path))
    as_of = pd.Timestamp(args.as_of, tz="UTC") if args.as_of else None
    snapshot = service.build_snapshot(as_of=as_of)
    if snapshot.packet is None:
        print("No deterministic report could be generated.")
        return 1
    repository = ReportRepository(Path(args.report_dir))
    json_path, md_path = repository.save_report(snapshot.packet)
    print(f"json={json_path}")
    print(f"markdown={md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

