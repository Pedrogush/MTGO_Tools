from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_session_manager_class() -> type:
    module_path = Path(__file__).resolve().parents[1] / "controllers" / "session_manager.py"
    spec = importlib.util.spec_from_file_location("session_manager_for_tests", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load session_manager module for tests")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.DeckSelectorSessionManager


DeckSelectorSessionManager = _load_session_manager_class()


class StubDeckRepo:
    def __init__(self) -> None:
        self._current_deck_text = ""
        self._current_deck: dict | None = None
        self.set_current_deck_text_calls: list[str] = []
        self.set_current_deck_calls: list[dict | None] = []

    def get_current_deck_text(self) -> str:
        return self._current_deck_text

    def set_current_deck_text(self, text: str) -> None:
        self._current_deck_text = text
        self.set_current_deck_text_calls.append(text)

    def get_current_deck(self) -> dict | None:
        return self._current_deck

    def set_current_deck(self, deck: dict | None) -> None:
        self._current_deck = deck
        self.set_current_deck_calls.append(deck)


def test_session_manager_persists_and_loads_snapshots(tmp_path):
    settings_file = tmp_path / "settings.json"
    config_file = tmp_path / "config.json"
    default_dir = tmp_path / "decks"
    repo = StubDeckRepo()
    repo.set_current_deck_text("4 Lightning Bolt")
    repo.set_current_deck({"name": "Burn"})
    zone_cards = {"main": [{"name": "Lightning Bolt", "qty": 4}], "side": [], "out": []}

    manager = DeckSelectorSessionManager(
        repo,
        settings_file=settings_file,
        config_file=config_file,
        default_deck_dir=default_dir,
    )
    manager.save(
        current_format="Modern",
        left_mode="builder",
        deck_data_source="mtgo",
        zone_cards=zone_cards,
        window_size=(1280, 720),
        screen_pos=(10, 20),
    )

    repo.set_current_deck_text("")
    repo.set_current_deck(None)
    window_preferences = manager.load_window_preferences()
    restored = manager.load_workspace_snapshot()
    assert restored["left_mode"] == "builder"
    assert restored["zone_cards"]["main"][0]["name"] == "Lightning Bolt"
    assert restored["zone_cards"]["main"][0]["qty"] == 4
    assert restored["deck_text"] == "4 Lightning Bolt"
    assert restored["deck_info"] == {"name": "Burn"}
    assert window_preferences["window_size"] == (1280, 720)
    assert window_preferences["screen_pos"] == (10, 20)
    assert repo.get_current_deck_text() == ""
    assert repo.get_current_deck() is None

    data = json.loads(settings_file.read_text(encoding="utf-8"))
    assert data["saved_deck_text"] == "4 Lightning Bolt"
    assert data["deck_data_source"] == "mtgo"
    assert data["language"] == "en-US"


def test_session_manager_validates_defaults_and_config(tmp_path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "format": "Legacy??",
                "left_mode": "invalid",
                "deck_data_source": "bad",
                "language": "invalid",
            }
        ),
        encoding="utf-8",
    )
    config_file = tmp_path / "config.json"
    default_dir = tmp_path / "fallback"
    repo = StubDeckRepo()

    manager = DeckSelectorSessionManager(
        repo,
        settings_file=settings_file,
        config_file=config_file,
        default_deck_dir=default_dir,
    )

    assert manager.get_current_format() == "Modern"
    assert manager.get_left_mode() == "research"
    assert manager.get_deck_data_source() == "both"
    assert manager.get_language() == "en-US"

    manager.update_deck_data_source("mtgo")
    assert manager.settings["deck_data_source"] == "mtgo"
    manager.update_language("pt-BR")
    assert manager.settings["language"] == "pt-BR"
    manager.update_language("es-ES")
    assert manager.settings["language"] == "en-US"

    deck_dir = manager.ensure_deck_save_dir()
    assert deck_dir.exists()

    config_data = json.loads(config_file.read_text(encoding="utf-8"))
    assert config_data["deck_selector_save_path"] == str(deck_dir)


def test_startup_restore_applies_saved_deck_state_once(tmp_path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "left_mode": "builder",
                "saved_deck_text": "4 Lightning Bolt",
                "saved_deck_info": {"name": "Burn"},
                "saved_zone_cards": {
                    "main": [{"name": "Lightning Bolt", "qty": 4}],
                    "side": [],
                    "out": [],
                },
                "window_size": [1280, 720],
                "screen_pos": [10, 20],
            }
        ),
        encoding="utf-8",
    )
    repo = StubDeckRepo()
    manager = DeckSelectorSessionManager(
        repo,
        settings_file=settings_file,
        config_file=tmp_path / "config.json",
        default_deck_dir=tmp_path / "decks",
    )
    zone_cards = {"main": [], "side": [], "out": []}

    assert manager.load_window_preferences() == {
        "window_size": (1280, 720),
        "screen_pos": (10, 20),
    }
    assert zone_cards == {"main": [], "side": [], "out": []}
    assert repo.set_current_deck_text_calls == []
    assert repo.set_current_deck_calls == []

    snapshot = manager.load_workspace_snapshot()
    if "zone_cards" in snapshot:
        zone_cards = snapshot["zone_cards"]
    if snapshot.get("deck_text"):
        repo.set_current_deck_text(snapshot["deck_text"])
    if isinstance(snapshot.get("deck_info"), dict):
        repo.set_current_deck(snapshot["deck_info"])

    assert zone_cards["main"] == [{"name": "Lightning Bolt", "qty": 4}]
    assert repo.set_current_deck_text_calls == ["4 Lightning Bolt"]
    assert repo.set_current_deck_calls == [{"name": "Burn"}]
