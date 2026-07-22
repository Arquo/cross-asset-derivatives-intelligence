from __future__ import annotations

from pathlib import Path

from cross_asset_intelligence.storage.duckdb_store import connect_duckdb, initialize_database


DATABASE_PATH = Path("data/database/cross_asset.duckdb")


def main() -> int:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect_duckdb(DATABASE_PATH) as connection:
        initialize_database(connection)
    print(f"Initialized database at {DATABASE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
