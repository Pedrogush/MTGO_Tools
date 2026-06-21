"""Sideboard guide/outboard persistence and state I/O handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from utils.atomic_io import atomic_write_json
from utils.constants import ACTIVE_GUIDE_FILE
from utils.constants.app import DECK_HASH_DISPLAY_LENGTH

if TYPE_CHECKING:
    from widgets.frames.app_frame import AppFrame
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class SideboardGuidePersistenceHandlers(_Base):
    """Persistence/state I/O for guides, outboards, and the pin indicator."""

    def _parse_card_text(self: AppFrame, text: str) -> dict[str, int]:
        if not text or not isinstance(text, str):
            return {}

        result: dict[str, int] = {}
        lines = text.replace(",", "\n").split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                qty_str, name = parts
                qty_str = qty_str.rstrip("x")
                try:
                    qty = int(qty_str)
                    result[name.strip()] = qty
                    continue
                except ValueError:
                    pass
            result[line] = 1
        return result

    def _persist_outboard_for_current(self: AppFrame) -> None:
        key = self.controller.deck_repo.get_current_deck_key()
        self.controller.outboard_store[key] = self.zone_cards.get("out", [])
        self.controller.store_service.save_store(
            self.controller.outboard_store_path, self.controller.outboard_store
        )

    def _load_outboard_for_current(self: AppFrame) -> list[dict[str, Any]]:
        key = self.controller.deck_repo.get_current_deck_key()
        data = self.controller.outboard_store.get(key, [])
        cleaned: list[dict[str, Any]] = []
        for entry in data:
            name = entry.get("name")
            qty_raw = entry.get("qty", 0)
            try:
                qty_float = float(qty_raw)
                qty = int(qty_float) if qty_float.is_integer() else qty_float
            except (TypeError, ValueError):
                qty = 0
            if name and qty > 0:
                cleaned.append({"name": name, "qty": qty})
        return cleaned

    def _refresh_pin_indicator(self: AppFrame) -> None:
        if not ACTIVE_GUIDE_FILE.exists():
            self.sideboard_guide_panel.set_pinned(False)
            return
        try:
            import json

            with ACTIVE_GUIDE_FILE.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            current_hash = self.controller.deck_repo.get_current_decklist_hash()
            self.sideboard_guide_panel.set_pinned(data.get("deck_hash") == current_hash)
        except Exception:
            self.sideboard_guide_panel.set_pinned(False)

    def _load_guide_for_current(self: AppFrame) -> None:
        # Use decklist hash so each unique 75 has its own guide
        key = self.controller.deck_repo.get_current_decklist_hash()
        payload = self.controller.guide_store.get(key) or {}
        entries = payload.get("entries", [])

        migrated_entries = []
        for entry in entries:
            if "cards_in" in entry or "cards_out" in entry:
                play_out = self._parse_card_text(entry.get("cards_out", ""))
                play_in = self._parse_card_text(entry.get("cards_in", ""))
                migrated_entries.append(
                    {
                        "archetype": entry.get("archetype", ""),
                        "play_out": play_out,
                        "play_in": play_in,
                        "draw_out": play_out.copy(),
                        "draw_in": play_in.copy(),
                        "notes": entry.get("notes", ""),
                    }
                )
            else:
                migrated = entry.copy()
                for field in ["play_out", "play_in", "draw_out", "draw_in"]:
                    if field in migrated and isinstance(migrated[field], str):
                        migrated[field] = self._parse_card_text(migrated[field])
                migrated_entries.append(migrated)

        self.sideboard_guide_entries = migrated_entries
        self.sideboard_exclusions = payload.get("exclusions", [])
        self.sideboard_flex_slots = payload.get("flex_slots", [])
        self.sideboard_guide_panel.set_entries(
            self.sideboard_guide_entries, self.sideboard_exclusions
        )
        self._refresh_pin_indicator()

    def _persist_guide_for_current(self: AppFrame) -> None:
        key = self.controller.deck_repo.get_current_decklist_hash()
        self.controller.guide_store[key] = {
            "entries": self.sideboard_guide_entries,
            "exclusions": self.sideboard_exclusions,
            "flex_slots": self.sideboard_flex_slots,
        }
        self.controller.store_service.save_store(
            self.controller.guide_store_path, self.controller.guide_store
        )

    def _on_pin_guide(self: AppFrame) -> None:
        deck_hash = self.controller.deck_repo.get_current_decklist_hash()
        current_deck = self.controller.deck_repo.get_current_deck()
        deck_name = ""
        if current_deck:
            deck_name = current_deck.get("name") or current_deck.get("archetype") or ""

        payload = {"deck_hash": deck_hash, "deck_name": deck_name}
        try:
            atomic_write_json(ACTIVE_GUIDE_FILE, payload, indent=2)
            self.sideboard_guide_panel.set_pinned(True)
            self._set_status(
                "guide.status.pinned", name=deck_name or deck_hash[:DECK_HASH_DISPLAY_LENGTH]
            )
            logger.info(f"Pinned guide: hash={deck_hash}, name={deck_name!r}")
        except OSError as exc:
            logger.error(f"Failed to save active guide: {exc}")
            self._set_status("guide.status.pin_error")
