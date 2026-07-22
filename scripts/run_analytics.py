from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from cross_asset_intelligence.services.intelligence_service import MarketIntelligenceService


DEFAULT_DATABASE_PATH = Path("data/database/cross_asset.duckdb")
DEFAULT_REPORT_DIR = Path("data/reports")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calculate and persist deterministic market intelligence.")
    parser.add_argument("--as-of", dest="as_of", default=None)
    parser.add_argument("--database-path", default=str(DEFAULT_DATABASE_PATH))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = parse_args(argv)
    service = MarketIntelligenceService(Path(args.database_path))
    as_of = pd.Timestamp(args.as_of, tz="UTC") if args.as_of else None
    snapshot = service.run(as_of=as_of)
    print(f"analytics_run_id={snapshot.analytics_run_id}")
    print(f"screener_rows={len(snapshot.screener)}")
    print(f"liquidity_rows={len(snapshot.liquidity)}")
    print(f"positioning_rows={len(snapshot.positioning)}")
    print(f"option_analytics_rows={len(snapshot.options)}")
    print(f"summary_rows={len(snapshot.summary)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
