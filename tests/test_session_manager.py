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

    def get_current_deck_text(self) -> str:
        return self._current_deck_text

    def set_current_deck_text(self, text: str) -> None:
        self._current_deck_text = text

    def get_current_deck(self) -> dict | None:
        return self._current_deck

    def set_current_deck(self, deck: dict | None) -> None:
        self._current_deck = deck


def test_session_manager_persists_and_restores(tmp_path):
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
    restore_target = {"main": [], "side": [], "out": []}

    restored = manager.restore_session_state(restore_target)
    assert restored["left_mode"] == "builder"
    assert restored["zone_cards"]["main"][0]["name"] == "Lightning Bolt"
    assert restored["zone_cards"]["main"][0]["qty"] == 4
    assert restored["window_size"] == (1280, 720)
    assert restored["screen_pos"] == (10, 20)
    assert restored["deck_text"] == "4 Lightning Bolt"
    assert restored["deck_info"] == {"name": "Burn"}
    assert repo.get_current_deck_text() == "4 Lightning Bolt"
    assert repo.get_current_deck() == {"name": "Burn"}

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


def _make_manager(tmp_path, settings: dict | None = None, repo: StubDeckRepo | None = None):
    settings_file = tmp_path / "settings.json"
    if settings is not None:
        settings_file.write_text(json.dumps(settings), encoding="utf-8")
    return DeckSelectorSessionManager(
        repo if repo is not None else StubDeckRepo(),
        settings_file=settings_file,
        config_file=tmp_path / "config.json",
        default_deck_dir=tmp_path / "decks",
    )


def test_placement_filter_migrates_legacy_values(tmp_path):
    manager = _make_manager(
        tmp_path,
        {
            "deck_placement_op": ">=",
            "deck_placement_field": "wins",
            "deck_placement_value": "3",
        },
    )
    assert manager.get_deck_placement_filter() == ("≥", "Wins", "3")

    manager = _make_manager(
        tmp_path,
        {"deck_placement_op": "<=", "deck_placement_field": "placement"},
    )
    assert manager.get_deck_placement_filter() == ("≤", "Placement", "")


def test_placement_filter_invalid_falls_back(tmp_path):
    manager = _make_manager(
        tmp_path,
        {"deck_placement_op": "??", "deck_placement_field": "bogus", "deck_placement_value": "1"},
    )
    assert manager.get_deck_placement_filter() == ("-", "Placement", "1")


def test_update_placement_filter_round_trips_and_migrates(tmp_path):
    manager = _make_manager(tmp_path)
    manager.update_deck_placement_filter(">=", "wins", "5")
    assert manager.settings["deck_placement_op"] == "≥"
    assert manager.settings["deck_placement_field"] == "Wins"
    assert manager.settings["deck_placement_value"] == "5"
    assert manager.get_deck_placement_filter() == ("≥", "Wins", "5")

    manager.update_deck_placement_filter("??", "bogus", "9")
    assert manager.settings["deck_placement_op"] == "-"
    assert manager.settings["deck_placement_field"] == "Placement"
    assert manager.settings["deck_placement_value"] == "9"


def test_save_removes_stale_saved_deck_info(tmp_path):
    repo = StubDeckRepo()
    repo.set_current_deck({"name": "Burn"})
    manager = _make_manager(tmp_path, repo=repo)
    save_kwargs = {
        "current_format": "Modern",
        "left_mode": "builder",
        "deck_data_source": "mtgo",
        "zone_cards": {"main": [], "side": [], "out": []},
    }
    manager.save(**save_kwargs)
    data = json.loads(manager.settings_file.read_text(encoding="utf-8"))
    assert data["saved_deck_info"] == {"name": "Burn"}

    repo.set_current_deck(None)
    manager.save(**save_kwargs)
    data = json.loads(manager.settings_file.read_text(encoding="utf-8"))
    assert "saved_deck_info" not in data

    # A subsequent restore must not set deck_info from stale state.
    restored = manager.restore_session_state({"main": [], "side": [], "out": []})
    assert "deck_info" not in restored


def test_restore_on_empty_settings_returns_only_left_mode(tmp_path):
    repo = StubDeckRepo()
    manager = _make_manager(tmp_path, repo=repo)
    target = {"main": [], "side": [], "out": []}
    restored = manager.restore_session_state(target)
    assert restored == {"left_mode": "research"}
    assert repo.get_current_deck_text() == ""
    assert repo.get_current_deck() is None


def test_restore_ignores_malformed_window_size_and_nonlist_zone(tmp_path):
    manager = _make_manager(
        tmp_path,
        {
            "window_size": [800, 600, 100],
            "screen_pos": [5, 5],
            "saved_zone_cards": {"main": "not-a-list", "side": [], "out": []},
        },
    )
    restored = manager.restore_session_state({"main": [], "side": [], "out": []})
    assert "window_size" not in restored
    assert restored["screen_pos"] == (5, 5)
    assert "zone_cards" not in restored


def test_corrupt_settings_json_degrades_to_defaults(tmp_path):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{not valid json", encoding="utf-8")
    manager = DeckSelectorSessionManager(
        StubDeckRepo(),
        settings_file=settings_file,
        config_file=tmp_path / "config.json",
        default_deck_dir=tmp_path / "decks",
    )
    assert manager.settings == {}
    assert manager.get_current_format() == "Modern"


def test_average_method_and_hours_validation(tmp_path):
    manager = _make_manager(tmp_path)
    assert manager.get_average_method() == "karsten"
    manager.update_average_method("arithmetic")
    assert manager.settings["average_method"] == "arithmetic"
    assert manager.get_average_method() == "arithmetic"
    manager.update_average_method("bogus")
    assert manager.settings["average_method"] == "karsten"

    assert manager.get_average_hours() == 24
    manager.update_average_hours(48)
    assert manager.settings["average_hours"] == 48
    assert manager.get_average_hours() == 48
    manager.update_average_hours(13)
    assert manager.settings["average_hours"] == 24

    manager.settings["average_hours"] = "not-a-number"
    assert manager.get_average_hours() == 24
    manager.settings["average_hours"] = "48"
    assert manager.get_average_hours() == 48


def test_event_logging_enabled_round_trips(tmp_path):
    manager = _make_manager(tmp_path)
    assert manager.get_event_logging_enabled() is False
    manager.update_event_logging_enabled(True)
    assert manager.settings["event_logging_enabled"] is True
    assert manager.get_event_logging_enabled() is True


def test_deck_view_and_pile_sort_modes(tmp_path):
    manager = _make_manager(tmp_path)
    assert manager.get_deck_view_mode("main") == "grid"
    manager.update_deck_view_mode("main", "table")
    assert manager.settings["deck_view_modes"]["main"] == "table"
    assert manager.get_deck_view_mode("main") == "table"
    manager.update_deck_view_mode("side", "bogus")
    assert manager.settings["deck_view_modes"]["side"] == "grid"

    assert manager.get_pile_sort_mode("main") == "mv"
    manager.update_pile_sort_mode("main", "color")
    assert manager.settings["deck_pile_sort_modes"]["main"] == "color"
    assert manager.get_pile_sort_mode("main") == "color"
    manager.update_pile_sort_mode("side", "bogus")
    assert manager.settings["deck_pile_sort_modes"]["side"] == "mv"


def test_event_type_player_and_date_filters(tmp_path):
    manager = _make_manager(tmp_path)
    assert manager.get_deck_event_type_filter() == "All"
    manager.update_deck_event_type_filter("League")
    assert manager.settings["deck_event_type_filter"] == "League"
    assert manager.get_deck_event_type_filter() == "League"
    manager.update_deck_event_type_filter("bogus")
    assert manager.settings["deck_event_type_filter"] == "All"

    assert manager.get_deck_player_filter() == ""
    manager.update_deck_player_filter("Alice")
    assert manager.get_deck_player_filter() == "Alice"

    assert manager.get_deck_date_filter() == ""
    manager.update_deck_date_filter("2026-06-01")
    assert manager.get_deck_date_filter() == "2026-06-01"


def test_tutorial_shown_persists_to_disk(tmp_path):
    manager = _make_manager(tmp_path)
    assert manager.is_tutorial_shown() is False
    manager.mark_tutorial_shown()
    assert manager.is_tutorial_shown() is True
    data = json.loads(manager.settings_file.read_text(encoding="utf-8"))
    assert data["tutorial_shown"] is True


def _unwritable_path(tmp_path, name: str) -> Path:
    """Return a path whose parent is a regular file, so any write raises OSError."""
    blocker = tmp_path / "blocker_file"
    blocker.write_text("not-a-directory", encoding="utf-8")
    return blocker / name


def test_ensure_deck_save_dir_falls_back_when_configured_path_unwritable(tmp_path):
    settings_file = tmp_path / "settings.json"
    config_file = tmp_path / "config.json"
    fallback_dir = tmp_path / "fallback_decks"
    manager = DeckSelectorSessionManager(
        StubDeckRepo(),
        settings_file=settings_file,
        config_file=config_file,
        default_deck_dir=fallback_dir,
    )
    # A configured save path that cannot be created (parent is a regular file).
    manager.config["deck_selector_save_path"] = str(_unwritable_path(tmp_path, "decks"))

    deck_dir = manager.ensure_deck_save_dir()

    assert deck_dir == fallback_dir
    assert deck_dir.exists()
    config_data = json.loads(config_file.read_text(encoding="utf-8"))
    assert config_data["deck_selector_save_path"] == str(fallback_dir)


def test_mark_tutorial_shown_survives_persist_failure(tmp_path):
    settings_file = _unwritable_path(tmp_path, "settings.json")
    manager = DeckSelectorSessionManager(
        StubDeckRepo(),
        settings_file=settings_file,
        config_file=tmp_path / "config.json",
        default_deck_dir=tmp_path / "decks",
    )
    # Persistence fails, but the in-memory flag is still flipped and no error escapes.
    manager.mark_tutorial_shown()
    assert manager.is_tutorial_shown() is True
    assert not settings_file.exists()


def test_save_keeps_old_settings_when_persist_fails(tmp_path):
    settings_file = _unwritable_path(tmp_path, "settings.json")
    repo = StubDeckRepo()
    repo.set_current_deck_text("4 Lightning Bolt")
    manager = DeckSelectorSessionManager(
        repo,
        settings_file=settings_file,
        config_file=tmp_path / "config.json",
        default_deck_dir=tmp_path / "decks",
    )
    previous_settings = dict(manager.settings)

    manager.save(
        current_format="Modern",
        left_mode="builder",
        deck_data_source="mtgo",
        zone_cards={"main": [], "side": [], "out": []},
    )

    # On write failure save() returns early without mutating in-memory settings.
    assert manager.settings == previous_settings
    assert not settings_file.exists()


def test_persist_config_swallows_oserror(tmp_path):
    config_file = _unwritable_path(tmp_path, "config.json")
    manager = DeckSelectorSessionManager(
        StubDeckRepo(),
        settings_file=tmp_path / "settings.json",
        config_file=config_file,
        default_deck_dir=tmp_path / "decks",
    )
    manager.config["deck_selector_save_path"] = str(tmp_path / "decks")

    # Should not raise even though the config file cannot be written.
    manager._persist_config()
    assert not config_file.exists()
