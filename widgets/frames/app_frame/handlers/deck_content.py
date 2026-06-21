"""Deck-content handlers: selection, copy/save/load, render, and daily average."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

from utils.deck import sanitize_filename
from utils.perf import perf_phase
from widgets.frames.app_frame.handlers.deck_formatting import format_deck_name

if TYPE_CHECKING:
    from widgets.frames.app_frame import AppFrame
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


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
        save_dir = self.controller.deck_save_dir
        default_dir = str(save_dir) if save_dir.exists() else str(Path.home())
        logger.info("Load Deck button clicked")
        with wx.FileDialog(
            self,
            "Load Deck",
            defaultDir=default_dir,
            wildcard="Text files (*.txt)|*.txt|All files (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                logger.info("Load Deck cancelled")
                return
            file_path = dlg.GetPath()

        file_ref = Path(file_path)
        deck_key = sanitize_filename(file_ref.stem, fallback="manual").lower()
        self.controller.deck_repo.set_current_deck(
            {
                "href": deck_key,
                "name": file_ref.stem,
                "path": str(file_ref),
                "source": "file",
            }
        )
        logger.info(f"Load Deck selected: {file_path} (deck_key={deck_key})")

        try:
            deck_text = Path(file_path).read_text(encoding="utf-8")
        except OSError as exc:
            logger.error(f"Failed to read deck file '{file_path}': {exc}")
            wx.MessageBox(f"Failed to read deck file:\n{exc}", "Load Deck", wx.OK | wx.ICON_ERROR)
            return

        self._on_deck_content_ready(deck_text, source="file")

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

    def on_save_clicked(self: AppFrame, _event: wx.CommandEvent) -> None:
        deck_content = self.controller.build_deck_text(self.zone_cards).strip()
        if not deck_content:
            wx.MessageBox("Load a deck first.", "Save Deck", wx.OK | wx.ICON_INFORMATION)
            return
        default_name = "saved_deck"
        current_deck = self.controller.deck_repo.get_current_deck()
        if current_deck:
            default_name = format_deck_name(current_deck).replace(" | ", "_")
        dlg = wx.TextEntryDialog(self, "Deck name:", "Save Deck", default_name)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        deck_name = dlg.GetValue().strip() or default_name
        dlg.Destroy()

        try:
            file_path, deck_id = self.controller.save_deck(
                deck_name=deck_name,
                deck_content=deck_content,
                format_name=self.current_format,
                deck=current_deck,
            )
        except OSError as exc:  # pragma: no cover
            wx.MessageBox(f"Failed to write deck file:\n{exc}", "Save Deck", wx.OK | wx.ICON_ERROR)
            return

        message = f"Deck saved to {file_path}"
        if deck_id:
            message += f"\nDatabase ID: {deck_id}"
        wx.MessageBox(message, "Deck Saved", wx.OK | wx.ICON_INFORMATION)
        self._set_status("app.status.deck_saved")

    def _on_deck_download_error(self: AppFrame, error: Exception) -> None:
        self.copy_button.Disable()
        self.save_button.Disable()
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
        with perf_phase("load outboard"):
            self.zone_cards["out"] = self._load_outboard_for_current()
        with perf_phase("main_table.set_cards"):
            self.main_table.set_cards(self.zone_cards["main"])
        # Defer the secondary zones to the next event-loop turn so the mainboard
        # — the zone the user is looking at — paints first. They fill in a frame
        # later, which removes their cost from the click-to-visible interval.
        wx.CallAfter(self._render_secondary_zones)
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
