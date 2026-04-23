"""Export helpers for collection data."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class ExporterMixin:
    """Export collection card lists to timestamped JSON files."""

    def export_to_file(
        self,
        cards: list[dict[str, Any]],
        directory: Path,
        filename_prefix: str = "collection_full_trade",
    ) -> Path:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{filename_prefix}_{timestamp}.json"
            filepath = directory / filename

            with filepath.open("w", encoding="utf-8") as f:
                json.dump(cards, f, indent=2)

            logger.info(f"Exported collection to {filepath} ({len(cards)} cards)")
            return filepath
        except OSError as exc:
            logger.error(f"Failed to export collection: {exc}")
            raise
        except (TypeError, ValueError) as exc:
            logger.error(f"Invalid card data for export: {exc}")
            raise ValueError("Invalid card data for export") from exc
