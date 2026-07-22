"""Atomic raw snapshot writers."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd


def write_atomic_parquet(frame: pd.DataFrame, destination: Path) -> None:
    """Write a Parquet file atomically when practical."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False, dir=destination.parent) as handle:
        temp_path = Path(handle.name)
    try:
        frame.to_parquet(temp_path, index=False)
        temp_path.replace(destination)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def write_atomic_json(payload: dict[str, Any], destination: Path) -> None:
    """Write JSON atomically."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, dir=destination.parent, mode="w", encoding="utf-8") as handle:
        temp_path = Path(handle.name)
        json.dump(payload, handle, indent=2, default=str)
    try:
        temp_path.replace(destination)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

