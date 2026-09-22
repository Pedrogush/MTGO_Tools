"""Deck-content handlers: selection, copy/save/load, render, and daily average."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

from repositories.scrapers.mtggoldfish_visual import DeckUnavailableError
from services.deck_name import (
    NAME_FALLBACK,
    adopt_file_name,
    clean_deck_name,
    deck_file_for,
    deck_name_of,
    has_deck_name,
    set_deck_name,
)
from utils.constants import FORMAT_OPTIONS
from utils.deck import sanitize_filename
from utils.perf import perf_phase
from widgets.dialogs.save_deck_dialog import SaveDeckDialog
from widgets.frames.app_frame.handlers.deck_formatting import format_deck_name

if TYPE_CHECKING:
    from widgets.frames.app_frame import AppFrame
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


def _same_file(left: object, right: object) -> bool:
    if not left or not right:
        return False
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
        os.path.abspath(str(right))
    )


class DeckContentHandlers(_Base):
    """Deck selection, clipboard/save/load, content rendering, and daily average."""

    def on_deck_selected(self: AppFrame, _event: wx.CommandEvent | None = None) -> None:
        with self._loading_lock:
            if self.loading_decks:
                return
        idx = self.deck_list.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        deck = self.controller.deck_repo.get_decks_list()[idx]
        # PERF: mark the instant of the click so _on_deck_content_ready can
        # report the full click-to-rendered-deck wall time (download + render).
        self._deck_click_t0 = time.perf_counter()
        self.controller.deck_repo.set_current_deck(deck)
        self.deck_notes_panel.load_notes_for_current()
        self.copy_button.Disable()
        self.save_button.Disable()
        self._set_status("app.status.loading_deck", name=format_deck_name(deck))
        loading_label = self._t("deck.loading")
        self.main_table.show_loading(loading_label)
        self.side_table.show_loading(loading_label)
        self._download_deck_text(deck)
        self._schedule_settings_save()

    def on_daily_average_clicked(self: AppFrame, _event: wx.CommandEvent) -> None:
        with self._loading_lock:
            if self.loading_daily_average:
                return
        if not self.controller.deck_repo.get_decks_list():
            return
        self._start_daily_average_build()

    def on_load_deck_clicked(self: AppFrame) -> None:
        default_dir = self.controller.resolve_deck_dialog_dir()
        logger.info(f"Load Deck clicked (opening in {default_dir})")
        with wx.FileDialog(
            self,
            self._t("deck_actions.load_deck"),
            defaultDir=str(default_dir),
            wildcard=self._t("deck_save.file_filter"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                logger.info("Load Deck cancelled")
                return
            file_path = dlg.GetPath()

        file_ref = Path(file_path)
        deck_key = sanitize_filename(file_ref.stem, fallback="manual").lower()
        deck_record: dict[str, Any] = {
            "href": deck_key,
            "name": file_ref.stem,
            "path": str(file_ref),
            "source": "file",
        }
        # A deck already on disk is named by the file it came from, which is the
        # same stem its history was keyed by before names existed -- so decks
        # saved by an older build keep the history they have, with no migration.
        adopt_file_name(deck_record, file_ref)
        self.controller.deck_repo.set_current_deck(deck_record)
        logger.info(f"Load Deck selected: {file_path} (deck_key={deck_key})")

        try:
            deck_text = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            logger.error(f"Failed to read deck file '{file_path}': {exc}")
            wx.MessageBox(f"Failed to read deck file:\n{exc}", "Load Deck", wx.OK | wx.ICON_ERROR)
            return

        # The format and archetype chosen when this file was saved (#1034) live in
        # the saved-decks database, keyed by the file's path.
        saved = self.controller.find_saved_deck(file_ref, deck_text)
        for field in ("format", "archetype"):
            if saved and saved.get(field):
                deck_record[field] = saved[field]

        self._on_deck_content_ready(deck_text, source="file")
        # The file may have been edited outside the app since it was last saved;
        # its content is the only thing that can say so.
        self._check_external_edit(file_ref, deck_text)
        # The graph is keyed by deck, and the deck just changed. Nothing binds a
        # page-changed event on the deck tabs, so a tab that is not repainted
        # here keeps showing the *previous* deck's history until something else
        # moves HEAD -- which reads as "this deck has no versions".
        self.refresh_deck_history()
        if deck_record.get("archetype"):
            self._set_status(
                "app.status.deck_loaded_with_archetype",
                name=file_ref.stem,
                archetype=deck_record["archetype"],
                format=deck_record.get("format") or self.current_format,
            )

    def on_copy_clicked(self: AppFrame, _event: wx.CommandEvent) -> None:
        deck_content = self.controller.build_deck_text(self.zone_cards).strip()
        if not deck_content:
            wx.MessageBox("No deck to copy.", "Copy Deck", wx.OK | wx.ICON_INFORMATION)
            return
        if wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(deck_content))
            finally:
                wx.TheClipboard.Close()
            self._set_status("app.status.deck_copied")
        else:  # pragma: no cover
            wx.MessageBox("Could not access clipboard.", "Copy Deck", wx.OK | wx.ICON_WARNING)

    def on_save_clicked(self: AppFrame, _event: wx.CommandEvent | None = None) -> None:
        """Save Deck: ask for name, format and archetype once, then write.

        A named deck saves with no dialog at all. The details are collected on
        the first save only, because the name they include decides the file,
        and re-deciding the file per save is exactly what used to split one
        deck's version history across two repos.
        """
        deck_content = self.controller.build_deck_text(self.zone_cards).strip()
        if not deck_content:
            wx.MessageBox("Load a deck first.", "Save Deck", wx.OK | wx.ICON_INFORMATION)
            return
        current_deck = self.controller.deck_repo.get_current_deck()

        if has_deck_name(current_deck):
            format_name = str((current_deck or {}).get("format") or self.current_format)
            archetype = str((current_deck or {}).get("archetype") or "") or None
        else:
            details = self._ask_save_details(deck_content, current_deck)
            if details is None:
                return
            name, format_name, archetype = details
            if current_deck is None:
                # A deck built from scratch gets a record so its name has
                # somewhere to live. Deliberately no ``name``/``href``: those
                # hold the *source's* label, and ``save_deck`` falls back to
                # ``name`` for the archetype, which would file this deck under
                # its own title as an archetype nobody chose.
                current_deck = {"source": "manual"}
                self.controller.deck_repo.set_current_deck(current_deck)
            set_deck_name(current_deck, name)
            self.refresh_deck_name_displays()

        file_path = deck_file_for(current_deck, self.controller.resolve_deck_dialog_dir())
        if file_path is None:  # pragma: no cover - guarded by has_deck_name above
            return

        try:
            saved_path, deck_id = self.controller.save_deck(
                deck_name=file_path.stem,
                deck_content=deck_content,
                format_name=format_name,
                deck=current_deck,
                file_path=file_path,
                archetype=archetype,
            )
        except OSError as exc:  # pragma: no cover
            wx.MessageBox(f"Failed to write deck file:\n{exc}", "Save Deck", wx.OK | wx.ICON_ERROR)
            return

        # The in-memory record is re-pointed at the saved file by
        # ``AppController.save_deck``, which every save path goes through.

        # A save is now a single click with no dialog, so it reports in the
        # status bar rather than with a modal the user has to dismiss every
        # time. The path is in the log for anyone who needs it.
        logger.info(f"Deck saved to {saved_path} (database ID: {deck_id})")
        self._set_status("app.status.deck_saved")
        self.refresh_deck_name_displays()
        # The save already committed a version (DeckWorkflowService.save_deck);
        # this only brings the graph into step with it.
        self.refresh_deck_history()

    def _ask_save_details(
        self: AppFrame, deck_content: str, current_deck: dict[str, Any] | None
    ) -> tuple[str, str, str | None] | None:
        """Collect name, format and archetype for a deck being named.

        Returns ``None`` when the user cancels. The name is pre-filled with the
        descriptive label the deck already reads as in the research list, which
        is what the Save As default used to offer.
        """
        details = SaveDeckDialog(
            self,
            formats=FORMAT_OPTIONS,
            initial_format=self._initial_save_format(deck_content, current_deck),
            initial_archetype=self._initial_save_archetype(current_deck),
            initial_name=self._suggested_deck_name(current_deck),
            load_archetypes=self.controller.load_archetype_names,
            t=self._t,
        )
        try:
            if details.ShowModal() != wx.ID_OK:
                logger.info("Save Deck cancelled (details)")
                return None
            name = details.deck_name()
            if not name:  # pragma: no cover - OK is disabled without one
                return None
            return (
                name,
                details.selected_format() or self.current_format,
                (details.selected_archetype() or None),
            )
        finally:
            details.Destroy()

    @staticmethod
    def _suggested_deck_name(current_deck: dict[str, Any] | None) -> str:
        """What the name field opens on for a deck that has never been named."""
        if not current_deck:
            return ""
        return clean_deck_name(format_deck_name(current_deck).replace(" | ", "_"))

    def _default_save_file_name(self: AppFrame, current_deck: dict[str, Any] | None) -> str:
        """The stem a Save As opens on for a file that is *about* this deck.

        Save Deck no longer asks -- the deck's name decides its file. Save
        Collection Diff still does, because a diff is not the deck, so it needs
        the answer the old default gave: the chosen name once there is one, and
        the descriptive label the deck reads as in the research list before that.
        """
        return (
            deck_name_of(current_deck) or self._suggested_deck_name(current_deck) or NAME_FALLBACK
        )

    def on_save_diff_clicked(self: AppFrame, _event: wx.CommandEvent | None = None) -> None:
        """Save Collection Diff: the deck minus what you already own (#1044).

        No format/archetype dialog: the result is a shopping list, not a deck to
        register, so it goes straight to Save As with the deck's own file name
        plus a suffix.
        """
        title = self._t("deck_diff.title")
        deck_content = self.controller.build_deck_text(self.zone_cards).strip()
        if not deck_content:
            wx.MessageBox(self._t("deck_diff.no_deck"), title, wx.OK | wx.ICON_INFORMATION)
            return

        collection = self.controller.collection_service
        if not collection.get_inventory():
            # Without a collection every card reads as missing, which would
            # silently hand back the deck itself. Say so instead.
            wx.MessageBox(self._t("deck_diff.no_collection"), title, wx.OK | wx.ICON_INFORMATION)
            return

        diff = collection.build_collection_diff(deck_content)
        if diff.is_empty:
            wx.MessageBox(self._t("deck_diff.nothing_missing"), title, wx.OK | wx.ICON_INFORMATION)
            return

        current_deck = self.controller.deck_repo.get_current_deck()
        stem = f"{self._default_save_file_name(current_deck)}_{self._t('deck_diff.file_suffix')}"
        default_dir = self.controller.resolve_deck_dialog_dir()
        logger.info(f"Save Collection Diff: opening Save As in {default_dir}")
        with wx.FileDialog(
            self,
            title,
            defaultDir=str(default_dir),
            defaultFile=f"{stem}.txt",
            wildcard=self._t("deck_save.file_filter"),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                logger.info("Save Collection Diff cancelled (file)")
                return
            file_path = Path(dlg.GetPath())
        if not file_path.suffix:
            file_path = file_path.with_suffix(".txt")

        try:
            # The deck repository's writer, not the full save_deck path: a diff
            # is not a deck and has no business in the saved-decks database.
            saved_path = self.controller.deck_repo.write_deck_file(file_path, diff.text)
        except OSError as exc:  # pragma: no cover - filesystem failure
            wx.MessageBox(
                self._t("deck_diff.write_failed", error=exc), title, wx.OK | wx.ICON_ERROR
            )
            return

        wx.MessageBox(
            self._t(
                "deck_diff.saved",
                path=saved_path,
                missing=diff.missing_total,
                required=diff.required_total,
            ),
            title,
            wx.OK | wx.ICON_INFORMATION,
        )
        self._set_status("app.status.deck_diff_saved", count=diff.missing_total)

    def _initial_save_format(
        self: AppFrame, deck_text: str, current_deck: dict[str, Any] | None
    ) -> str:
        """The format the save dialog opens on.

        What is *known* beats what is guessed: a file saved with a format keeps
        it, and a deck picked from the research list belongs to the format that
        list was for. Anything else -- a builder list, an average, a pasted or
        unrecorded file -- is detected from its cards, falling back to the
        research panel's format when detection cannot decide.
        """
        deck = current_deck or {}
        if deck.get("format"):
            return str(deck["format"])
        if deck.get("source") in {"mtggoldfish", "mtgo"} or deck.get("number"):
            return self.current_format
        try:
            detected = self.controller.detect_deck_format(deck_text)
        except Exception:  # noqa: BLE001 - a guess must never block a save
            logger.exception("Format detection failed; using the current format")
            detected = ""
        return detected or self.current_format

    def _initial_save_archetype(self: AppFrame, current_deck: dict[str, Any] | None) -> str:
        """The archetype the save dialog preselects, or ``""``.

        A loaded file carries the archetype it was saved with. A research deck
        carries its archetype's *slug* in ``name``; that is resolved against the
        archetype list to the display name the dropdown shows, and dropped when
        it does not resolve rather than offered raw.
        """
        deck = current_deck or {}
        if deck.get("archetype"):
            return str(deck["archetype"])
        if deck.get("source") == "file":
            return ""
        key = str(deck.get("name") or "").strip()
        if not key:
            return ""
        for entry in self.controller.archetypes:
            if key in (entry.get("href"), entry.get("name")):
                return str(entry.get("name") or "")
        return ""

    def _on_deck_download_error(self: AppFrame, error: Exception) -> None:
        self.copy_button.Disable()
        self.save_button.Disable()
        if isinstance(error, DeckUnavailableError):
            # The archetype listing still offers decks MTGGoldfish has removed.
            # Nothing failed on our side, so say what is true and say it calmly
            # rather than raising an error box about parsing.
            self._set_status("app.status.deck_unavailable")
            wx.MessageBox(
                self._t("app.deck_unavailable.body"),
                self._t("app.deck_unavailable.title"),
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        self._set_status("app.status.deck_download_error", error=error)
        wx.MessageBox(f"Failed to download deck:\n{error}", "Deck Download", wx.OK | wx.ICON_ERROR)

    def _normalize_deck_printings(self: AppFrame, deck_text: str) -> str:
        """Normalise a decklist's printing pointers on entry (issue #792, part 4).

        Runs :func:`format_decklist_on_load` so a list is stored at the most
        restrictive printing format that fits every card. Requires the printing
        index (``ImageService.bulk_data_by_name``); when it has not loaded yet we
        leave the text untouched. As a safety net we only adopt the normalised
        text when it preserves every card — ``format_decklist_on_load`` drops
        names it cannot resolve, and a stale/partial index must never silently
        delete a card from a freshly loaded deck.
        """
        index = getattr(self.controller.image_service, "bulk_data_by_name", None)
        if not index or not deck_text.strip():
            return deck_text
        try:
            normalized = self.controller.deck_service.format_decklist_on_load(deck_text, index)
        except Exception:
            logger.exception("format_decklist_on_load failed; keeping deck text as-is")
            return deck_text
        before = self.controller.deck_service.analyze_deck(deck_text)["total_cards"]
        after = self.controller.deck_service.analyze_deck(normalized)["total_cards"]
        if after < before:
            logger.warning(
                "Printing normalisation would drop cards ({} -> {}); keeping original text",
                before,
                after,
            )
            return deck_text
        return normalized

    def _capture_printing_selections(self: AppFrame, deck_text: str) -> None:
        """Refresh the runtime per-card printing map from ``deck_text`` (#792).

        Records which cards' printing changed versus the previous deck so the
        board art can be force-refreshed for just those — the views cache art by
        name and would otherwise keep showing the old printing.
        """
        index = getattr(self.controller.image_service, "bulk_data_by_name", None)
        new_map: dict[str, dict] = {}
        if index and deck_text.strip():
            try:
                new_map = self.controller.deck_service.extract_printing_selections(deck_text, index)
            except Exception:
                logger.exception("extract_printing_selections failed; clearing selection map")
                new_map = {}
        old_map = self._printing_selections
        self._changed_printing_names = {
            name for name in set(old_map) | set(new_map) if old_map.get(name) != new_map.get(name)
        }
        self._printing_selections = new_map

    def _apply_changed_printing_art(self: AppFrame) -> None:
        """Force-refresh board art for cards whose printing changed on load (#792)."""
        names = self._changed_printing_names
        self._changed_printing_names = set()
        for name in names:
            self._refresh_board_card_art(name)

    def _on_deck_content_ready(self: AppFrame, deck_text: str, source: str = "manual") -> None:
        if source in {"manual", "automation", "average"}:
            self.controller.deck_repo.set_current_deck(None)
        logger.info(
            "Deck content ready: source={} current_deck={} deck_key={}",
            source,
            self.controller.deck_repo.get_current_deck(),
            self.controller.deck_repo.get_current_deck_key(),
        )
        render_t0 = time.perf_counter()
        # Capture per-card printing choices from the *original* text (issue #792)
        # before normalisation, which forces a uniform precision and can strip
        # individual pointers. The runtime map is what drives board art, so it
        # outlives that downgrade.
        self._capture_printing_selections(deck_text)
        deck_text = self._normalize_deck_printings(deck_text)
        self.controller.deck_repo.set_current_deck_text(deck_text)
        with perf_phase("analyze_deck + zone sort"):
            stats = self.controller.deck_service.analyze_deck(deck_text)
            self.zone_cards["main"] = sorted(
                [{"name": name, "qty": qty} for name, qty in stats["mainboard_cards"]],
                key=lambda card: card["name"].lower(),
            )
            self.zone_cards["side"] = sorted(
                [{"name": name, "qty": qty} for name, qty in stats["sideboard_cards"]],
                key=lambda card: card["name"].lower(),
            )
        # The name belongs to the deck that just arrived, so both of its views
        # move with it -- including back to the placeholder for a scraped list,
        # which has no name until the user gives it one.
        self.refresh_deck_name_displays()
        with perf_phase("load outboard"):
            self.zone_cards["out"] = self._load_outboard_for_current()
        with perf_phase("main_table.set_cards"):
            self.main_table.set_cards(self.zone_cards["main"])
        # Batch-prefetch every zone's images right away (runs on a background
        # thread) so art streams in while the tables render (issue #951).
        self._prefetch_deck_zone_images()
        # Defer the secondary zones to the next event-loop turn so the mainboard
        # — the zone the user is looking at — paints first. They fill in a frame
        # later, which removes their cost from the click-to-visible interval.
        wx.CallAfter(self._render_secondary_zones)
        # Re-render art for any card whose printing changed (runs after the zones
        # are populated, including the deferred secondary ones) (issue #792).
        if self._changed_printing_names:
            wx.CallAfter(self._apply_changed_printing_art)
        with perf_phase("update_stats"):
            self._update_stats(deck_text)
        self.copy_button.Enable(True)
        self.save_button.Enable(True)
        logger.info("Triggering deck notes reload for source={}", source)
        with perf_phase("load_notes_for_current"):
            self.deck_notes_panel.load_notes_for_current()
        with perf_phase("load_guide_for_current"):
            self._load_guide_for_current()
        self._set_status("app.status.deck_ready", source=source)
        self._schedule_settings_save()

        # PERF: headline numbers. "render" is the synchronous UI-thread block
        # that stalls the app (the ~600ms gap in the logs); "click-to-ready"
        # adds the async download leg when this load came from a deck click.
        render_ms = (time.perf_counter() - render_t0) * 1000.0
        click_t0 = getattr(self, "_deck_click_t0", None)
        if source == "mtggoldfish" and click_t0 is not None:
            total_ms = (time.perf_counter() - click_t0) * 1000.0
            self._deck_click_t0 = None
            logger.info(
                "PERF | {:>7.1f} ms | === deck render block (sync, UI thread) ===", render_ms
            )
            logger.info(
                "PERF | {:>7.1f} ms | === click-to-ready TOTAL (download + render) ===", total_ms
            )
        else:
            logger.info(
                "PERF | {:>7.1f} ms | === deck render block (sync, UI thread), source={} ===",
                render_ms,
                source,
            )

    def _render_secondary_zones(self: AppFrame) -> None:
        """Render the sideboard/outboard zones, deferred off the click path.

        Reads the current ``zone_cards`` at fire time, so if a newer deck loaded
        between scheduling and firing it simply paints the latest data (the new
        load scheduled its own deferral); a redundant repaint is harmless.
        """
        with perf_phase("side_table.set_cards (deferred)"):
            self.side_table.set_cards(self.zone_cards["side"])
        if self.out_table:
            with perf_phase("out_table.set_cards (deferred)"):
                self.out_table.set_cards(self.zone_cards["out"])

    def _on_daily_average_success(self: AppFrame, deck_text: str) -> None:
        self.daily_average_button.Enable()
        self._on_deck_content_ready(deck_text, source="average")

    def _on_daily_average_error(self: AppFrame, error: Exception) -> None:
        logger.error(f"Daily average error: {error}")
        self.daily_average_button.Enable()
        wx.MessageBox(
            f"Failed to build daily average:\n{error}", "Daily Average", wx.OK | wx.ICON_ERROR
        )
        self._set_status("app.status.daily_average_error", error=error)

    def _start_daily_average_build(self: AppFrame) -> None:
        self.daily_average_button.Disable()

        can_proceed, message = self.controller.build_daily_average_deck(
            on_success=lambda deck_text: wx.CallAfter(self._on_daily_average_success, deck_text),
            on_error=lambda error: wx.CallAfter(self._on_daily_average_error, error),
            on_status=lambda *a, **kw: wx.CallAfter(self._set_status, *a, **kw),
            on_progress=lambda current, total: wx.CallAfter(
                self._set_status, "app.status.building_average", current=current, total=total
            ),
        )

        if not can_proceed:
            self.daily_average_button.Enable()
            wx.MessageBox(message, "Daily Average", wx.OK | wx.ICON_INFORMATION)
            return

    def _download_deck_text(self: AppFrame, deck: dict[str, Any]) -> None:
        deck_number = deck.get("number")
        if not deck_number:
            wx.MessageBox("Deck identifier missing.", "Deck Error", wx.OK | wx.ICON_ERROR)
            return

        # Update UI state immediately
        self.copy_button.Disable()
        self.save_button.Disable()

        self.controller.download_deck_text(
            deck_number=deck_number,
            on_success=lambda content: wx.CallAfter(self.present_deck_text, content),
            on_error=lambda error: wx.CallAfter(self._on_deck_download_error, error),
            on_status=lambda *a, **kw: wx.CallAfter(self._set_status, *a, **kw),
        )

    def present_deck_text(self: AppFrame, content: str) -> None:
        self._on_deck_content_ready(content, source="mtggoldfish")
