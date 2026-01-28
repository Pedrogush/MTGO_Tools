from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

from curl_cffi import requests
from loguru import logger

from utils.constants import (
    ATOMIC_DATA_DOWNLOAD_TIMEOUT_SECONDS,
    ATOMIC_DATA_HEAD_TIMEOUT_SECONDS,
    ATOMIC_DATA_URL,
    CARD_DATA_DIR,
)


def load_card_manager(data_dir: Path | str = CARD_DATA_DIR, force: bool = False) -> CardDataManager:
    """
    Load and return a CardDataManager with the latest card data.

    This is a synchronous function intended to be called from a background thread.
    It will download/update card data if needed and return a ready-to-use manager.

    Args:
        data_dir: Directory to store card data (default: "data")
        force: Force refresh even if data is up-to-date

    Returns:
        CardDataManager instance with loaded card data

    Raises:
        RuntimeError: If card data cannot be loaded and no cache exists
    """
    manager = CardDataManager(data_dir)
    manager.ensure_latest(force=force)
    return manager


class CardDataManager:
    def __init__(self, data_dir: Path | str = CARD_DATA_DIR):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.data_dir / "atomic_cards_index.json"
        self.meta_path = self.data_dir / "atomic_cards_meta.json"
        self._cards: list[dict[str, Any]] | None = None
        self._cards_by_name: dict[str, dict[str, Any]] | None = None

    def ensure_latest(self, force: bool = False) -> None:

        remote_meta = self._fetch_remote_meta()
        local_meta = self._load_json(self.meta_path) or {}
        missing_index = not self.index_path.exists()
        needs_refresh = force or missing_index
        if not needs_refresh and remote_meta:
            remote_size = remote_meta.get("content_length")
            local_size = local_meta.get("content_length")
            if remote_size and local_size != remote_size:
                logger.warning(f"File size changed: local={local_size}, remote={remote_size}")
                logger.warning("Forcing a refresh")
                needs_refresh = True

        if needs_refresh:
            logger.warning("No atomic card index found or force refresh requested")
            try:
                if remote_meta:
                    logger.info("Refreshing MTGJSON AtomicCards dataset")
                else:
                    logger.info("Fetching MTGJSON AtomicCards dataset (using headers for metadata)")
                self._download_and_rebuild(remote_meta)
            except Exception as exc:
                if missing_index:
                    raise RuntimeError(
                        "Card data download failed and no cache is available"
                    ) from exc
                logger.warning(f"Failed to refresh MTGJSON data, using cache: {exc}")
        self._load_index()

    def search_cards(
        self,
        query: str = "",
        format_filter: str | None = None,
        type_filter: str | None = None,
        color_identity: list[str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        self._require_cards()
        query = (query or "").strip().lower()
        fmt = (format_filter or "").strip().lower()
        type_filter = (type_filter or "").strip().lower()
        color_identity = [c.upper() for c in (color_identity or [])]
        results: list[dict[str, Any]] = []
        for card in self._cards or []:
            name_lower = card["name_lower"]
            type_line = (card.get("type_line") or "").lower()
            oracle_text = (card.get("oracle_text") or "").lower()
            if query:
                haystacks = (
                    name_lower,
                    type_line,
                    oracle_text,
                )
                if not any(query in h for h in haystacks if h):
                    continue
            if fmt and card.get("legalities", {}).get(fmt) != "Legal":
                continue
            if type_filter and type_filter not in type_line:
                continue
            if color_identity:
                identity = card.get("color_identity", [])
                if not all(c in identity for c in color_identity):
                    continue
            results.append(card)
            if limit and len(results) >= limit:
                break
        return results

    def get_card(self, name: str) -> dict[str, Any] | None:
        self._require_cards()
        return (self._cards_by_name or {}).get(name.lower())

    def available_formats(self) -> list[str]:
        self._require_cards()
        seen = set()
        formats: list[str] = []
        for card in self._cards or []:
            for fmt, state in (card.get("legalities") or {}).items():
                if state != "Legal" or fmt in seen:
                    continue
                seen.add(fmt)
                formats.append(fmt)
        return sorted(formats)

    def _require_cards(self) -> None:
        if self._cards is None:
            raise RuntimeError("Card data not loaded; call ensure_latest first")

    def _fetch_remote_meta(self) -> dict[str, Any] | None:
        return self._fetch_dataset_headers()

    def _fetch_dataset_headers(self) -> dict[str, Any] | None:
        try:
            resp = requests.head(
                ATOMIC_DATA_URL,
                impersonate="chrome",
                timeout=ATOMIC_DATA_HEAD_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning(f"Failed to fetch MTGJSON dataset headers: {exc}")
            return None
        meta: dict[str, Any] = {}
        headers = {k.lower(): v for k, v in resp.headers.items()}  # type: ignore[arg-type]
        if "etag" in headers:
            meta["etag"] = headers["etag"].strip('"')
        if "last-modified" in headers:
            meta["last_modified"] = headers["last-modified"]
        if "content-length" in headers:
            meta["content_length"] = headers["content-length"]
        return meta or None

    def _download_and_rebuild(self, remote_meta: dict[str, Any] | None) -> None:
        resp = requests.get(
            ATOMIC_DATA_URL,
            impersonate="chrome",
            timeout=ATOMIC_DATA_DOWNLOAD_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        content = resp.content
        digest = hashlib.sha512(content).hexdigest()
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            with zf.open("AtomicCards.json") as source:
                raw = json.load(source)
        index = self._build_index(raw.get("data", {}))
        self.index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        meta_to_store: dict[str, Any] = remote_meta.copy() if remote_meta else {}
        meta_to_store.setdefault("sha512", digest)
        headers = {k.lower(): v for k, v in resp.headers.items()}  # type: ignore[arg-type]
        if "etag" in headers:
            meta_to_store.setdefault("etag", headers["etag"].strip('"'))
        if "last-modified" in headers:
            meta_to_store.setdefault("last_modified", headers["last-modified"])
        if "content-length" in headers:
            meta_to_store.setdefault("content_length", headers["content-length"])
        self.meta_path.write_text(json.dumps(meta_to_store, ensure_ascii=False), encoding="utf-8")
        self._cards = index["cards"]
        self._cards_by_name = index["cards_by_name"]

    def _load_index(self) -> None:
        data = self._load_json(self.index_path)
        if not data:
            raise RuntimeError("Card data index missing or invalid")
        self._cards = data["cards"]
        self._cards_by_name = data["cards_by_name"]

    def _load_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning(f"Invalid JSON at {path}: {exc}")
            return None

    def _build_index(self, atomic_cards: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        cards: dict[str, dict[str, Any]] = {}
        alias_map: dict[str, dict[str, Any]] = {}
        for variations in atomic_cards.values():
            if not isinstance(variations, list):
                continue
            for printing in variations:
                if printing.get("isToken") or printing.get("layout") == "token":
                    continue
                canonical_name = (printing.get("name") or printing.get("faceName") or "").strip()
                if not canonical_name:
                    continue
                key = canonical_name.lower()
                existing = cards.get(key)
                candidate = self._simplify_printing(printing, canonical_name)
                if not existing:
                    cards[key] = candidate
                else:
                    existing["legalities"] = self._merge_legalities(
                        existing.get("legalities"), candidate.get("legalities")
                    )
                aliases = candidate.setdefault("aliases", set())
                aliases.update(self._collect_name_aliases(canonical_name, printing))
        card_list = sorted(cards.values(), key=lambda c: c["name_lower"])
        for card in card_list:
            alias_set = card.pop("aliases", set()) or set()
            alias_set.add(card["name"])
            cleaned_aliases = sorted({alias.strip() for alias in alias_set if alias})
            card["aliases"] = cleaned_aliases
            for alias in cleaned_aliases:
                alias_map.setdefault(alias.lower(), card)
        return {
            "cards": card_list,
            "cards_by_name": alias_map,
        }

    def _simplify_printing(self, printing: dict[str, Any], canonical_name: str) -> dict[str, Any]:
        legalities = printing.get("legalities") or {}
        mana_value = printing.get("manaValue")
        if isinstance(mana_value, str):
            try:
                mana_value = float(mana_value)
            except ValueError:
                pass
        simplified = {
            "name": canonical_name,
            "name_lower": canonical_name.lower(),
            "mana_cost": printing.get("manaCost"),
            "mana_value": mana_value,
            "type_line": printing.get("type"),
            "oracle_text": printing.get("text"),
            "power": printing.get("power"),
            "toughness": printing.get("toughness"),
            "loyalty": printing.get("loyalty"),
            "colors": printing.get("colors") or [],
            "color_identity": printing.get("colorIdentity") or [],
            "legalities": {k.lower(): v for k, v in legalities.items()},
            "aliases": set(),
        }
        return simplified

    @staticmethod
    def _collect_name_aliases(canonical_name: str, printing: dict[str, Any]) -> set[str]:
        """Gather alias names for a printing, including individual faces."""
        aliases: set[str] = set()
        face_name = (printing.get("faceName") or "").strip()
        if face_name:
            aliases.add(face_name)
        if canonical_name:
            aliases.add(canonical_name)
            if "//" in canonical_name:
                for piece in canonical_name.split("//"):
                    alias = piece.strip()
                    if alias:
                        aliases.add(alias)
        return aliases

    def _merge_legalities(
        self,
        base: dict[str, Any] | None,
        incoming: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for source in (base or {}), (incoming or {}):
            for fmt, state in source.items():
                if state == "Legal":
                    merged[fmt] = state
        return merged


__all__ = ["CardDataManager", "load_card_manager"]
