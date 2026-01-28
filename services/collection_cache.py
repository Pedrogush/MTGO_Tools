"""Cache discovery helpers for collection files."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from utils.constants import ONE_HOUR_SECONDS


def find_latest_cached_file(
    directory: Path, pattern: str = "collection_full_trade_*.json"
) -> Path | None:
    """Return the most recent cached collection file in a directory."""
    files = sorted(directory.glob(pattern))
    return files[-1] if files else None


def get_file_age_hours(filepath: Path) -> int:
    """Return the age of a file in whole hours."""
    file_age_seconds = datetime.now().timestamp() - filepath.stat().st_mtime
    return int(file_age_seconds / ONE_HOUR_SECONDS)
