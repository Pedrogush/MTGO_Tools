from __future__ import annotations

import gc
import sys
import time as time_module
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from data_isolation import redirect_bound_paths

if sys.platform != "win32":
    pytest.skip("wxPython UI tests must run on Windows", allow_module_level=True)

import repositories.scrapers.mtggoldfish as mtggoldfish
import services.image_service as card_images
import services.image_service.schemas as card_images_schemas
import utils.constants as constants
import widgets.frames.app_frame as app_frame
import widgets.frames.identify_opponent as identify_opponent
from controllers.app_controller import AppController
from repositories.card_repository import CardDataManager
from repositories.deck_repository.database import DatabaseMixin
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
    install_ui_environment(monkeypatch, tmp_path / "mtgo")


def install_ui_environment(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """Point every data path under *root* and stub the network-facing seams.

    Per test, through :func:`ui_environment`; per module, through
    :func:`shared_app_frame`, whose window outlives any one test's patches.
    """
    config = root / "config"
    cache = root / "cache"
    decks = root / "decks"
    logs = root / "logs"
    card_data = root / "data"
    image_cache = cache / "card_images"
    _ensure_dirs(config, cache, decks, logs, card_data, image_cache)

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
    # Every real data path, wherever it is bound (see tests/data_isolation.py),
    # then the explicit names above, some of which differ from the real file name.
    redirect_bound_paths(
        monkeypatch,
        {"config": config, "cache": cache, "decks": decks, "logs": logs, "data": card_data},
    )
    for attr, value in replacements.items():
        monkeypatch.setattr(constants, attr, value, raising=False)

    # The saved-decks SQLite database resolves its path from a module-level
    # import of SAVED_DECKS_DB_FILE, which the constants patch above cannot reach,
    # and Save/Load Deck now read and write it (#1034). Pin it per test.
    saved_decks_db = cache / "saved_decks.db"
    monkeypatch.setattr(DatabaseMixin, "_get_db_path", lambda _self: saved_decks_db)

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


def wait_until(
    app: wx.App,
    condition: Callable[[], bool],
    *,
    timeout: float = 15.0,
    message: str = "",
) -> None:
    """Pump the event queue until *condition* holds, or fail after *timeout*.

    The alternative -- pumping a fixed number of times -- is a guess about how
    much work a machine gets done per pass, and it is the reason
    test_match_history_filters was flaky: 40 passes was enough for the history
    to load here and not always enough on a loaded CI runner, and the test then
    failed on an assertion about labels rather than saying what it was waiting
    for. The timeout is generous because it is only ever paid by a failure.
    """
    deadline = time_module.monotonic() + timeout
    while True:
        pump_ui_events(app)
        if condition():
            return
        if time_module.monotonic() >= deadline:
            raise AssertionError(
                message or f"timed out after {timeout}s waiting for the UI to settle"
            )
        time_module.sleep(0.01)


@pytest.fixture
def deck_selector_factory(wx_app) -> AppFrame:
    def _factory() -> AppFrame:
        return build_app_frame(wx_app)

    return _factory


def build_app_frame(wx_app: wx.App) -> AppFrame:
    """A fresh AppFrame on a controller of its own, with loading made synchronous.

    ``AppController()`` directly, never ``get_deck_selector_controller()``. The
    global singleton belongs to the running application, and a fixture that
    swapped it made the two window fixtures disagree about which controller was
    current: ``build_app_frame`` used to reset the global and take the fresh
    instance, so from the first ``deck_selector_factory`` test in a module the
    module's shared window was driving a controller the singleton no longer
    named -- a different set of repositories and services than anything that
    asked for "the" controller would get. Nothing in the suite reads the
    global; ``tests/test_ui_fixture_guards.py`` keeps it that way.
    """
    # Drain wx events and force GC of the prior controller before building the
    # next one. The previous test's frame.Destroy() schedules async cleanup;
    # without pumping, those Destroy events plus queued wx.CallAfter callbacks
    # accumulate. By the last UI test, wx fails to back new windows with
    # HWNDs and Layout()/SetScrollRate() asserts inside the C++ layer.
    pump_ui_events(wx_app)
    gc.collect()
    pump_ui_events(wx_app)

    controller = AppController()
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

    fake_deck_text = "4 Mountain\n4 Island\nSideboard\n2 Dispel\n"

    def fake_download_deck_text(deck_number, on_success, on_error, on_status):  # noqa: ARG001
        on_status("Downloading deck…")
        on_success(fake_deck_text)

    controller.download_deck_text = fake_download_deck_text  # type: ignore[assignment]
    return frame


# ---------------------------------------------------------------------------
# One AppFrame per test module
# ---------------------------------------------------------------------------
#
# Building an AppFrame costs ~1.2s, and most UI tests only need *a* main window
# in a known state, not a newly constructed one. The app itself is one
# long-lived window whose state accumulates, so a window reused across a
# module's tests is, if anything, closer to real use. Tests that are *about*
# construction, startup, session restore or what a second window reads back
# keep using ``deck_selector_factory`` for a fresh one.
#
# Scope is the module, never the session: a test that leaves the window in a
# state the reset below does not cover can only disturb its own file.


def find_timers(*owners: Any) -> list[wx.Timer]:
    """Every ``wx.Timer`` reachable from *owners*, panels included.

    Only a few of them are on the frame. The builder panel debounces its search
    and its image prefetch, the card image display drives its cross-fade, and
    each of the six card views owns a marquee whose autoscroll timer lives on a
    plain helper object the view holds -- not on a window at all. So the walk is
    the window tree, plus one hop into whatever ``widgets`` object a window
    holds, which is how a timer on a non-window helper is reached.
    """
    found: list[wx.Timer] = []
    seen: set[int] = set()
    queue: list[Any] = list(owners)
    while queue:
        owner = queue.pop()
        if id(owner) in seen:
            continue
        seen.add(id(owner))
        for value in vars(owner).values() if hasattr(owner, "__dict__") else ():
            if isinstance(value, wx.Timer):
                found.append(value)
            elif (
                not isinstance(value, wx.Object)
                and hasattr(value, "__dict__")
                and (type(value).__module__ or "").startswith("widgets")
            ):
                queue.append(value)
        if isinstance(owner, wx.Window):
            queue.extend(owner.GetChildren())
    return found


def _stop_timers(*owners: Any) -> None:
    """Stop every timer :func:`find_timers` reaches.

    A one-shot timer still running when its owner is destroyed fires into freed
    memory the next time a live loop dispatches WM_TIMER -- and, between tests,
    a debounce one test started fires inside the next one, against a window
    that test has not set up yet.
    """
    for timer in find_timers(*owners):
        timer.Stop()


def _instance_overrides(obj: Any) -> dict[str, Any]:
    """Instance attributes that shadow a callable defined on the class.

    That is exactly the shape of a test double installed on an object --
    ``frame._load_decks = recording_load_decks`` -- and of the synchronous stubs
    :func:`build_app_frame` installs.
    """
    cls = type(obj)
    return {
        name: value
        for name, value in vars(obj).items()
        if callable(value) and callable(getattr(cls, name, None))
    }


class SharedAppFrame:
    """A module's AppFrame plus the state each of its tests starts from."""

    #: Plain attributes restored before every test: the load re-entrancy flags
    #: and the dedup/debounce memory of the previous test's loads, which would
    #: otherwise swallow the next test's first load of the same target.
    FRAME_STATE = (
        "loading_archetypes",
        "loading_decks",
        "loading_daily_average",
        "_last_archetype_reload_sig",
        "_last_deck_load_sig",
        "_last_deck_load_time",
    )

    #: The card tables whose view mode is part of that state.
    ZONES = ("main", "side")

    def __init__(self, frame: AppFrame, wx_app: wx.App) -> None:
        self.frame = frame
        self.wx_app = wx_app
        # Let construction settle before reading the baseline off the window.
        # ``_apply_min_size`` queues itself through ``wx.CallAfter``, so an
        # unpumped frame reports the size and floor of a window still moving --
        # and which of the two a capture here saw was a race the reset then
        # tried to restore the window to.
        pump_ui_events(wx_app)
        self.controller = frame.controller
        self._overrides = {
            "frame": _instance_overrides(frame),
            "controller": _instance_overrides(self.controller),
        }
        self._state = {name: getattr(frame, name) for name in self.FRAME_STATE}
        self._format = frame.research_panel.get_selected_format()
        combo = frame.research_panel.archetype_list
        self._archetypes = list(self.controller.archetypes)
        self._filtered_archetypes = list(self.controller.filtered_archetypes)
        self._archetype_items = list(combo.GetStrings())
        self._archetype_selection = combo.GetSelection()
        self._archetype_enabled = combo.IsEnabled()
        # The floor, and the size the window can actually be put back to.
        # Construction leaves the frame a few pixels shorter than the floor
        # ``_apply_min_size`` goes on to compute -- wx does not re-clamp a
        # window when its minimum grows under it, but it does clamp every
        # SetSize after that. Taking the recorded size as at least the floor is
        # what stops the reset chasing a height the window will never report.
        self.min_size = frame.GetMinSize()
        size = frame.GetSize()
        self.size = wx.Size(
            max(size.GetWidth(), self.min_size.GetWidth()),
            max(size.GetHeight(), self.min_size.GetHeight()),
        )
        self.view_modes = {zone: self._table(zone).view_mode for zone in self.ZONES}

    def _table(self, zone: str) -> Any:
        return getattr(self.frame, f"{zone}_table")

    def _restore_overrides(self, obj: Any, baseline: dict[str, Any]) -> None:
        for name, value in _instance_overrides(obj).items():
            if name not in baseline:
                delattr(obj, name)
            elif value is not baseline[name]:
                setattr(obj, name, baseline[name])
        for name, value in baseline.items():
            if vars(obj).get(name) is not value:
                setattr(obj, name, value)

    def reset(self) -> AppFrame:
        """Put the window back into the state a test may assume, and return it."""
        frame = self.frame
        pump_ui_events(self.wx_app)
        self._restore_overrides(frame, self._overrides["frame"])
        self._restore_overrides(self.controller, self._overrides["controller"])
        with frame._loading_lock:
            for name, value in self._state.items():
                setattr(frame, name, value)
        if frame.research_panel.get_selected_format() != self._format:
            frame.research_panel.format_choice.SetStringSelection(self._format)
        frame.current_format = self._format
        panel = frame.research_panel
        panel.reset_event_type_filter()
        panel.reset_placement_filter()
        panel.reset_player_name_filter()
        panel.reset_date_filter()
        # The deck builder's own filter set, via the Clear button's handler: a
        # format or colour left selected silently narrows the next test's search
        # (a "Legacy" left over from a format-change test filters out every card
        # in the sample database, which are all Modern-legal).
        frame.builder_panel.clear_filters()
        # The loaded deck: what "nothing is loaded yet" means to the window.
        # ``build_deck_text`` answers from the repository's deck *text* first,
        # so a deck a previous test rendered would still be there to copy/save.
        frame.deck_repo.set_current_deck(None)
        frame.deck_repo.set_current_deck_text("")
        frame.deck_repo.clear_decks_list()
        frame.zone_cards = {"main": [], "side": [], "out": []}
        self._restore_archetypes(frame)
        # The card views' mode, before the geometry: a zone left showing piles
        # is a taller widget, and the floor the window is sized against is
        # measured from what is on screen. A test that switched a zone left
        # every later test in the file measuring a different widget than the
        # one it names.
        for zone, mode in self.view_modes.items():
            self._table(zone).set_view_mode(mode, persist=False)
        self._restore_geometry(frame)
        # Last, not first: a debounce the previous test started would fire
        # inside this one -- the use-after-free the module docstring warns
        # about -- but clearing the filters above *schedules* debounces of its
        # own, so stopping them before that would leave two of them armed. Same
        # walk the module teardown uses, and for the same reason: nearly every
        # timer in this window is on a panel rather than on the frame.
        _stop_timers(frame)
        return frame

    def _restore_archetypes(self, frame: AppFrame) -> None:
        """The archetype list and what is selected in it.

        The reset above has just emptied the loaded deck, and
        ``_baseline_archetype`` falls back to the research selection when no
        deck is loaded -- so a selection left over from the previous test makes
        a window with nothing in it claim an archetype, and the Baseline tab
        measures against a pool the test never asked for. The list itself
        matters too: ``on_archetype_selected`` indexes ``filtered_archetypes``
        by the combo's row.
        """
        self.controller.archetypes = list(self._archetypes)
        self.controller.filtered_archetypes = list(self._filtered_archetypes)
        combo = frame.research_panel.archetype_list
        if list(combo.GetStrings()) != self._archetype_items:
            combo.Clear()
            for item in self._archetype_items:
                combo.Append(item)
        if combo.GetSelection() != self._archetype_selection:
            combo.SetSelection(self._archetype_selection)
        combo.Enable(self._archetype_enabled)

    def _restore_geometry(self, frame: AppFrame) -> None:
        """The window's own size.

        ``test_card_view_scroll_snap`` sizes the window down to its enforced
        minimum to measure what a card view does there, and every test in that
        file re-applies the floor itself, so the leak never showed. Any other
        file's test that reads a client size after one of those would be
        reading the previous test's window.

        The floor goes back first, and not only for its own sake: the enforced
        minimum is a lower bound on ``SetSize``, so a window left at a taller
        content's floor cannot be sized back down to the baseline until the
        floor is.
        """
        if frame.GetMinSize() != self.min_size:
            frame.SetMinSize(self.min_size)
        if frame.GetSize() != self.size:
            frame.SetSize(self.size)
            frame.Layout()


@pytest.fixture(scope="module")
def shared_app_frame(
    wx_app: wx.App, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[SharedAppFrame]:
    """One AppFrame for the whole module, under its own module-scoped data dirs.

    The window's controller, repositories and stores bind their paths when they
    are built, so they get a module tmp dir of their own rather than the first
    test's, which that test's teardown would pull out from under them. Each test
    still gets ``ui_environment``'s per-test redirect on top.
    """
    with pytest.MonkeyPatch.context() as module_patch:
        install_ui_environment(module_patch, tmp_path_factory.mktemp("mtgo-module") / "mtgo")
        frame = build_app_frame(wx_app)
        shared = SharedAppFrame(frame, wx_app)
        try:
            yield shared
        finally:
            _stop_timers(frame)
            frame.Destroy()
            pump_ui_events(wx_app)


@pytest.fixture
def shared_frame(shared_app_frame: SharedAppFrame) -> AppFrame:
    """The module's shared AppFrame, reset to the state a test may assume."""
    return shared_app_frame.reset()


def prepare_card_manager(frame: AppFrame) -> None:
    manager = CardDataManager()
    manager._cards = SAMPLE_CARDS
    manager._cards_by_name = {card["name_lower"]: card for card in SAMPLE_CARDS}
    frame.card_repo.set_card_manager(manager)
    frame.card_repo.set_card_data_loading(False)
    frame.card_repo.set_card_data_ready(True)
    frame.card_manager = manager
    frame.card_data_ready = True
