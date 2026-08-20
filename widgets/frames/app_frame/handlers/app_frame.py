"""Event handlers, menu builders, session/window persistence, and deck rendering for the main application frame."""

from __future__ import annotations

import time
import webbrowser
from typing import TYPE_CHECKING

import wx
from loguru import logger

from services.image_service.priorities import PRIORITY_SELECTED_DECK
from utils.constants import APP_FRAME_MIN_SIZE, APP_FRAME_SIZE, SPACE_SM
from utils.constants.timing import IMAGE_REFRESH_COALESCE_MS
from utils.i18n import LOCALE_LABELS
from utils.runtime_flags import is_automation_enabled
from widgets.dialogs.help_dialog import show_help
from widgets.dialogs.image_download_dialog import show_image_download_dialog
from widgets.dialogs.tutorial_dialog import show_tutorial
from widgets.frames.app_frame.handlers.deck_formatting import simple_summary_html
from widgets.frames.app_frame.handlers.session_logic import should_show_tutorial
from widgets.frames.mana_keyboard import open_mana_keyboard
from widgets.menu_bar import MenuEntry, MenuSpec, separator
from widgets.wx_layout import set_shown

if TYPE_CHECKING:
    from services.image_service import CardImageRequest
    from services.update_service import UpdateInfo
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class AppFrameHandlersMixin(_Base):
    """Menu, session, window, filter, and deck-rendering handlers for :class:`AppFrame`.

    Kept as a mixin (no ``__init__``) so :class:`AppFrame` remains the single
    source of truth for instance-state initialization.
    """

    # ------------------------------------------------------------------ Menu bar ------------------------------------------------------------
    def menu_specs(self) -> list[MenuSpec]:
        """The main window's four menus, in bar order.

        Phase 3b replaced six toolbar buttons and one unlabeled gear popup with
        this. The gear held twelve items mixing three taxonomies — bulk data
        *actions*, *navigation/help*, and *preferences* — in one flat list, which
        is why ``Help`` and ``Show Tutorial`` were undiscoverable. One menu per
        taxonomy, plus one for the six companion windows the toolbar used to open:

        ``File``      data the app loads or writes
        ``Tools``     the six companion windows
        ``Settings``  the four preference groups + the update-check toggle
        ``Help``      documentation, the tutorial, and a pending release

        ``Settings`` is a menu of its own rather than a tail on ``Tools`` because
        merging them would re-create exactly the mixed list this replaces. Phase 7
        collapses it into a single ``Preferences…`` item once the dialog exists.
        """
        return [
            MenuSpec(self._t("menu.file"), self._file_menu_entries),
            MenuSpec(self._t("menu.tools"), self._tools_menu_entries),
            MenuSpec(self._t("menu.settings"), self._settings_menu_entries),
            MenuSpec(self._t("menu.help"), self._help_menu_entries),
        ]

    def _file_menu_entries(self) -> list[MenuEntry]:
        return [
            MenuEntry(
                label=self._t("toolbar.load_collection"),
                on_activate=lambda: self.controller.refresh_collection_from_bridge(force=True),
            ),
            MenuEntry(
                label=self._t("toolbar.download_card_images"),
                on_activate=lambda: show_image_download_dialog(
                    self,
                    self.image_cache,
                    self.image_downloader,
                    self.controller.BULK_DATA_CACHE,
                    self._set_status,
                ),
            ),
            MenuEntry(
                label=self._t("toolbar.update_card_database"),
                on_activate=lambda: self.controller.force_bulk_data_update(),
            ),
            separator(),
            MenuEntry(
                label=self._t("toolbar.export_diagnostics"),
                on_activate=self._open_feedback_dialog,
            ),
            separator(),
            MenuEntry(label=self._t("menu.exit"), on_activate=lambda: self.Close()),
        ]

    def _tools_menu_entries(self) -> list[MenuEntry]:
        # The six companion windows the toolbar used to open, in the order they
        # sat in. Their tooltips become menu help strings rather than being lost.
        openers = {
            "opponent_tracker": self.open_opponent_tracker,
            "timer_alert": self.open_timer_alert,
            "match_history": self.open_match_history,
            "metagame_analysis": self.open_metagame_analysis,
            "top_cards": self.open_top_cards,
            "radar": lambda: self.open_radar(),
        }
        return [
            MenuEntry(
                label=self._t(f"toolbar.{key}"),
                help=self._t(f"toolbar.tooltip.{key}"),
                on_activate=opener,
            )
            for key, opener in openers.items()
        ]

    def _settings_menu_entries(self) -> list[MenuEntry]:
        return [
            MenuEntry(
                kind="radio",
                label=self._t("app.menu.deck_data_source"),
                options=(
                    ("both", self._t("app.choice.source.both")),
                    ("mtggoldfish", self._t("app.choice.source.mtggoldfish")),
                    ("mtgo", self._t("app.choice.source.mtgo")),
                ),
                current=self.controller.get_deck_data_source(),
                on_select=self._apply_deck_source,
            ),
            MenuEntry(
                kind="radio",
                label=self._t("app.menu.language"),
                options=tuple((locale, LOCALE_LABELS[locale]) for locale in self._language_values),
                current=self.locale or "",
                on_select=self._apply_language,
            ),
            MenuEntry(
                kind="radio",
                label=self._t("app.menu.average_method"),
                options=(
                    ("karsten", self._t("app.choice.average_method.karsten")),
                    ("arithmetic", self._t("app.choice.average_method.arithmetic")),
                ),
                current=self.controller.get_average_method(),
                on_select=self._apply_average_method,
            ),
            MenuEntry(
                kind="radio",
                label=self._t("app.menu.average_hours"),
                options=tuple(
                    (str(h), self._t(f"app.choice.average_hours.{h}"))
                    for h in (12, 24, 36, 48, 60, 72)
                ),
                current=str(self.controller.get_average_hours()),
                on_select=lambda value: self._apply_average_hours(int(value)),
            ),
            separator(),
            MenuEntry(
                kind="check",
                label=self._t("app.menu.check_for_updates"),
                checked=self.controller.get_update_check_enabled(),
                on_toggle=self._apply_update_check_enabled,
            ),
        ]

    def _help_menu_entries(self) -> list[MenuEntry]:
        entries = [
            MenuEntry(label=self._t("toolbar.help"), on_activate=self._open_help),
            MenuEntry(label=self._t("toolbar.show_tutorial"), on_activate=self._open_tutorial),
            MenuEntry(label=self._t("toolbar.comp_rules"), on_activate=self._open_rules_browser),
        ]
        # The update entry exists only while an update is pending, so the
        # status-bar note has a discoverable counterpart without the menu
        # carrying a permanently dead item.
        available_update = self.controller.get_available_update()
        if available_update is not None:
            entries.append(separator())
            entries.append(
                MenuEntry(
                    label=self._t("app.menu.get_update", version=available_update.version),
                    on_activate=self._open_release_page,
                )
            )
        return entries

    def _apply_deck_source(self, source: str) -> None:
        self.controller.set_deck_data_source(source)
        self._schedule_settings_save()

    def _apply_language(self, locale: str) -> None:
        self.locale = locale
        self.controller.set_language(locale)
        # The menus themselves re-translate for free (their entries are rebuilt
        # on every open); the bar's titles are button labels and have to be told.
        menu_bar = getattr(self, "menu_bar", None)
        if menu_bar is not None:
            menu_bar.set_menus(self.menu_specs())
        self._set_status("app.status.language_changed")
        self._schedule_settings_save()

    def _apply_average_method(self, method: str) -> None:
        self.controller.set_average_method(method)
        self._schedule_settings_save()

    def _apply_average_hours(self, hours: int) -> None:
        self.controller.set_average_hours(hours)
        self._schedule_settings_save()

    def _apply_update_check_enabled(self, enabled: bool) -> None:
        self.controller.set_update_check_enabled(enabled)
        self._schedule_settings_save()

    def _on_update_available(self, info: UpdateInfo) -> None:
        """Surface a newer release passively — a status-bar note, never a dialog.

        People open this app to research decks mid-tournament; a modal on launch
        would interrupt exactly the moment they can least afford it. The note
        sits in the right-hand status field until it is clicked (the settings
        menu carries the same action), and the app is untouched otherwise.
        """
        if not self.status_bar:
            return
        self.status_bar.SetStatusText(
            self._t("app.status.update_available", version=info.version), 1
        )
        self.status_bar.SetToolTip(self._t("app.tooltip.update_available", version=info.version))
        self.status_bar.Bind(wx.EVT_LEFT_DOWN, self._on_status_bar_click)

    def _on_status_bar_click(self, event: wx.MouseEvent) -> None:
        # Scoped to the update field: a click on the status *message* must stay
        # inert rather than launching a browser out of nowhere.
        if self.status_bar and self.status_bar.GetFieldRect(1).Contains(event.GetPosition()):
            self._open_release_page()
            return
        event.Skip()

    def _open_release_page(self) -> None:
        """Open the release page for the pending update in the default browser."""
        update = self.controller.get_available_update()
        if update is None:
            return
        try:
            webbrowser.open(update.release_url)
        except Exception as exc:  # pragma: no cover - depends on the desktop environment
            logger.warning(f"Unable to open release page {update.release_url!r}: {exc}")

    def _handle_image_downloaded(self, request: CardImageRequest) -> None:
        # The inspector update is cheap (a no-op unless the download matches
        # the card currently shown) and hover latency matters, so it stays
        # immediate. The table refreshes are coalesced: a mass download (empty
        # cache + warm-up/prefetch) completes hundreds of images per minute,
        # and repainting per image floods the UI event loop enough to make the
        # app unusable until the downloads drain.
        self.card_inspector_panel.handle_image_downloaded(request)
        self._note_deck_image_progress(request.card_name)
        self._pending_image_refresh_names.add(request.card_name)
        if self._image_refresh_timer is None:
            self._image_refresh_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._flush_image_refreshes, self._image_refresh_timer)
        if not self._image_refresh_timer.IsRunning():
            self._image_refresh_timer.StartOnce(IMAGE_REFRESH_COALESCE_MS)

    def _handle_image_download_failed(self, request: CardImageRequest, message: str) -> None:
        # Keep the perf tracker honest: a failed download still resolves the
        # name, otherwise one 404 would leave the deck timer dangling forever.
        self._note_deck_image_progress(request.card_name, failed=True)

    def _flush_image_refreshes(self, _event: wx.TimerEvent | None = None) -> None:
        names = self._pending_image_refresh_names
        self._pending_image_refresh_names = set()
        for name in names:
            self.main_table.refresh_card_image(name)
            self.side_table.refresh_card_image(name)
            if self.out_table:
                self.out_table.refresh_card_image(name)

    def _prefetch_deck_zone_images(self) -> None:
        """Queue image downloads for every card in the loaded deck's zones.

        The whole deck is "potentially visible" the moment it loads (grid view
        shows art immediately; hover can land on any row), so batch-prefetch it
        instead of waiting for per-card mouseover requests (issue #951).
        """
        names = [
            card["name"]
            for zone in ("main", "side", "out")
            for card in self.zone_cards.get(zone) or []
        ]
        if names:
            # PERF: t0 for the deck-load → all-images-local interval. The
            # previous deck's tracker (if unfinished) is superseded here.
            perf = self._deck_image_perf
            if perf and perf.get("pending"):
                logger.info(
                    "PERF | deck images superseded with {} of {} still pending",
                    len(perf["pending"]),
                    perf.get("enqueued", 0),
                )
            self._deck_image_perf = {
                "t0": time.perf_counter(),
                "total_names": len({name.lower() for name in names}),
                "pending": None,  # filled by _on_deck_prefetch_batch
                "enqueued": 0,
                "failed": 0,
            }
            self.controller.image_service.prefetch_card_images(
                "deck",
                names,
                priority=PRIORITY_SELECTED_DECK,
                on_batch=self._on_deck_prefetch_batch,
            )

    def _on_deck_prefetch_batch(self, source: str, enqueued: list[str], skipped: list[str]) -> None:
        # Fires on the prefetcher worker thread; marshal to the UI thread.
        wx.CallAfter(self._begin_deck_image_tracking, enqueued, skipped)

    def _begin_deck_image_tracking(self, enqueued: list[str], skipped: list[str]) -> None:
        perf = self._deck_image_perf
        if perf is None:
            return
        perf["enqueued"] = len(enqueued)
        perf["cached"] = len(skipped)
        if not enqueued:
            elapsed_ms = (time.perf_counter() - perf["t0"]) * 1000.0
            logger.info(
                "PERF | {:>7.1f} ms | === deck images all local ({} cards, 0 downloads needed) ===",
                elapsed_ms,
                perf["total_names"],
            )
            self._deck_image_perf = None
            return
        perf["pending"] = {name.lower() for name in enqueued}

    def _note_deck_image_progress(self, card_name: str, *, failed: bool = False) -> None:
        perf = self._deck_image_perf
        if not perf or not perf.get("pending"):
            return
        key = (card_name or "").lower()
        pending: set[str] = perf["pending"]
        if key not in pending:
            return
        pending.discard(key)
        if failed:
            perf["failed"] += 1
        if pending:
            return
        elapsed_ms = (time.perf_counter() - perf["t0"]) * 1000.0
        logger.info(
            "PERF | {:>7.1f} ms | === deck images all local "
            "({} downloaded, {} already cached, {} failed) ===",
            elapsed_ms,
            perf["enqueued"] - perf["failed"],
            perf.get("cached", 0),
            perf["failed"],
        )
        self._deck_image_perf = None

    # ------------------------------------------------------------------ Left panel helpers -------------------------------------------------
    def _show_left_panel(self, mode: str, force: bool = False) -> None:
        target = "builder" if mode == "builder" else "research"
        if self.left_stack:
            index = 1 if target == "builder" else 0
            if force or self.left_stack.GetSelection() != index:
                self.left_stack.ChangeSelection(index)
        if target == "builder":
            self.ensure_card_data_loaded()
        if force or self.left_mode != target:
            self.left_mode = target
            self._schedule_settings_save()

    def _open_full_mana_keyboard(self) -> None:
        self.mana_keyboard_window = open_mana_keyboard(
            self, self.mana_icons, self.mana_keyboard_window, self._on_mana_keyboard_closed
        )

    def _open_tutorial(self) -> None:
        show_tutorial(self, locale=self.locale)
        self.controller.session_manager.mark_tutorial_shown()

    def _open_help(self, topic: str | None = None) -> None:
        show_help(self, topic=topic)

    def _open_rules_browser(self) -> None:
        # Lazily imported so launching the rest of the app stays cheap when
        # the user never opens the browser.
        from widgets.frames.app_frame.handlers.ui_helpers import open_child_window
        from widgets.frames.rules_browser import RulesBrowserFrame

        open_child_window(
            self,
            "_rules_browser_window",
            RulesBrowserFrame,
            "Comprehensive Rules",
            self._handle_child_close,
            controller=self.controller,
            locale=self.locale,
        )

    def _restore_session_state(self) -> None:
        state = self.controller.session_manager.restore_session_state(self.controller.zone_cards)
        if should_show_tutorial(
            tutorial_shown=self.controller.session_manager.is_tutorial_shown(),
            automation_enabled=is_automation_enabled(),
        ):
            wx.CallAfter(self._open_tutorial)

        # Restore left panel mode
        self._show_left_panel(state["left_mode"], force=True)

        has_saved_deck = bool(state.get("zone_cards"))

        # Restore zone cards
        if has_saved_deck:
            if self.controller.card_repo.is_card_data_ready():
                self._render_current_deck()
            else:
                self._pending_deck_restore = True
                self._set_status("app.status.restoring_deck")
                self.ensure_card_data_loaded()

        # Restore deck text
        if (
            state.get("deck_text")
            and self.controller.card_repo.is_card_data_ready()
            and not has_saved_deck
        ):
            self._update_stats(state["deck_text"])
            self.copy_button.Enable(True)
            self.save_button.Enable(True)
            self.deck_notes_panel.load_notes_for_current()
            self._load_guide_for_current()

        # __init__ measured the structural minimum against *empty* deck tables,
        # because the session is restored one CallAfter later. Once the saved
        # deck is in, the layout wants more width than the floor that was set --
        # measured at 1381 enforced against 1417 wanted -- so the window could be
        # dragged 52px narrower than its own content fits. Re-measure now that
        # the tables hold what they will hold. CallAfter so it runs after the
        # sizers have settled from this method's own work.
        wx.CallAfter(self._apply_min_size)

    # ------------------------------------------------------------------ Window persistence ---------------------------------------------------
    def _save_window_settings(self) -> None:
        pos = self.GetPosition()
        size = self.GetSize()
        self.controller.save_settings(
            window_size=(size.width, size.height), screen_pos=(pos.x, pos.y)
        )

    def _apply_window_preferences(self) -> None:
        state = self.controller.session_manager.restore_session_state(self.controller.zone_cards)

        # Restore the collapsed/expanded state of the side panels before sizing,
        # so the recomputed minimum reflects what is actually shown.
        if state.get("left_collapsed"):
            self._set_left_collapsed(True, persist=False)
        if state.get("inspector_collapsed"):
            self._set_inspector_collapsed(True, persist=False)

        area = self._target_display_client_area()

        # On a display too small to host the preferred size, maximize to use the
        # full usable area. Also collapse the (tall) inspector by default the
        # first time we hit such a screen, so the layout fits without the card
        # image forcing the window taller than the display (the user can expand
        # it again — its toggle persists from then on).
        too_small = APP_FRAME_SIZE[0] > area.width or APP_FRAME_SIZE[1] > area.height
        if too_small:
            if "inspector_collapsed" not in state:
                self._set_inspector_collapsed(True, persist=False)
            self.Maximize(True)
            return

        size = state.get("window_size") or APP_FRAME_SIZE
        try:
            width = min(int(size[0]), area.width)
            height = min(int(size[1]), area.height)
        except (TypeError, ValueError):
            logger.debug("Ignoring invalid saved window size")
            width, height = APP_FRAME_SIZE
        self.SetSize(wx.Size(width, height))

        pos = state.get("screen_pos")
        if pos:
            try:
                x = max(area.x, min(int(pos[0]), area.x + area.width - width))
                y = max(area.y, min(int(pos[1]), area.y + area.height - height))
                self.SetPosition(wx.Point(x, y))
            except (TypeError, ValueError):
                logger.debug("Ignoring invalid saved window position")
                self.Centre(wx.BOTH)
        else:
            self.Centre(wx.BOTH)

    def _target_display_client_area(self) -> wx.Rect:
        """Usable area (excluding the taskbar) of the display hosting the frame."""
        index = wx.Display.GetFromWindow(self)
        if index == wx.NOT_FOUND:
            index = 0
        try:
            return wx.Display(index).GetClientArea()
        except (RuntimeError, AssertionError):
            return wx.Display(0).GetClientArea()

    def _apply_min_size(self) -> None:
        """Set the frame's minimum size to the larger of the hard floor and the
        current content minimum.

        Recomputed whenever a side panel is collapsed/expanded so that, e.g.,
        collapsing the tall inspector lets the window shrink below the inspector's
        natural height, while expanding it raises the floor again.
        """
        if not self.root_panel or not self.root_panel.GetSizer():
            self.SetMinSize(APP_FRAME_MIN_SIZE)
            return
        self.root_panel.Layout()
        min_size = self.root_panel.GetSizer().GetMinSize()
        # The status strip is a sibling of root_panel, not a wx.StatusBar, so
        # ClientToWindowSize no longer accounts for it — add it back by hand or the
        # floor sits one strip short and the strip is what gets squeezed.
        if self.status_bar:
            min_size = wx.Size(
                min_size.GetWidth(), min_size.GetHeight() + self.status_bar.GetSize().GetHeight()
            )
        # Same for the menu bar, which is also a sibling of root_panel. Its width
        # is not folded in: four menu titles are ~250px against a content column
        # that never drops below ~1000, so it can never be the binding term, and
        # taking a max() here would only invite the reader to think it might be.
        menu_bar = getattr(self, "menu_bar", None)
        if menu_bar:
            min_size = wx.Size(
                min_size.GetWidth(),
                min_size.GetHeight() + menu_bar.GetSize().GetHeight() + SPACE_SM,
            )
        try:
            min_size = self.ClientToWindowSize(min_size)
        except AttributeError:
            pass
        self.SetMinSize(
            wx.Size(
                max(APP_FRAME_MIN_SIZE[0], min_size.GetWidth()),
                max(APP_FRAME_MIN_SIZE[1], min_size.GetHeight()),
            )
        )

    # ------------------------------------------------------------------ Collapsible side panels ---------------------------------------------
    def toggle_left_panel(self) -> None:
        self._set_left_collapsed(not self._left_collapsed)

    def toggle_inspector(self) -> None:
        self._set_inspector_collapsed(not self._inspector_collapsed)

    def _set_left_collapsed(self, collapsed: bool, *, persist: bool = True) -> None:
        self._left_collapsed = collapsed
        if self.left_toggle_btn:
            # ▶ invites expanding (panel hidden to the left); ◀ invites collapsing.
            self.left_toggle_btn.SetLabel("▶" if collapsed else "◀")
        self._relayout_after_toggle(self.left_panel_window, not collapsed)
        if persist:
            self.controller.save_settings(left_collapsed=collapsed)

    def _set_inspector_collapsed(self, collapsed: bool, *, persist: bool = True) -> None:
        self._inspector_collapsed = collapsed
        if self.inspector_toggle_btn:
            # ◀ invites expanding (panel hidden to the right); ▶ invites collapsing.
            self.inspector_toggle_btn.SetLabel("◀" if collapsed else "▶")
        self._relayout_after_toggle(self.inspector_panel, not collapsed)
        if persist:
            self.controller.save_settings(inspector_collapsed=collapsed)

    def _relayout_after_toggle(self, panel: wx.Window | None, shown: bool) -> None:
        if self.root_panel:
            # set_shown repaints the whole frame so the toggled panel never
            # leaves ghost pixels over the toolbar (see widgets.wx_layout).
            set_shown(panel, shown, relayout_from=self.root_panel)
        self._apply_min_size()

    def _schedule_settings_save(self) -> None:
        if self._save_timer is None:
            self._save_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._flush_pending_settings, self._save_timer)
        if self._save_timer.IsRunning():
            self._save_timer.Stop()
        self._save_timer.StartOnce(600)

    def _flush_pending_settings(self, _event: wx.TimerEvent) -> None:
        self._save_window_settings()

    def _schedule_filter_debounce(self) -> None:
        if self._filter_debounce_timer is None:
            self._filter_debounce_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._flush_deck_filters, self._filter_debounce_timer)
        if self._filter_debounce_timer.IsRunning():
            self._filter_debounce_timer.Stop()
        self._filter_debounce_timer.StartOnce(250)

    def _flush_deck_filters(self, _event: wx.TimerEvent) -> None:
        self._apply_deck_filters()

    def fetch_archetypes(self, force: bool = False) -> None:
        if force:
            # An explicit reload must always refresh the deck list, even if the
            # refreshed archetype list is byte-for-byte identical. Clearing the
            # dedup signature lets _on_archetypes_loaded reload decks again.
            self._last_archetype_reload_sig = None
        self.research_panel.set_loading_state()
        self.controller.deck_repo.clear_decks_list()
        self.deck_list.Clear()
        self._clear_deck_display()
        self.daily_average_button.Disable()
        self.copy_button.Disable()
        self.save_button.Disable()

        self.controller.fetch_archetypes(
            on_success=lambda archetypes: wx.CallAfter(self._on_archetypes_loaded, archetypes),
            on_error=lambda error: wx.CallAfter(self._on_archetypes_error, error),
            on_status=lambda *a, **kw: wx.CallAfter(self._set_status, *a, **kw),
            force=force,
        )

    def _clear_deck_display(self) -> None:
        self.controller.deck_repo.set_current_deck(None)
        self.summary_text.SetPage(simple_summary_html(self._t("app.status.select_archetype")))
        self.zone_cards = {"main": [], "side": [], "out": []}
        self.main_table.set_cards([])
        self.side_table.set_cards([])
        if self.out_table:
            self.out_table.set_cards(self.zone_cards["out"])
        self.controller.deck_repo.set_current_deck_text("")
        self._update_stats("")
        self.deck_notes_panel.clear()
        self.sideboard_guide_panel.clear()
        self.card_inspector_panel.reset()
        self.card_panel.clear()

    def _render_current_deck(self) -> None:
        self.main_table.set_cards(self.zone_cards["main"])
        self.side_table.set_cards(self.zone_cards["side"])
        if self.out_table:
            self.out_table.set_cards(self.zone_cards["out"])
        self._prefetch_deck_zone_images()
        deck_text = self.controller.deck_repo.get_current_deck_text()
        if deck_text:
            self._update_stats(deck_text)
            self.copy_button.Enable(True)
            self.save_button.Enable(True)
        self.deck_notes_panel.load_notes_for_current()
        self._load_guide_for_current()
        self._pending_deck_restore = False

    def _render_pending_deck(self) -> None:
        if not self.controller.card_repo.is_card_data_ready():
            return
        if self._pending_deck_restore or self._has_deck_loaded():
            was_restore = self._pending_deck_restore
            self._render_current_deck()
            # The other half of the deferred-restore path: on a cold start the
            # card database is not ready when _restore_session_state runs, so the
            # deck lands here instead and the floor has to be re-measured here
            # too. Restore only -- a later deck load must not move the floor
            # under a window the user has already sized.
            if was_restore:
                wx.CallAfter(self._apply_min_size)

    def _populate_archetype_list(self) -> None:
        archetype_names = ["Any"] + [
            item.get("name", "Unknown") for item in self.filtered_archetypes
        ]
        self.research_panel.populate_archetypes(archetype_names)

    def _on_deck_download_success(self, content: str) -> None:
        self.present_deck_text(content)

    def _update_stats(self, deck_text: str) -> None:
        self.deck_stats_panel.update_stats(deck_text, self.zone_cards)
