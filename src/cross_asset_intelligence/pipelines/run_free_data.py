"""Backward-compatible entrypoint for the Phase 2 ingestion pipeline."""

from __future__ import annotations

from cross_asset_intelligence.pipelines.orchestration import main


if __name__ == "__main__":
    raise SystemExit(main())
