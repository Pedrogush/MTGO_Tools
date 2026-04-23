"""Collection-file I/O for :class:`CardRepository`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import msgspec
import msgspec.json
from loguru import logger


class _CollectionEntry(msgspec.Struct, gc=False):
    # Only the three fields we actually need; all other keys in the JSON object
    # are silently ignored by msgspec.
    name: str
    quantity: float  # Accept int or float; we coerce to int after decoding.
    id: Any = None  # Optional UUID / numeric card ID


_collection_any_decoder: msgspec.json.Decoder[Any] = msgspec.json.Decoder(Any)


class CollectionMixin:
    """Read MTGO/Scryfall-shaped collection files into normalized dicts."""

    def load_collection_from_file(self, filepath: Path) -> list[dict[str, Any]]:
        def _extract_cards(payload: Any) -> list[Any]:
            if isinstance(payload, list):
                return payload

            if isinstance(payload, dict):
                for key in ("cards", "items"):
                    candidate = payload.get(key)
                    if isinstance(candidate, list):
                        return candidate

                collection = payload.get("collection")
                if collection is not None:
                    return _extract_cards(collection)

            return []

        try:
            raw_data = filepath.read_bytes()
        except FileNotFoundError:
            logger.info(f"Collection file {filepath} does not exist")
            return []
        except OSError as exc:
            logger.error(f"Unable to read collection file {filepath}: {exc}")
            return []

        # Decode the outer wrapper (may be a list or a dict with a nested list)
        # using the untyped Any decoder so the existing _extract_cards logic works.
        try:
            payload = _collection_any_decoder.decode(raw_data)
        except msgspec.DecodeError as exc:
            logger.error(f"Invalid JSON in collection file {filepath}: {exc}")
            return []

        raw_entries = _extract_cards(payload)
        if not raw_entries:
            logger.warning(f"No card entries found in collection file {filepath}")
            return []

        parsed_cards: list[dict[str, Any]] = []
        for entry in raw_entries:
            if not isinstance(entry, dict):
                continue

            name = str(entry.get("name", "")).strip()
            if not name:
                continue

            quantity_raw = entry.get("quantity", 0)
            try:
                quantity = int(quantity_raw)
            except (TypeError, ValueError):
                try:
                    quantity = int(float(quantity_raw))
                except (TypeError, ValueError):
                    logger.debug(f"Skipping {name}: invalid quantity {quantity_raw!r}")
                    continue

            if quantity < 0:
                logger.debug(f"Skipping {name}: negative quantity {quantity}")
                continue

            normalized: dict[str, Any] = {"name": name, "quantity": quantity}
            if "id" in entry:
                normalized["id"] = entry.get("id")

            parsed_cards.append(normalized)

        logger.info(f"Loaded {len(parsed_cards)} cards from {filepath}")
        return parsed_cards

    def get_collection_cache_path(self) -> Path:
        from utils.constants import CACHE_DIR

        return CACHE_DIR / "collection.json"
