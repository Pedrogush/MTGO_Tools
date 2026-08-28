from __future__ import annotations

import sys
import time as time_module
from pathlib import Path
from typing import Any

import pytest
import requests

if sys.platform != "win32":
    pytest.skip("wxPython UI tests must run on Windows", allow_module_level=True)

from network_guard import NetworkWatch, install_network_tripwire

import repositories.metagame_repository as metagame_repository
import repositories.scrapers.mtggoldfish as mtggoldfish
import services.image_service as card_images
import services.image_service.schemas as card_images_schemas
import utils.constants as constants
import widgets.frames.app_frame as app_frame
import widgets.frames.identify_opponent as identify_opponent
from controllers.app_controller import (
    get_deck_selector_controller,
    reset_deck_selector_controller,
)
from repositories.card_repository import CardDataManager
from services.image_service.scryfall_session import ScryfallSession
from utils.constants import METAGAME_CACHE_TTL_SECONDS
from widgets.frames.app_frame import AppFrame

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


SAMPLE_ARCHETYPES = [
    {"name": "Mono Red Aggro", "href": "mono-red-aggro"},
    {"name": "Azorius Control", "href": "azorius-control"},
]

SAMPLE_DECK_TEXT = "4 Mountain\n4 Island\nSideboard\n2 Dispel\n"


def fake_archetypes(
    fmt: str,
    cache_ttl: int = METAGAME_CACHE_TTL_SECONDS,
    allow_stale: bool = True,
):  # noqa: ARG001
    return SAMPLE_ARCHETYPES


def fake_archetype_decks(archetype: str) -> list[dict[str, Any]]:
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


def fake_fetch_deck_text(deck_num: str, source_filter: str | None = None) -> str:  # noqa: ARG001
    return SAMPLE_DECK_TEXT


@pytest.fixture(scope="session", autouse=True, name="network_attempts")
def fixture_network_attempts() -> list[str]:
    """Take the whole UI session offline, and record anything that tries anyway.

    Session-scoped on purpose. The archetype refresh, the deck-text prefetch and
    the image pipeline all do their work on daemon threads that routinely outlive
    the test that started them. A per-test patch is unwound while those threads
    are still running, so they land on the *real* scraper in the gap between
    tests — which is how real Scryfall ``.jpg`` files ended up in a developer's
    ``cache/card_images/`` during a ``pytest tests/ui`` run. Holding both the
    fakes and the tripwire for the whole session closes that gap.

    Three layers, outermost first:

    1. The MTGGoldfish scraper entry points are faked on ``mtggoldfish``, on
       ``widgets.frames.app_frame`` **and** on ``repositories.metagame_repository``.
       The last one is the seam this package documents for exactly this purpose:
       it re-exports the scraper functions into its own namespace at import time
       and its mixins look them up there (``_pkg.get_archetypes(...)``), so
       rebinding only the scraper module leaves those copies pointing at the real
       thing and the UI suite scrapes for real.
    2. Scryfall traffic is short-circuited at
       :class:`~services.image_service.scryfall_session.ScryfallSession` — the
       adapter this app owns and routes *all* Scryfall API and CDN calls through
       (``BulkImageDownloader.session``, shared with the batch resolver and the
       bulk-metadata fetcher). Faking our own adapter rather than the transport
       under it is what ``tests/README.md`` §2 asks for, and it lets the image
       pipeline run its real offline-fallback branches.
    3. Under both, the transport tripwire: nothing in this directory can reach
       the wire at any point, and anything that tries is recorded for
       :func:`fixture_blocked_network` to fail on.
    """
    with pytest.MonkeyPatch.context() as session_patch:
        attempts = install_network_tripwire(session_patch)

        # Spelled out one module at a time rather than looped: the guard in
        # tests/test_ui_network_fakes.py reads these names straight out of the
        # source, and a loop variable would hide them from it.
        session_patch.setattr(mtggoldfish, "get_archetypes", fake_archetypes, raising=False)
        session_patch.setattr(
            mtggoldfish, "get_archetype_decks", fake_archetype_decks, raising=False
        )
        session_patch.setattr(mtggoldfish, "fetch_deck_text", fake_fetch_deck_text, raising=False)
        session_patch.setattr(app_frame, "get_archetypes", fake_archetypes, raising=False)
        session_patch.setattr(app_frame, "get_archetype_decks", fake_archetype_decks, raising=False)
        session_patch.setattr(metagame_repository, "get_archetypes", fake_archetypes, raising=False)
        session_patch.setattr(
            metagame_repository, "get_archetype_decks", fake_archetype_decks, raising=False
        )
        session_patch.setattr(
            metagame_repository, "fetch_deck_text", fake_fetch_deck_text, raising=False
        )
        # The remote-snapshot fetch is the resolver's other network branch and is
        # env-gated; pin it off so a developer with REMOTE_SNAPSHOTS_ENABLED
        # exported doesn't silently put the UI suite back on the wire.
        session_patch.setattr(metagame_repository, "REMOTE_SNAPSHOTS_ENABLED", False, raising=False)

        def offline(self, method, url, *args, **kwargs):  # noqa: ANN001, ARG001
            raise requests.ConnectionError(f"Scryfall is offline in tests: {method} {url}")

        session_patch.setattr(ScryfallSession, "request", offline, raising=False)
        yield attempts


@pytest.fixture(autouse=True, name="blocked_network")
def fixture_blocked_network(network_attempts: list[str]) -> NetworkWatch:
    """Fail any UI test that reached for the real network.

    ``tests/README.md`` §2 allows exactly one category of test double — outbound
    network and scraping — so a UI test must never make a real request. Checking
    for downloaded files afterwards is both late and lossy; this asserts on the
    transport-boundary record instead.

    Declared before :func:`ui_environment` so it is torn down after it and sees
    every call the test *and its fixtures* attempted. Tests may also take it as
    an argument to assert mid-test.
    """
    watch = NetworkWatch(network_attempts)
    yield watch
    assert not watch.attempts, "UI test made real outbound network calls:\n  " + "\n  ".join(
        watch.attempts
    )


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
        "DECK_TEXT_CACHE_FILE": cache / "deck_text_cache.json",
        "ARCHETYPE_DECKS_CACHE_FILE": cache / "archetype_decks_cache.json",
        "DECK_CACHE_FILE": cache / "deck_cache.json",
        "CURR_DECK_FILE": decks / "curr_deck.txt",
    }
    for attr, value in replacements.items():
        monkeypatch.setattr(constants, attr, value, raising=False)

    monkeypatch.setattr(card_images_schemas, "IMAGE_CACHE_DIR", image_cache, raising=False)
    monkeypatch.setattr(
        card_images_schemas, "IMAGE_DB_PATH", image_cache / "images.db", raising=False
    )
    monkeypatch.setattr(
        card_images_schemas, "BULK_DATA_CACHE", image_cache / "bulk_data.json", raising=False
    )
    monkeypatch.setattr(
        card_images_schemas,
        "PRINTING_INDEX_CACHE",
        image_cache / "printings_v3.json",
        raising=False,
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

    def fake_download(number: str, source_filter: str | None = None) -> None:  # noqa: ARG001
        (decks / "curr_deck.txt").write_text(SAMPLE_DECK_TEXT, encoding="utf-8")

    # The scraper *reads* are faked for the whole session by
    # ``fixture_network_attempts`` — background threads outlive the test that
    # starts them, so a per-test patch leaves a window on the real network.
    # ``download_deck`` needs this test's temp ``decks`` dir, so it stays here.
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
    """Drain the wx event queue AND the idle loop.

    wx.Window.Destroy() is lazy: it enqueues the window on the app's
    pending-delete list, which is only drained during idle processing
    (wxAppBase::OnIdle -> DeletePendingObjects). Dispatching queued events
    alone never runs OnIdle, so frame.Destroy() doesn't actually free the
    Win32 HWNDs. Across ~10 AppFrames (~1200 HWNDs each) that exhausts the
    Windows per-process USER-handle ceiling (~10k) and subsequent
    ::CreateWindowEx calls return NULL — which surfaces as wxWindow::
    GetLayoutDirection "invalid window" asserts during Layout().

    wx.SafeYield processes pending events and runs OnIdle; calling it in a
    loop until the queue is quiet drains both queued events and pending
    deletes.
    """
    for _ in range(max_passes):
        # wx.WakeUpIdle ensures the idle loop actually fires even when the
        # message queue is otherwise quiet (so DeletePendingObjects runs).
        wx.WakeUpIdle()
        # app.Yield processes pending events AND runs idle on wxMSW, which
        # is what invokes wxAppBase::DeletePendingObjects.
        try:
            app.Yield()
        except Exception:
            # Re-entrancy: fall back to the safer variant.
            wx.SafeYield(None, onlyIfNeeded=False)
        # Explicitly push an idle cycle to top-level windows so pending
        # deletes are definitely processed. SendIdleEvents is what wx's own
        # event loop calls during its idle phase.
        for win in wx.GetTopLevelWindows():
            if win:
                evt = wx.IdleEvent()
                win.ProcessEvent(evt)
        if hasattr(app, "HasPendingEvents") and not app.HasPendingEvents():
            break
        time_module.sleep(0)


@pytest.fixture
def deck_selector_factory(wx_app) -> AppFrame:
    def _factory() -> AppFrame:
        # Drain wx events and force GC of the prior controller before resetting.
        # The previous test's frame.Destroy() schedules async cleanup; without
        # pumping, those Destroy events plus queued wx.CallAfter callbacks
        # accumulate. By the last UI test, wx fails to back new windows with
        # HWNDs and Layout()/SetScrollRate() asserts inside the C++ layer.
        import gc

        pump_ui_events(wx_app)
        gc.collect()
        pump_ui_events(wx_app)

        reset_deck_selector_controller()
        controller = get_deck_selector_controller()
        controller.attach_frame(AppFrame(controller=controller))
        frame = controller.frame
        # Expose controller-backed repos/services for legacy tests
        frame.card_repo = controller.card_repo
        frame.deck_repo = controller.deck_repo
        frame.metagame_repo = controller.metagame_repo
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
        local_archetypes = SAMPLE_ARCHETYPES

        def fetch_archetypes_sync(force: bool = False) -> None:  # noqa: ARG001
            frame._on_archetypes_loaded(local_archetypes)

        def load_decks_sync(
            *,
            scope: str,
            archetype: dict[str, Any] | None = None,
        ) -> None:
            if scope == "all":
                frame._on_decks_loaded("Any", [])
                return
            assert archetype is not None
            decks = fake_archetype_decks(archetype.get("href", ""))
            frame._on_decks_loaded(archetype.get("name", "Unknown"), decks)

        frame.fetch_archetypes = fetch_archetypes_sync  # type: ignore[assignment]
        frame._load_decks = load_decks_sync  # type: ignore[assignment]
        controller.fetch_archetypes = lambda **kwargs: kwargs["on_success"](local_archetypes)  # type: ignore[assignment]
        controller.load_decks = lambda scope, on_success, archetype=None, **_: on_success(
            "Any" if scope == "all" else archetype.get("name", "Unknown"),
            [] if scope == "all" else fake_archetype_decks(archetype.get("href", "")),
        )  # type: ignore[assignment]
        controller.check_and_download_bulk_data = lambda *_, **__: None  # type: ignore[assignment]
        controller.run_initial_loads = lambda *_, **__: None  # type: ignore[assignment]

        fake_deck_text = SAMPLE_DECK_TEXT

        def fake_download_deck_text(deck_number, on_success, on_error, on_status):  # noqa: ARG001
            on_status("Downloading deck…")
            on_success(fake_deck_text)

        controller.download_deck_text = fake_download_deck_text  # type: ignore[assignment]
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
