"""Deck download, text building, saving, and daily-average computation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from services.card_rarity_service import get_card_rarity_service
from services.gamelog_service import detect_format_from_cards
from utils.perf import perf_phase

if TYPE_CHECKING:
    from controllers.app_controller.protocol import AppControllerProto

    _Base = AppControllerProto
else:
    _Base = object


class DeckManagementMixin(_Base):
    """Per-deck download/save/build plus daily-average orchestration."""

    def download_deck_text(
        self,
        deck_number: str,
        on_success: Callable[[str], None],
        on_error: Callable[[Exception], None],
        on_status: Callable[..., None],
    ) -> None:
        if not deck_number:
            on_error(ValueError("Deck identifier missing"))
            return

        on_status("app.status.downloading_deck")

        source_filter = self.get_deck_data_source()

        def worker(number: str):
            # PERF: this runs on the worker thread (off the UI thread). It is
            # the "download" leg of click-to-ready — a SQLite cache hit when the
            # deck text is local, an HTTP scrape of MTGGoldfish on a cache miss.
            with perf_phase("deck download (worker thread, cache or network)"):
                return self.workflow_service.download_deck_text(number, source_filter=source_filter)

        self._worker.submit(worker, deck_number, on_success=on_success, on_error=on_error)

    def build_deck_text(self, zone_cards: dict[str, list[dict[str, Any]]] | None = None) -> str:
        zones = zone_cards if zone_cards is not None else self.zone_cards
        return self.workflow_service.build_deck_text(zones)

    def save_deck(
        self,
        deck_name: str,
        deck_content: str,
        format_name: str,
        deck: dict[str, Any] | None = None,
        file_path: Path | None = None,
        archetype: str | None = None,
    ) -> tuple[Path, int | None]:
        if deck is None:
            # A deck with no record of its own -- built from scratch, or loaded
            # as bare text -- acquires one by being saved. Without this it keeps
            # falling back to the "manual" key, so its versions pile up in a
            # history no deck ever looks at again.
            #
            # Made *before* the save, and empty: the save is what stamps the
            # deck's stable id, and it can only stamp a record that exists by
            # then, while what the deck is called is only settled once the file
            # has been written. An empty record answers every question the save
            # asks of it the same way no record did.
            deck = {}
            self.deck_repo.set_current_deck(deck)
        saved_path, deck_id = self.workflow_service.save_deck(
            deck_name=deck_name,
            deck_content=deck_content,
            format_name=format_name,
            deck=deck,
            deck_save_dir=self.deck_save_dir,
            file_path=file_path,
            archetype=archetype,
        )
        deck.setdefault("href", saved_path.stem)
        deck.setdefault("name", saved_path.stem)
        self._sync_saved_deck_record(deck, saved_path, format_name, archetype)
        return saved_path, deck_id

    @staticmethod
    def _sync_saved_deck_record(
        deck: dict[str, Any] | None,
        saved_path: Path,
        format_name: str,
        archetype: str | None,
    ) -> None:
        """Point the in-memory deck record at what was just written.

        Every save path ends here, which is the reason this lives on the
        controller rather than in the Save dialog's handler. The version history
        follows the deck's stable id now, so a stale ``path`` no longer splits
        one deck's commits across two repos -- but it is still the file a
        checkout is allowed to rewrite, and it is how the *next* session finds
        the saved-decks row that hands the deck its id back. A record left
        pointing at a scraped ``href`` (or at the file it was *loaded* from,
        after a Save As under a new name) therefore loses the deck its versions
        the next time it is opened.
        """
        if deck is None:
            return
        deck["format"] = format_name
        if archetype:
            deck["archetype"] = archetype
        else:
            deck.pop("archetype", None)
        deck["path"] = str(saved_path)
        deck["source"] = "file"

    def find_saved_deck(self, file_path: Path, deck_text: str) -> dict[str, Any] | None:
        """The saved-deck record (format, archetype, ...) for a deck file, if any.

        Best effort, like the save it reads back: a database problem must never
        stop a deck file from loading.
        """
        try:
            return self.workflow_service.deck_repo.find_saved_deck(
                file_path=file_path, deck_content=deck_text
            )
        except Exception as exc:  # noqa: BLE001 - the file itself already loaded
            logger.warning(f"Saved-deck lookup failed for {file_path}: {exc}")
            return None

    def detect_deck_format(self, deck_text: str) -> str:
        """The format a deck list reads as, or ``""`` when it cannot be told.

        The same detector Match History uses (legality intersection, plus the
        rarity test for Pauper). The rarity index is only consulted if something
        has already loaded it: building it reads the Scryfall bulk file, which is
        not something to do on the UI thread behind a Save click. Without it a
        Pauper list reads as the most restrictive constructed format it is legal
        in, and the save dialog lets the user correct that.
        """
        stats = self.deck_service.analyze_deck(deck_text)
        names = [name for name, _qty in stats["mainboard_cards"]]
        names += [name for name, _qty in stats["sideboard_cards"]]
        if not names:
            return ""
        rarity_service = get_card_rarity_service()
        detected = detect_format_from_cards(
            names,
            self.card_service.get_card_manager(),
            last_parsed_format="",
            rarity_index=rarity_service if rarity_service.is_loaded else None,
        )
        return detected or ""

    def load_archetype_names(
        self,
        mtg_format: str,
        on_success: Callable[[list[str]], None],
    ) -> None:
        """Deliver the archetype names for ``mtg_format``, from the metagame list.

        The list the research panel shows already holds them for the current
        format, so that answers synchronously. Any other format goes through the
        metagame repository (local cache, then the remote bundle) on the worker
        thread; a failure delivers an empty list rather than an error, because an
        archetype is optional when saving.
        """
        if mtg_format == self.current_format and self.archetypes:
            on_success([str(entry.get("name", "")) for entry in self.archetypes])
            return

        def loader(fmt: str) -> list[str]:
            archetypes = self.metagame_service.get_archetypes_for_format(fmt)
            return [str(entry.get("name", "")) for entry in archetypes or []]

        def error_handler(error: Exception) -> None:
            logger.warning(f"Archetype list unavailable for {mtg_format}: {error}")
            on_success([])

        self._worker.submit(loader, mtg_format, on_success=on_success, on_error=error_handler)

    def build_daily_average_deck(
        self,
        on_success: Callable[[str], None],
        on_error: Callable[[Exception], None],
        on_status: Callable[[str], None],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> tuple[bool, str]:
        cutoff_date = (datetime.now() - timedelta(hours=self._average_hours)).strftime("%Y-%m-%d")
        todays_decks = [
            deck
            for deck in self.workflow_service.get_decks_list()
            if deck.get("date", "") >= cutoff_date
        ]

        if not todays_decks:
            return False, "No decks from the selected time window found for this archetype."

        with self._loading_lock:
            self.loading_daily_average = True

        on_status("app.status.building_daily_average")

        source_filter = self.get_deck_data_source()
        method = self._average_method
        deck_count = len(todays_decks)

        def worker(rows: list[dict[str, Any]]):
            return self.workflow_service.build_daily_average_buffer(
                rows,
                source_filter=source_filter,
                method=method,
                on_progress=on_progress,
            )

        def success_handler(buffer):
            with self._loading_lock:
                self.loading_daily_average = False
            if method == "karsten":
                deck_text = self.deck_service.render_karsten_deck(buffer)
            else:
                deck_text = self.deck_service.render_average_deck(buffer, deck_count)
            on_success(deck_text)

        def error_handler(error: Exception):
            with self._loading_lock:
                self.loading_daily_average = False
            logger.error(f"Daily average error: {error}")
            on_error(error)

        self._worker.submit(
            worker,
            todays_decks,
            on_success=success_handler,
            on_error=error_handler,
        )

        return True, f"Processing {deck_count} decks"

    def get_zone_cards(self) -> dict[str, list[dict[str, Any]]]:
        return self.zone_cards
