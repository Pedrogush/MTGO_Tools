from __future__ import annotations

import sys
import time as time_module
from pathlib import Path
from typing import Any

import pytest

if sys.platform != "win32":
    pytest.skip("wxPython UI tests must run on Windows", allow_module_level=True)

import navigators.mtggoldfish as mtggoldfish
import utils.card_images as card_images
import utils.constants as constants
import widgets.app_frame as app_frame
import widgets.identify_opponent as identify_opponent
from controllers.app_controller import (
    get_deck_selector_controller,
    reset_deck_selector_controller,
)
from utils.card_data import CardDataManager
from utils.constants import METAGAME_CACHE_TTL_SECONDS
from widgets.app_frame import AppFrame

wx = pytest.importorskip("wx")

if hasattr(wx, "App") and hasattr(wx.App, "IsDisplayAvailable"):
    if not wx.App.IsDisplayAvailable():
        pytest.skip(
            "wxPython UI tests require an available display (headless session detected)",
            allow_module_level=True,
        )


SAMPLE_CARDS = [
    {
        "name": "Mountain",
        "name_lower": "mountain",
        "mana_value": 0,
        "color_identity": ["R"],
        "type_line": "Basic Land — Mountain",
        "mana_cost": "",
        "oracle_text": "({T}: Add {R}.)",
        "legalities": {"modern": "Legal"},
    },
    {
        "name": "Island",
        "name_lower": "island",
        "mana_value": 0,
        "color_identity": ["U"],
        "type_line": "Basic Land — Island",
        "mana_cost": "",
        "oracle_text": "({T}: Add {U}.)",
        "legalities": {"modern": "Legal"},
    },
]


def _ensure_dirs(*dirs: Path) -> None:
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="session", name="wx_app")
def fixture_wx_app() -> wx.App:
    """Create a shared wx App for all UI tests."""
    if wx is None:
        pytest.skip("wxPython is required for UI tests", allow_module_level=True)
    try:
        app = wx.App(False)
    except (SystemError, SystemExit, RuntimeError) as exc:  # wx raises SystemExit when headless
        pytest.skip(
            f"wxPython cannot initialize a GUI in this environment: {exc}",
            allow_module_level=True,
        )
    except Exception as exc:  # pragma: no cover - fallback for other wx headless errors
        pytest.skip(
            f"wxPython cannot initialize a GUI in this environment: {exc}",
            allow_module_level=True,
        )
    yield app
    app.Destroy()


@pytest.fixture(autouse=True)
def ui_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate filesystem paths and make background workers deterministic."""
    root = tmp_path / "mtgo"
    config = root / "config"
    cache = root / "cache"
    decks = root / "decks"
    image_cache = cache / "card_images"
    _ensure_dirs(config, cache, decks, image_cache)

    replacements = {
        "CONFIG_DIR": config,
        "CACHE_DIR": cache,
        "DECKS_DIR": decks,
        "CONFIG_FILE": config / "config.json",
        "DECK_SELECTOR_SETTINGS_FILE": config / "deck_selector_settings.json",
        "DECK_MONITOR_CONFIG_FILE": config / "deck_monitor_config.json",
        "DECK_MONITOR_CACHE_FILE": cache / "deck_monitor_cache.json",
        "ARCHETYPE_CACHE_FILE": cache / "archetype_cache.json",
        "ARCHETYPE_LIST_CACHE_FILE": cache / "archetype_list.json",
        "MTGO_ARTICLES_CACHE_FILE": cache / "mtgo_articles.json",
        "MTGO_DECK_CACHE_FILE": cache / "mtgo_decks.json",
        "DECK_TEXT_CACHE_FILE": cache / "deck_text_cache.json",
        "ARCHETYPE_DECKS_CACHE_FILE": cache / "archetype_decks_cache.json",
        "DECK_CACHE_FILE": cache / "deck_cache.json",
        "CURR_DECK_FILE": decks / "curr_deck.txt",
    }
    for attr, value in replacements.items():
        monkeypatch.setattr(constants, attr, value, raising=False)

    monkeypatch.setattr(card_images, "IMAGE_CACHE_DIR", image_cache, raising=False)
    monkeypatch.setattr(card_images, "IMAGE_DB_PATH", image_cache / "images.db", raising=False)
    monkeypatch.setattr(
        card_images, "BULK_DATA_CACHE", image_cache / "bulk_data.json", raising=False
    )
    monkeypatch.setattr(
        card_images, "PRINTING_INDEX_CACHE", image_cache / "printings_v2.json", raising=False
    )

    def fake_ensure_latest(self: CardDataManager, force: bool = False) -> None:
        self._cards = SAMPLE_CARDS
        self._cards_by_name = {card["name_lower"]: card for card in SAMPLE_CARDS}

    def fake_get_card(self: CardDataManager, name: str) -> dict[str, object] | None:
        lookup = self._cards_by_name or {}
        return lookup.get(name.lower())

    def fake_search_cards(
        self: CardDataManager, query: str = "", **kwargs
    ) -> list[dict[str, object]]:
        needle = (query or "").strip().lower()
        cards = self._cards or []
        return [card for card in cards if needle in card.get("name_lower", "")]

    monkeypatch.setattr(CardDataManager, "ensure_latest", fake_ensure_latest, raising=False)
    monkeypatch.setattr(CardDataManager, "get_card", fake_get_card, raising=False)
    monkeypatch.setattr(CardDataManager, "search_cards", fake_search_cards, raising=False)

    monkeypatch.setattr(
        app_frame,
        "MANA_RENDER_LOG",
        cache / "mana_render.log",
        raising=False,
    )

    monkeypatch.setattr(
        identify_opponent,
        "LEGACY_DECK_MONITOR_CONFIG",
        config / "deck_monitor_config.json",
        raising=False,
    )
    monkeypatch.setattr(
        identify_opponent,
        "LEGACY_DECK_MONITOR_CACHE",
        cache / "deck_monitor_cache.json",
        raising=False,
    )
    monkeypatch.setattr(
        identify_opponent,
        "LEGACY_DECK_MONITOR_CACHE_CONFIG",
        config / "deck_monitor_cache.json",
        raising=False,
    )

    for attr, value in {
        "LEGACY_ARCHETYPE_CACHE_FILE": cache / "archetype_cache.json",
        "LEGACY_DECK_CACHE_FILE": cache / "deck_cache.json",
        "LEGACY_ARCHETYPE_CACHE_CONFIG_FILE": config / "archetype_cache.json",
        "LEGACY_DECK_CACHE_CONFIG_FILE": config / "deck_cache.json",
        "LEGACY_CURR_DECK_CACHE_FILE": cache / "curr_deck.txt",
        "LEGACY_CURR_DECK_ROOT_FILE": decks / "curr_deck.txt",
    }.items():
        monkeypatch.setattr(mtggoldfish, attr, value, raising=False)

    def fake_download(number: str) -> None:
        (decks / "curr_deck.txt").write_text(
            "4 Mountain\n4 Island\nSideboard\n2 Dispel\n", encoding="utf-8"
        )

    archetype_list = [
        {"name": "Mono Red Aggro", "href": "mono-red-aggro"},
        {"name": "Azorius Control", "href": "azorius-control"},
    ]

    def fake_archetypes(
        fmt: str, cache_ttl: int = METAGAME_CACHE_TTL_SECONDS, allow_stale: bool = True
    ):
        return archetype_list

    def fake_archetype_decks(archetype: str):
        return [
            {
                "name": archetype,
                "number": "1",
                "player": "TestPilot",
                "event": "Test Event",
                "result": "2-1",
                "date": "2024-10-01",
            },
        ]

    monkeypatch.setattr(mtggoldfish, "get_archetypes", fake_archetypes, raising=False)
    monkeypatch.setattr(mtggoldfish, "get_archetype_decks", fake_archetype_decks, raising=False)
    monkeypatch.setattr(app_frame, "get_archetypes", fake_archetypes, raising=False)
    monkeypatch.setattr(app_frame, "get_archetype_decks", fake_archetype_decks, raising=False)
    monkeypatch.setattr(mtggoldfish, "download_deck", fake_download, raising=False)
    monkeypatch.setattr(app_frame, "download_deck", fake_download, raising=False)

    payload_data: dict[str, list[dict[str, Any]]] = {}
    for card in SAMPLE_CARDS:
        key = card["name_lower"]
        payload_data.setdefault(key, []).append(
            {
                "id": f"{key}-id",
                "set": "TEST",
                "set_name": "Test Set",
                "collector_number": "1",
                "released_at": "2024-01-01",
            }
        )

    fake_printing_index_payload: dict[str, Any] = {
        "version": 1,
        "bulk_mtime": time_module.time(),
        "unique_names": len(payload_data),
        "total_printings": sum(len(entries) for entries in payload_data.values()),
        "data": payload_data,
    }

    monkeypatch.setattr(
        card_images,
        "ensure_printing_index_cache",
        lambda force=False: fake_printing_index_payload,
        raising=False,
    )

    yield


def pump_ui_events(app: wx.App, *, max_passes: int = 25) -> None:
    """Process pending wx events until the queue drains or a safety cap is reached."""
    for _ in range(max_passes):
        processed = False
        pending = getattr(app, "Pending", None)
        if pending:
            while pending():
                app.Dispatch()
                processed = True
        else:
            loop_pending = getattr(app, "ProcessPendingEvents", None)
            if loop_pending:
                while loop_pending():
                    time_module.sleep(0)
                    processed = True
            else:
                # Fall back to the older Pending/Dispatch loop if available
                pending_func = getattr(wx, "Pending", None)
                if pending_func:
                    while pending_func():
                        app.Dispatch()
                        processed = True
                else:
                    app.Yield()
                    processed = True
        time_module.sleep(0)
        if not processed:
            break


@pytest.fixture
def deck_selector_factory(wx_app) -> AppFrame:
    def _factory() -> AppFrame:
        reset_deck_selector_controller()
        controller = get_deck_selector_controller()
        frame = controller.frame
        # Expose controller-backed repos/services for legacy tests
        frame.card_repo = controller.card_repo
        frame.deck_repo = controller.deck_repo
        frame.metagame_repo = controller.metagame_repo
        frame.deck_action_buttons = getattr(frame, "deck_action_buttons", None)

        # Prevent the first-run tutorial dialog from hanging tests.
        # Introduced in PR #301 (commit 273ae4d): _restore_session_state queues
        # wx.CallAfter(self._open_tutorial) when is_tutorial_shown() returns False.
        # In a fresh temp-dir environment there is no saved config, so
        # is_tutorial_shown() always returns False. When pump_ui_events() processes
        # the queued callback it runs show_tutorial() → dlg.ShowModal(), which blocks
        # indefinitely waiting for user input and hangs the entire test session.
        # Marking the tutorial shown here updates the in-memory settings dict so that
        # _restore_session_state (which fires later via wx.CallAfter) skips the dialog.
        controller.session_manager.mark_tutorial_shown()

        # Make archetype/deck loading synchronous for tests
        local_archetypes = [
            {"name": "Mono Red Aggro", "href": "mono-red-aggro"},
            {"name": "Azorius Control", "href": "azorius-control"},
        ]

        def fake_archetype_decks(archetype: str):
            return [
                {
                    "name": archetype,
                    "number": "1",
                    "player": "TestPilot",
                    "event": "Test Event",
                    "result": "2-1",
                    "date": "2024-10-01",
                },
            ]

        def fetch_archetypes_sync(force: bool = False) -> None:  # noqa: ARG001
            frame._on_archetypes_loaded(local_archetypes)

        def load_decks_sync(archetype: dict[str, Any]) -> None:
            decks = fake_archetype_decks(archetype.get("href", ""))
            frame._on_decks_loaded(archetype.get("name", "Unknown"), decks)

        frame.fetch_archetypes = fetch_archetypes_sync  # type: ignore[assignment]
        frame._load_decks_for_archetype = load_decks_sync  # type: ignore[assignment]
        controller.fetch_archetypes = lambda **kwargs: kwargs["on_success"](local_archetypes)  # type: ignore[assignment]
        controller.load_decks_for_archetype = lambda archetype, on_success, **_: on_success(
            archetype.get("name", "Unknown"), fake_archetype_decks(archetype.get("href", ""))
        )  # type: ignore[assignment]
        controller.check_and_download_bulk_data = lambda *_, **__: None  # type: ignore[assignment]
        controller.run_initial_loads = lambda *_, **__: None  # type: ignore[assignment]

        fake_deck_text = "4 Mountain\n4 Island\nSideboard\n2 Dispel\n"

        def fake_download_and_display_deck(deck, on_success, on_error, on_status):
            on_status("Downloading deck…")
            on_success(fake_deck_text)

        controller.download_and_display_deck = fake_download_and_display_deck  # type: ignore[assignment]
        return frame

    return _factory


def prepare_card_manager(frame: AppFrame) -> None:
    manager = CardDataManager()
    manager._cards = SAMPLE_CARDS
    manager._cards_by_name = {card["name_lower"]: card for card in SAMPLE_CARDS}
    frame.card_repo.set_card_manager(manager)
    frame.card_repo.set_card_data_loading(False)
    frame.card_repo.set_card_data_ready(True)
    frame.card_manager = manager
    frame.card_data_ready = True
