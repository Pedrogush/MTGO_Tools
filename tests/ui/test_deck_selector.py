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
def test_present_deck_text_updates_ui_without_download_io(
    deck_selector_factory,
):
    frame = deck_selector_factory()
    try:
        download_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        frame.controller.download_deck_text = lambda *args, **kwargs: download_calls.append(
            (args, kwargs)
        )  # type: ignore[assignment]

        frame.present_deck_text("4 Mountain\n4 Island\nSideboard\n2 Dispel\n")
        pump_ui_events(wx.GetApp())

        assert download_calls == []
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
