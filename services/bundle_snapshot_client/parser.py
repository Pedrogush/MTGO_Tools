"""Bundle archive parser — extracts tar entries into grouped JSON payloads."""

from __future__ import annotations

import io
import json
import tarfile
from typing import Any

from loguru import logger


class BundleParserMixin:
    """Parse the downloaded tar.gz bundle into grouped artifact entries."""

    def _parse_bundle(self, bundle_bytes: bytes) -> tuple[
        dict[str, Any],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[tuple[str, str, str]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        """Extract the bundle and return bundle entries grouped by artifact type.

        Each archetype entry is the full parsed JSON from
        ``latest/archetypes/{format}.json``.  Each deck entry is the full parsed
        JSON from ``latest/decks/{format}/{slug}.json``.  Each deck_texts element
        is a ``(deck_id, deck_text, source)`` tuple ready for ``DeckTextCache.bulk_set``,
        extracted from ``archive/deck-texts/{format}/{id}.json``.
        Each mtgo_decklist entry is the full parsed JSON from
        ``latest/mtgo-decklists/{format}.json``.
        """
        manifest: dict[str, Any] = {}
        archetype_entries: list[dict[str, Any]] = []
        deck_entries: list[dict[str, Any]] = []
        deck_texts: list[tuple[str, str, str]] = []
        card_pool_entries: list[dict[str, Any]] = []
        radar_entries: list[dict[str, Any]] = []
        mtgo_decklist_entries: list[dict[str, Any]] = []

        with tarfile.open(fileobj=io.BytesIO(bundle_bytes), mode="r:gz") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue

                name = member.name
                fobj = tf.extractfile(member)
                if fobj is None:
                    continue

                try:
                    data = json.loads(fobj.read().decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    logger.debug(f"Skipping {name!r}: {exc}")
                    continue

                if name.endswith("latest.json"):
                    manifest = data
                elif name.startswith("latest/mtgo-decklists/") and name.endswith(".json"):
                    mtgo_decklist_entries.append(data)
                elif "/archetypes/" in name and name.endswith(".json"):
                    archetype_entries.append(data)
                elif "/card-pools/" in name and name.endswith(".json"):
                    card_pool_entries.append(data)
                elif name.startswith("archive/deck-texts/") and name.endswith(".json"):
                    deck_id = data.get("deck_id", "")
                    text = data.get("deck_text", "")
                    source = data.get("source", "mtggoldfish")
                    if deck_id and text:
                        deck_texts.append((deck_id, text, source))
                elif "/radars/" in name and name.endswith(".json"):
                    radar_entries.append(data)
                elif "/decks/" in name and name.endswith(".json"):
                    deck_entries.append(data)

        return (
            manifest,
            archetype_entries,
            deck_entries,
            deck_texts,
            card_pool_entries,
            radar_entries,
            mtgo_decklist_entries,
        )
