from unittest.mock import patch

import pytest
import wx

from tests.ui.conftest import prepare_card_manager, pump_ui_events
from widgets.panels.deck_builder_panel import DeckBuilderPanel


@pytest.mark.usefixtures("wx_app")
def test_deck_selector_loads_archetypes_and_mainboard_stats(
    deck_selector_factory,
):
    frame = deck_selector_factory()
    try:
        frame.fetch_archetypes()
        pump_ui_events(wx.GetApp())
        assert frame.research_panel.archetype_list.GetCount() == 3  # "Any" + 2 archetypes

        frame.research_panel.archetype_list.SetSelection(
            1
        )  # index 0 = "Any", index 1 = first archetype
        frame.on_archetype_selected()
        pump_ui_events(wx.GetApp())

        assert frame.deck_list.GetCount() == 1
        frame.deck_list.SetSelection(0)
        frame.on_deck_selected(None)
        pump_ui_events(wx.GetApp())

        assert "8 card" in frame.main_table.count_label.GetLabel()
        assert "Mainboard: 8 cards" in frame.stats_summary.GetLabel()
        assert frame.deck_action_buttons.copy_button.IsEnabled()
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_format_change_reloads_decks_with_any_selected(
    deck_selector_factory,
):
    """Switching formats while "Any" is selected must reload the decklists.

    Regression test: previously, the auto-load of "Any" decks was gated by a
    `_initial_any_load_triggered` flag that only fired once per session, so a
    format change populated the archetype list but left the deck list empty.

    Note: the factory replaces ``frame._load_decks`` with a debounce-free stub,
    so this test only exercises the ``_on_archetypes_loaded`` signature-skip
    logic (which decides whether to reload at all). The real ``_load_decks``
    debounce — including that a distinct (format, scope) target is never
    swallowed across a format change — is covered separately by
    ``test_format_change_reloads_decks_through_real_load_decks`` and
    ``test_load_decks_debounces_rapid_identical_target``.
    """
    frame = deck_selector_factory()
    try:
        load_decks_calls: list[dict[str, object]] = []
        original_load_decks = frame._load_decks

        def recording_load_decks(**kwargs):
            load_decks_calls.append(kwargs)
            return original_load_decks(**kwargs)

        frame._load_decks = recording_load_decks  # type: ignore[assignment]

        frame.fetch_archetypes()
        pump_ui_events(wx.GetApp())
        assert frame.research_panel.archetype_list.GetSelection() == 0  # "Any"
        assert load_decks_calls == [{"scope": "all"}]

        # Simulate the user picking a different format while "Any" is still selected.
        frame.research_panel.format_choice.SetStringSelection("Legacy")
        frame.on_format_changed()
        pump_ui_events(wx.GetApp())

        assert frame.current_format == "Legacy"
        # A second "all" load must fire so decklists refresh for the new format.
        assert load_decks_calls == [{"scope": "all"}, {"scope": "all"}]
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_duplicate_archetype_delivery_skips_redundant_deck_reload(
    deck_selector_factory,
):
    """Stale-while-revalidate delivers archetypes twice (cached, then a
    background-refreshed copy). The second, identical delivery must NOT trigger
    a second "Any" deck reload — that was the duplicate "Loading decks for Any"
    seen on startup.
    """
    frame = deck_selector_factory()
    try:
        load_decks_calls: list[dict[str, object]] = []
        original_load_decks = frame._load_decks

        def recording_load_decks(**kwargs):
            load_decks_calls.append(kwargs)
            return original_load_decks(**kwargs)

        frame._load_decks = recording_load_decks  # type: ignore[assignment]

        archetypes = [
            {"name": "Mono Red Aggro", "href": "mono-red-aggro"},
            {"name": "Azorius Control", "href": "azorius-control"},
        ]
        frame._on_archetypes_loaded(archetypes)  # cached delivery
        frame._on_archetypes_loaded(list(archetypes))  # background refresh (identical)
        pump_ui_events(wx.GetApp())

        assert load_decks_calls == [{"scope": "all"}]
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_load_decks_debounces_rapid_identical_target(
    deck_selector_factory,
):
    """A second _load_decks for the same target within 1s is debounced, while a
    different target fires immediately.
    """
    frame = deck_selector_factory()
    try:
        real_load_decks = type(frame)._load_decks
        controller_calls: list[dict[str, object]] = []
        original_ctrl_load = frame.controller.load_decks

        def recording_ctrl_load(**kwargs):
            controller_calls.append(kwargs)
            return original_ctrl_load(**kwargs)

        frame.controller.load_decks = recording_ctrl_load  # type: ignore[assignment]

        real_load_decks(frame, scope="all")
        real_load_decks(frame, scope="all")  # identical target, <1s → debounced
        assert len(controller_calls) == 1

        # A distinct target is never debounced.
        real_load_decks(frame, scope="archetype", archetype={"name": "X", "href": "x"})
        assert len(controller_calls) == 2
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_present_deck_text_updates_ui_without_download_io(
    deck_selector_factory,
):
    frame = deck_selector_factory()
    try:
        frame.present_deck_text("4 Mountain\n4 Island\nSideboard\n2 Dispel\n")
        pump_ui_events(wx.GetApp())

        # present_deck_text renders straight from the supplied text; it must not
        # trigger another download round-trip.
        assert frame.controller.deck_repo.get_current_deck_text().startswith("4 Mountain")
        assert "8 card" in frame.main_table.count_label.GetLabel()
        assert frame.deck_action_buttons.copy_button.IsEnabled()
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_builder_search_populates_results(
    deck_selector_factory,
):
    frame = deck_selector_factory()
    try:
        frame.card_data_dialogs_disabled = True
        prepare_card_manager(frame)
        frame._show_left_panel("builder", force=True)
        name_ctrl = frame.builder_panel.inputs["name"]
        name_ctrl.ChangeValue("Mountain")
        frame._on_builder_search()
        pump_ui_events(wx.GetApp())

        assert frame.builder_panel.results_ctrl is not None
        assert frame.builder_panel.results_ctrl.GetItemCount() >= 1
        assert "Mountain" in frame.builder_panel.results_ctrl.GetItemText(0)
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_builder_radar_zone_choices_are_localized_for_pt_br(
    deck_selector_factory,
):
    frame = deck_selector_factory()
    panel = None
    try:
        panel = DeckBuilderPanel(
            parent=frame,
            controller=frame.controller,
            mana_icons=frame.mana_icons,
            on_switch_to_research=lambda: None,
            on_ensure_card_data=lambda: None,
            open_mana_keyboard=lambda: None,
            on_search=lambda: None,
            on_clear=lambda: None,
            on_result_selected=lambda _idx: None,
            locale="pt-BR",
        )

        assert panel.radar_zone_choice.GetString(0) == "Ambos"
        assert panel.radar_zone_choice.GetString(1) == "Principal"
        assert panel.radar_zone_choice.GetString(2) == "Sideboard"
    finally:
        if panel is not None:
            panel.Destroy()
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_notes_replaced_on_deck_switch(
    deck_selector_factory,
):
    """Notes for deck A must be cleared/replaced when switching to deck B."""
    frame = deck_selector_factory()
    try:
        frame.controller.deck_notes_store.clear()
        deck_a = {"name": "deck-a", "number": "1", "href": "deck-a"}
        deck_b = {"name": "deck-b", "number": "2", "href": "deck-b"}
        frame.controller.deck_notes_store["deck-a"] = [
            {"id": "a1", "title": "Note A", "body": "Deck A note", "type": "General"}
        ]

        frame.deck_repo.set_current_deck(deck_a)
        frame.deck_notes_panel.load_notes_for_current()
        assert frame.deck_notes_panel.get_notes()[0]["body"] == "Deck A note"

        frame.deck_repo.set_current_deck(deck_b)
        frame.deck_notes_panel.load_notes_for_current()
        assert frame.deck_notes_panel.get_notes() == []
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_notes_loaded_on_session_restore(
    deck_selector_factory,
):
    """_render_current_deck() must load notes so they appear after app restart."""
    frame = deck_selector_factory()
    try:
        frame.controller.deck_notes_store.clear()
        frame.deck_repo.set_current_deck({"href": "restore-deck", "name": "Restore Deck"})
        frame.controller.deck_notes_store["restore-deck"] = [
            {"id": "r1", "title": "Restored", "body": "Session note", "type": "General"}
        ]
        # Simulate session restore with saved zone cards
        frame.zone_cards = {
            "main": [{"name": "Mountain", "qty": 4}],
            "side": [],
            "out": [],
        }
        frame._render_current_deck()
        cards = frame.deck_notes_panel.get_notes()
        assert len(cards) == 1
        assert cards[0]["body"] == "Session note"
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_toolbar_settings_apply_preferences(
    deck_selector_factory,
):
    frame = deck_selector_factory()
    try:
        frame._apply_deck_source("mtgo")
        assert frame.controller.get_deck_data_source() == "mtgo"

        frame._apply_language("pt-BR")
        assert frame.locale == "pt-BR"
        assert frame.controller.get_language() == "pt-BR"
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_notes_persist_across_frames(
    deck_selector_factory,
):
    first_frame = deck_selector_factory()
    try:
        first_frame.controller.deck_notes_store.clear()
        first_frame.deck_repo.set_current_deck({"href": "manual", "name": "Manual Deck"})
        first_frame.deck_notes_panel.set_notes(
            [{"id": "test-id", "title": "General", "body": "Important note", "type": "General"}]
        )
        first_frame.deck_notes_panel.save_current_notes()
    finally:
        first_frame.Destroy()

    second_frame = deck_selector_factory()
    try:
        second_frame.deck_repo.set_current_deck({"href": "manual", "name": "Manual Deck"})
        second_frame.deck_notes_panel.load_notes_for_current()
        cards = second_frame.deck_notes_panel.get_notes()
        assert len(cards) == 1
        assert cards[0]["body"] == "Important note"
    finally:
        second_frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_file_deck_load_uses_file_deck_key_for_notes(
    deck_selector_factory,
):
    frame = deck_selector_factory()
    try:
        frame.controller.deck_notes_store.clear()
        frame.deck_repo.set_current_deck(
            {"href": "my-deck", "name": "My Deck", "path": "C:/decks/My Deck.txt", "source": "file"}
        )
        frame.controller.deck_notes_store["my-deck"] = [
            {"id": "file-1", "title": "File", "body": "File note", "type": "General"}
        ]

        frame.deck_notes_panel.load_notes_for_current()
        assert frame.deck_notes_panel.get_notes()[0]["body"] == "File note"

        frame._on_deck_content_ready(
            "4 Lightning Bolt\n4 Mountain\nSideboard\n1 Abrade\n",
            source="file",
        )
        assert frame.deck_repo.get_current_deck_key() == "my-deck"
        assert frame.deck_notes_panel.get_notes()[0]["body"] == "File note"
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_format_change_reloads_decks_through_real_load_decks(
    deck_selector_factory,
):
    """A format change must reach the real ``_load_decks`` -> ``controller.load_decks``.

    Complements ``test_format_change_reloads_decks_with_any_selected`` (which
    stubs ``_load_decks``): here we restore the real method and assert the
    downstream ``controller.load_decks`` fires for each distinct format, proving
    the debounce does not swallow the post-format-change "all" load.
    """
    frame = deck_selector_factory()
    try:
        # Restore the real (debounced) _load_decks; the factory stubs it out.
        frame._load_decks = lambda **kwargs: type(frame)._load_decks(frame, **kwargs)

        controller_calls: list[dict[str, object]] = []
        original_ctrl_load = frame.controller.load_decks

        def recording_ctrl_load(**kwargs):
            controller_calls.append(kwargs)
            return original_ctrl_load(**kwargs)

        frame.controller.load_decks = recording_ctrl_load  # type: ignore[assignment]

        frame.fetch_archetypes()
        pump_ui_events(wx.GetApp())
        assert frame.research_panel.archetype_list.GetSelection() == 0  # "Any"
        assert [c["scope"] for c in controller_calls] == ["all"]

        frame.research_panel.format_choice.SetStringSelection("Legacy")
        frame.on_format_changed()
        pump_ui_events(wx.GetApp())

        assert frame.current_format == "Legacy"
        # The distinct (scope='all', format='Legacy') target is not debounced
        # against the prior Modern load, so a second controller load fires.
        assert [c["scope"] for c in controller_calls] == ["all", "all"]
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_on_archetypes_error_resets_loading_flag(
    deck_selector_factory,
):
    """A failed archetype fetch must clear ``loading_archetypes`` and notify."""
    frame = deck_selector_factory()
    try:
        with frame._loading_lock:
            frame.loading_archetypes = True
        with patch("wx.MessageBox") as message_box:
            frame._on_archetypes_error(RuntimeError("boom"))
        assert frame.loading_archetypes is False
        assert message_box.called
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_on_decks_error_resets_loading_flag_and_shows_failed_load(
    deck_selector_factory,
):
    """A failed deck fetch must clear ``loading_decks`` and surface the error."""
    frame = deck_selector_factory()
    try:
        with frame._loading_lock:
            frame.loading_decks = True
        with patch("wx.MessageBox") as message_box:
            frame._on_decks_error(RuntimeError("kaboom"))
        assert frame.loading_decks is False
        assert frame.deck_list.GetCount() == 1
        assert frame.deck_list.GetString(0) == frame._t("deck_results.failed_load")
        assert message_box.called
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_on_deck_download_error_disables_actions(
    deck_selector_factory,
):
    """A failed deck download must disable copy/save and notify the user."""
    frame = deck_selector_factory()
    try:
        frame.copy_button.Enable(True)
        frame.save_button.Enable(True)
        with patch("wx.MessageBox") as message_box:
            frame._on_deck_download_error(RuntimeError("nope"))
        assert not frame.copy_button.IsEnabled()
        assert not frame.save_button.IsEnabled()
        assert message_box.called
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_load_decks_archetype_scope_without_archetype_is_guarded(
    deck_selector_factory,
):
    """``_load_decks(scope='archetype', archetype=None)`` must not load decks."""
    frame = deck_selector_factory()
    try:
        controller_calls: list[dict[str, object]] = []
        frame.controller.load_decks = lambda **kwargs: controller_calls.append(  # type: ignore[assignment]
            kwargs
        )
        with patch("wx.MessageBox") as message_box:
            type(frame)._load_decks(frame, scope="archetype", archetype=None)
        assert controller_calls == []
        assert message_box.called
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_on_archetype_selected_skips_while_loading(
    deck_selector_factory,
):
    """The re-entrancy guard must block archetype selection during an in-flight load."""
    frame = deck_selector_factory()
    try:
        load_calls: list[dict[str, object]] = []
        frame._load_decks = lambda **kwargs: load_calls.append(kwargs)  # type: ignore[assignment]
        with frame._loading_lock:
            frame.loading_archetypes = True
        frame.on_archetype_selected()
        assert load_calls == []
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_on_deck_selected_skips_while_loading(
    deck_selector_factory,
):
    """The re-entrancy guard must block deck selection during an in-flight load."""
    frame = deck_selector_factory()
    try:
        download_calls: list[object] = []
        frame._download_deck_text = lambda deck: download_calls.append(deck)  # type: ignore[assignment]
        with frame._loading_lock:
            frame.loading_decks = True
        frame.on_deck_selected(None)
        assert download_calls == []
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_on_deck_content_ready_clears_current_deck_for_manual_source(
    deck_selector_factory,
):
    """Manual/automation/average pastes must reset the current deck to None.

    This is what scopes deck notes to the source's fallback ("manual") key
    rather than a previously selected research deck.
    """
    frame = deck_selector_factory()
    try:
        frame.deck_repo.set_current_deck({"href": "azorius-control", "name": "Azorius Control"})
        frame._on_deck_content_ready("4 Mountain\n4 Island\n", source="manual")
        pump_ui_events(wx.GetApp())
        assert frame.controller.deck_repo.get_current_deck() is None
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_on_copy_clicked_empty_deck_warns_without_clipboard_write(
    deck_selector_factory,
):
    """Copying with nothing loaded must warn and never touch the clipboard."""
    frame = deck_selector_factory()
    try:
        frame.zone_cards = {"main": [], "side": [], "out": []}
        with patch("wx.MessageBox") as message_box, patch("wx.TheClipboard") as clipboard:
            frame.on_copy_clicked(None)
        assert message_box.called
        assert not clipboard.Open.called
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_on_save_clicked_empty_deck_warns_without_save(
    deck_selector_factory,
):
    """Saving with nothing loaded must warn and never call save_deck."""
    frame = deck_selector_factory()
    try:
        frame.zone_cards = {"main": [], "side": [], "out": []}
        save_calls: list[object] = []
        frame.controller.save_deck = lambda **kwargs: save_calls.append(kwargs)  # type: ignore[assignment]
        with patch("wx.MessageBox") as message_box:
            frame.on_save_clicked(None)
        assert message_box.called
        assert save_calls == []
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_on_save_clicked_round_trip(
    deck_selector_factory,
):
    """A non-empty deck must be written via controller.save_deck under the entered name."""
    frame = deck_selector_factory()
    try:
        frame.zone_cards = {
            "main": [{"name": "Mountain", "qty": 4}],
            "side": [],
            "out": [],
        }
        save_calls: list[dict[str, object]] = []

        def fake_save_deck(**kwargs):
            save_calls.append(kwargs)
            return ("C:/decks/saved_deck.txt", None)

        frame.controller.save_deck = fake_save_deck  # type: ignore[assignment]

        with patch("wx.TextEntryDialog") as dialog_cls, patch("wx.MessageBox"):
            dialog = dialog_cls.return_value
            dialog.ShowModal.return_value = wx.ID_OK
            dialog.GetValue.return_value = "My Saved Deck"
            frame.on_save_clicked(None)

        assert len(save_calls) == 1
        assert save_calls[0]["deck_name"] == "My Saved Deck"
        assert save_calls[0]["deck_content"].strip()
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_on_load_deck_clicked_file_read_error_is_handled(
    deck_selector_factory,
):
    """An unreadable selected file must surface an error and not render content."""
    frame = deck_selector_factory()
    try:
        ready_calls: list[object] = []
        frame._on_deck_content_ready = lambda text, source="manual": ready_calls.append(  # type: ignore[assignment]
            (text, source)
        )

        with (
            patch("wx.FileDialog") as dialog_cls,
            patch("pathlib.Path.read_text", side_effect=OSError("denied")),
            patch("wx.MessageBox") as message_box,
        ):
            dialog = dialog_cls.return_value.__enter__.return_value
            dialog.ShowModal.return_value = wx.ID_OK
            dialog.GetPath.return_value = "C:/decks/Unreadable Deck.txt"
            frame.on_load_deck_clicked()

        assert ready_calls == []
        assert message_box.called
        # The current deck key is derived from the chosen file before the read.
        assert frame.deck_repo.get_current_deck_key() == "unreadable deck"
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_on_copy_clicked_writes_deck_to_clipboard(
    deck_selector_factory,
):
    """A non-empty deck must be copied to the clipboard as text."""
    frame = deck_selector_factory()
    try:
        frame.zone_cards = {
            "main": [{"name": "Mountain", "qty": 4}],
            "side": [{"name": "Island", "qty": 2}],
            "out": [],
        }
        with patch("wx.TheClipboard") as clipboard:
            clipboard.Open.return_value = True
            frame.on_copy_clicked(None)

        assert clipboard.Open.called
        assert clipboard.SetData.called
        assert clipboard.Close.called
        data_object = clipboard.SetData.call_args.args[0]
        copied_text = data_object.GetText()
        assert "Mountain" in copied_text
        assert "Island" in copied_text
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_on_load_deck_clicked_renders_selected_file(
    deck_selector_factory,
):
    """A readable selected file must reach _on_deck_content_ready as source='file'."""
    frame = deck_selector_factory()
    try:
        ready_calls: list[tuple[str, str]] = []
        frame._on_deck_content_ready = lambda text, source="manual": ready_calls.append(  # type: ignore[assignment]
            (text, source)
        )

        deck_text = "4 Lightning Bolt\n4 Mountain\nSideboard\n1 Abrade\n"
        with (
            patch("wx.FileDialog") as dialog_cls,
            patch("pathlib.Path.read_text", return_value=deck_text),
        ):
            dialog = dialog_cls.return_value.__enter__.return_value
            dialog.ShowModal.return_value = wx.ID_OK
            dialog.GetPath.return_value = "C:/decks/My Deck.txt"
            frame.on_load_deck_clicked()

        assert ready_calls == [(deck_text, "file")]
        assert frame.deck_repo.get_current_deck_key() == "my deck"
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_on_daily_average_clicked_skips_while_loading(
    deck_selector_factory,
):
    """The re-entrancy guard must block a daily-average build already in flight."""
    frame = deck_selector_factory()
    try:
        build_calls: list[object] = []
        frame._start_daily_average_build = lambda: build_calls.append(object())  # type: ignore[assignment]
        with frame._loading_lock:
            frame.loading_daily_average = True
        frame.on_daily_average_clicked(None)
        assert build_calls == []
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_on_daily_average_clicked_no_op_without_decks(
    deck_selector_factory,
):
    """With no decks loaded the daily-average build must not start."""
    frame = deck_selector_factory()
    try:
        build_calls: list[object] = []
        frame._start_daily_average_build = lambda: build_calls.append(object())  # type: ignore[assignment]
        frame.controller.deck_repo.set_decks_list([])
        with frame._loading_lock:
            frame.loading_daily_average = False
        frame.on_daily_average_clicked(None)
        assert build_calls == []
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_on_daily_average_clicked_builds_and_renders(
    deck_selector_factory,
):
    """The happy path stubs build_daily_average_deck, fires on_success, and renders."""
    frame = deck_selector_factory()
    try:
        frame.controller.deck_repo.set_decks_list([{"name": "Mono Red Aggro", "number": "1"}])

        def fake_build(on_success, on_error, on_status, on_progress):  # noqa: ARG001
            on_success("4 Mountain\n4 Island\n")
            return True, ""

        frame.controller.build_daily_average_deck = fake_build  # type: ignore[assignment]

        frame.on_daily_average_clicked(None)
        pump_ui_events(wx.GetApp())

        # source='average' clears the current deck and renders the built list.
        assert frame.controller.deck_repo.get_current_deck() is None
        assert "8 card" in frame.main_table.count_label.GetLabel()
        assert frame.daily_average_button.IsEnabled()
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_deck_filter_through_frame_narrows_and_empties_deck_list(
    deck_selector_factory,
):
    """A player-name filter applied via the frame must narrow, then empty, the list.

    Drives the real ``_apply_deck_filters`` row-building path: an archetype load
    populates ``_all_loaded_decks`` with one deck (player ``TestPilot``); a
    matching filter keeps it, a non-matching filter yields the disabled
    "no decks" state.
    """
    frame = deck_selector_factory()
    try:
        frame.fetch_archetypes()
        pump_ui_events(wx.GetApp())
        frame.research_panel.archetype_list.SetSelection(1)
        frame.on_archetype_selected()
        pump_ui_events(wx.GetApp())
        assert frame.deck_list.GetCount() == 1

        # A matching player filter keeps the single deck.
        frame.research_panel.set_player_name_filter("testpilot")
        frame.on_event_type_filter_changed()
        pump_ui_events(wx.GetApp())
        assert frame.deck_list.GetCount() == 1
        assert frame.deck_list.IsEnabled()

        # A non-matching filter empties the list and disables it.
        frame.research_panel.set_player_name_filter("nobody")
        frame.on_event_type_filter_changed()
        pump_ui_events(wx.GetApp())
        assert frame.deck_list.GetCount() == 1
        assert frame.deck_list.GetString(0) == frame._t("deck_results.no_decks")
        assert not frame.deck_list.IsEnabled()
    finally:
        frame.Destroy()
