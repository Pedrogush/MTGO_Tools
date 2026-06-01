"""Tests for opponent tracker radar integration.

These exercise the real production code paths:

* :class:`RadarMixin` worker orchestration in
  ``widgets/frames/identify_opponent/handlers/radar.py`` (archetype guards,
  dedup, in-progress guard, error/cancel handling, thread lifecycle).
* :class:`CompactRadarHandlersMixin` public setters and list populators in
  ``widgets/panels/compact_radar_panel/handlers.py`` (clear/loading/error
  side effects and the actual card-line formatting incl. ``max(1, round(...))``
  clamping).
* :func:`find_archetype_by_name` / :func:`normalize_archetype_name` in
  ``services/archetype_resolver.py`` (exact, forward- and reverse-containment
  partial matches, the no-match ``None`` path, and the repo-error path).

``wx`` is not importable in the WSL dev environment, so a permissive stub
module is injected before the handler modules are imported by file path. The
stub's ``CallAfter`` runs synchronously so the marshalled UI calls can be
asserted directly.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
import types
from pathlib import Path
from typing import Any


# --------------------------------------------------------------------------- #
# wx stub + module loading                                                    #
# --------------------------------------------------------------------------- #
class _WxStub(types.ModuleType):
    """A permissive ``wx`` stand-in fabricating attributes on demand.

    ``CallAfter`` is overridden to run synchronously so that the UI calls the
    worker marshals via ``wx.CallAfter`` can be observed in the test thread.
    """

    def __getattr__(self, name: str) -> Any:  # noqa: D401 - simple stub
        value: Any = type(name, (), {})
        setattr(self, name, value)
        return value

    @staticmethod
    def CallAfter(func: Any, *args: Any, **kwargs: Any) -> Any:  # noqa: N802
        return func(*args, **kwargs)


def _install_wx_stub() -> types.ModuleType:
    """Install a ``wx`` stub only when the real module is unavailable."""
    try:
        import wx as real_wx  # noqa: F401

        return sys.modules["wx"]
    except Exception:
        pass
    stub = _WxStub("wx")
    sys.modules["wx"] = stub
    return stub


def _load_module(name: str, *parts: str) -> types.ModuleType:
    """Import a module directly by file path, bypassing package side effects."""
    path = Path(__file__).resolve().parent.parent.joinpath(*parts)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# wx must be stubbed before importing anything that transitively imports it
# (services.radar_service pulls in utils.constants.keyboard, which imports wx).
_install_wx_stub()

from services.radar_service import CardFrequency, RadarData  # noqa: E402

RadarMixin = _load_module(
    "_radar_handler_under_test",
    "widgets",
    "frames",
    "identify_opponent",
    "handlers",
    "radar.py",
).RadarMixin
CompactRadarHandlersMixin = _load_module(
    "_compact_radar_handlers_under_test",
    "widgets",
    "panels",
    "compact_radar_panel",
    "handlers.py",
).CompactRadarHandlersMixin


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #
def _card(name: str, avg_copies: float, inclusion_rate: float = 100.0) -> CardFrequency:
    return CardFrequency(
        card_name=name,
        appearances=10,
        total_copies=int(avg_copies * 10),
        max_copies=4,
        avg_copies=avg_copies,
        inclusion_rate=inclusion_rate,
        expected_copies=avg_copies,
        copy_distribution={},
    )


def _radar(mainboard=None, sideboard=None, total: int = 10) -> RadarData:
    return RadarData(
        archetype_name="UR Murktide",
        format_name="Modern",
        mainboard_cards=list(mainboard or []),
        sideboard_cards=list(sideboard or []),
        total_decks_analyzed=total,
        decks_failed=0,
    )


class _FakePanel:
    """Records the radar-panel setter/clear calls the worker marshals."""

    def __init__(self) -> None:
        self.set_error_calls: list[str] = []
        self.set_loading_calls: list[str] = []
        self.display_radar_calls: list[RadarData] = []
        self.clear_calls = 0

    def set_error(self, message: str) -> None:
        self.set_error_calls.append(message)

    def set_loading(self, message: str) -> None:
        self.set_loading_calls.append(message)

    def display_radar(self, radar: RadarData) -> None:
        self.display_radar_calls.append(radar)

    def clear(self) -> None:
        self.clear_calls += 1


class _FakeController:
    def __init__(self, resolved: dict[str, Any] | None) -> None:
        self._resolved = resolved
        self.resolve_calls: list[tuple] = []

    def find_archetype_by_name(self, archetype_name, format_name, repo):
        self.resolve_calls.append((archetype_name, format_name, repo))
        return self._resolved


class _FakeHost(RadarMixin):
    """Concrete :class:`RadarMixin` host with the collaborators it touches."""

    def __init__(self, last_seen_decks, resolved):
        self.last_seen_decks = last_seen_decks
        self._last_radar_archetype = ""
        self._radar_worker_thread = None
        self._radar_cancel_requested = False
        self.current_radar = None
        self._last_guide_archetype = "stale"
        self.radar_panel = _FakePanel()
        self.sideboard_panel = _FakePanel()
        self.controller = _FakeController(resolved)
        self.metagame_service = types.SimpleNamespace(metagame_repo=object())
        self.radar_service = types.SimpleNamespace(calculate_radar=None)


def _join_worker(host: _FakeHost) -> None:
    """Wait for the (already started) worker thread to finish, if any."""
    thread = host._radar_worker_thread
    if isinstance(thread, threading.Thread):
        thread.join(timeout=5)


# --------------------------------------------------------------------------- #
# RadarMixin._trigger_radar_load                                              #
# --------------------------------------------------------------------------- #
class TestTriggerRadarLoad:
    def test_no_decks_is_noop(self):
        host = _FakeHost({}, resolved={"name": "UR Murktide"})
        host._trigger_radar_load()
        assert host.controller.resolve_calls == []
        assert host._radar_worker_thread is None

    def test_unknown_archetype_skipped(self):
        host = _FakeHost({"Modern": "Unknown"}, resolved={"name": "x"})
        host._trigger_radar_load()
        assert host.controller.resolve_calls == []
        assert host._last_radar_archetype == ""

    def test_unresolved_archetype_sets_error(self):
        host = _FakeHost({"Modern": "UR Murktide"}, resolved=None)
        host._trigger_radar_load()
        assert host.controller.resolve_calls  # production resolver was invoked
        assert host.radar_panel.set_error_calls == ["Archetype 'UR Murktide' not found"]
        assert host._radar_worker_thread is None
        assert host._last_radar_archetype == ""

    def test_valid_archetype_starts_worker_and_sets_loading(self):
        resolved = {"name": "UR Murktide", "href": "/archetype/ur-murktide"}
        host = _FakeHost({"Modern": "UR Murktide"}, resolved=resolved)

        captured: dict[str, Any] = {}

        def calculate_radar(archetype_dict, format_name, max_decks, progress_callback):
            captured["args"] = (archetype_dict, format_name, max_decks)
            return _radar(mainboard=[_card("Murktide Regent", 4.0)])

        host.radar_service.calculate_radar = calculate_radar
        host._trigger_radar_load()
        _join_worker(host)

        assert host._last_radar_archetype == "UR Murktide"
        assert any("Loading radar" in m for m in host.radar_panel.set_loading_calls)
        assert captured["args"][0] is resolved
        assert captured["args"][1] == "Modern"
        # On success the worker marshals the radar to _display_radar.
        assert host.current_radar is not None
        assert host.radar_panel.display_radar_calls

    def test_duplicate_archetype_skipped(self):
        host = _FakeHost({"Modern": "UR Murktide"}, resolved={"name": "UR Murktide"})
        host._last_radar_archetype = "UR Murktide"
        host._trigger_radar_load()
        # Early-return before resolving / starting a worker.
        assert host.controller.resolve_calls == []
        assert host.radar_panel.set_loading_calls == []

    def test_in_progress_thread_skipped(self):
        host = _FakeHost({"Modern": "UR Murktide"}, resolved={"name": "UR Murktide"})

        started = threading.Event()
        release = threading.Event()

        def _busy() -> None:
            started.set()
            release.wait(timeout=5)

        live = threading.Thread(target=_busy, daemon=True)
        live.start()
        started.wait(timeout=5)
        host._radar_worker_thread = live

        host._trigger_radar_load()
        try:
            assert host.controller.resolve_calls == []
            assert host.radar_panel.set_loading_calls == []
        finally:
            release.set()
            live.join(timeout=5)


# --------------------------------------------------------------------------- #
# RadarMixin._generate_radar_worker                                           #
# --------------------------------------------------------------------------- #
class TestGenerateRadarWorker:
    def test_network_failure_sets_error_and_resets_thread(self):
        host = _FakeHost({"Modern": "UR Murktide"}, resolved={"name": "x"})
        host._radar_worker_thread = "sentinel"

        def calculate_radar(*_a, **_k):
            raise RuntimeError("Network error")

        host.radar_service.calculate_radar = calculate_radar
        host._generate_radar_worker({"name": "x"}, "Modern")

        assert host.radar_panel.set_error_calls == ["Failed to load radar"]
        assert host._radar_worker_thread is None  # finally block ran

    def test_cancellation_clears_panel(self):
        host = _FakeHost({"Modern": "UR Murktide"}, resolved={"name": "x"})
        host._radar_cancel_requested = True

        def calculate_radar(archetype_dict, format_name, max_decks, progress_callback):
            # The production update_progress closure raises InterruptedError
            # because cancellation was requested.
            progress_callback(1, 10, "Deck 1")
            raise AssertionError("calculate_radar should have been interrupted")

        host.radar_service.calculate_radar = calculate_radar
        host._generate_radar_worker({"name": "x"}, "Modern")

        assert host.radar_panel.clear_calls == 1
        assert host.radar_panel.set_error_calls == []
        assert host._radar_worker_thread is None

    def test_success_displays_radar(self):
        host = _FakeHost({"Modern": "UR Murktide"}, resolved={"name": "x"})
        radar = _radar(mainboard=[_card("Murktide Regent", 4.0)])

        def calculate_radar(archetype_dict, format_name, max_decks, progress_callback):
            progress_callback(1, 1, "Deck 1")  # not cancelled -> schedules loading
            return radar

        host.radar_service.calculate_radar = calculate_radar
        host._generate_radar_worker({"name": "x"}, "Modern")

        assert host.current_radar is radar
        assert host.radar_panel.display_radar_calls == [radar]
        assert any("Analyzing deck" in m for m in host.radar_panel.set_loading_calls)
        assert host._radar_worker_thread is None


# --------------------------------------------------------------------------- #
# RadarMixin._clear_radar_display                                             #
# --------------------------------------------------------------------------- #
class TestClearRadarDisplay:
    def test_resets_state_and_clears_panels(self):
        host = _FakeHost({"Modern": "UR Murktide"}, resolved={"name": "x"})
        host._last_radar_archetype = "UR Murktide"
        host.current_radar = _radar()
        host._radar_cancel_requested = False

        host._clear_radar_display()

        assert host._radar_cancel_requested is True
        assert host.current_radar is None
        assert host._last_radar_archetype == ""
        assert host._last_guide_archetype == ""
        assert host.radar_panel.clear_calls == 1
        assert host.sideboard_panel.clear_calls == 1


# --------------------------------------------------------------------------- #
# CompactRadarHandlersMixin                                                   #
# --------------------------------------------------------------------------- #
class _FakeLabel:
    def __init__(self) -> None:
        self.label = ""

    def SetLabel(self, text: str) -> None:
        self.label = text


class _FakeList:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def Append(self, line: str) -> None:
        self.lines.append(line)

    def Clear(self) -> None:
        self.lines = []


class _FakeButton:
    def __init__(self) -> None:
        self.shown = True
        self.label = ""

    def Show(self) -> None:
        self.shown = True

    def Hide(self) -> None:
        self.shown = False

    def SetLabel(self, text: str) -> None:
        self.label = text


class _FakeParent:
    def __init__(self) -> None:
        self.layout_calls = 0

    def Layout(self) -> None:
        self.layout_calls += 1


class _FakePanelHost(CompactRadarHandlersMixin):
    def __init__(self, view_mode):
        self.current_radar = None
        self.header_label = _FakeLabel()
        self.status_label = _FakeLabel()
        self.card_list = _FakeList()
        self.view_toggle_btn = _FakeButton()
        self._view_mode = view_mode
        self._parent = _FakeParent()
        self.shown = False

    def Show(self) -> None:
        self.shown = True

    def GetParent(self) -> _FakeParent:
        return self._parent


def _view_modes():
    props = _load_module(
        "_compact_radar_props_under_test",
        "widgets",
        "panels",
        "compact_radar_panel",
        "properties.py",
    )
    return props.RadarViewMode


_RadarViewMode = _view_modes()


class TestCompactRadarSetters:
    def test_clear_resets_labels_list_and_button(self):
        panel = _FakePanelHost(_RadarViewMode.TOP_CARDS)
        panel.current_radar = _radar()
        panel.card_list.lines = ["stale"]
        panel.view_toggle_btn.shown = True

        panel.clear()

        assert panel.current_radar is None
        assert panel.header_label.label == "Radar: —"
        assert "Waiting for opponent" in panel.status_label.label
        assert panel.card_list.lines == []
        assert panel.view_toggle_btn.shown is False
        assert panel._parent.layout_calls == 1

    def test_set_error_shows_message(self):
        panel = _FakePanelHost(_RadarViewMode.TOP_CARDS)
        panel.set_error("boom")
        assert panel.header_label.label == "Radar: Error"
        assert panel.status_label.label == "boom"
        assert panel.view_toggle_btn.shown is False
        assert panel.shown is True

    def test_set_loading_shows_message(self):
        panel = _FakePanelHost(_RadarViewMode.TOP_CARDS)
        panel.set_loading("Loading radar for UR Murktide...")
        assert panel.header_label.label == "Radar: Loading..."
        assert panel.status_label.label == "Loading radar for UR Murktide..."
        assert panel.view_toggle_btn.shown is False
        assert panel.shown is True


class TestCompactRadarFormatting:
    def test_top_cards_line_format_and_clamping(self):
        panel = _FakePanelHost(_RadarViewMode.TOP_CARDS)
        # 0.3 must clamp up to 1; 95.6% must floor-format to 96 via :.0f rounding.
        panel.current_radar = _radar(
            mainboard=[
                _card("Lightning Bolt", 4.0, inclusion_rate=95.0),
                _card("Spell Pierce", 0.3, inclusion_rate=40.0),
            ],
            sideboard=[_card("Mystical Dispute", 2.4, inclusion_rate=60.0)],
        )

        panel._populate_top_cards()

        assert "4x Lightning Bolt (95%)" in panel.card_list.lines
        # max(1, int(round(0.3))) == 1
        assert "1x Spell Pierce (40%)" in panel.card_list.lines
        # max(1, int(round(2.4))) == 2
        assert "2x Mystical Dispute (60%)" in panel.card_list.lines
        assert "─── Mainboard ───" in panel.card_list.lines
        assert "─── Sideboard ───" in panel.card_list.lines

    def test_top_cards_respects_limits(self):
        props = _load_module(
            "_compact_radar_props_limits",
            "widgets",
            "panels",
            "compact_radar_panel",
            "properties.py",
        )
        mainboard = [_card(f"MB {i}", 1.0) for i in range(props._TOP_MAINBOARD_LIMIT + 5)]
        sideboard = [_card(f"SB {i}", 1.0) for i in range(props._TOP_SIDEBOARD_LIMIT + 5)]
        panel = _FakePanelHost(_RadarViewMode.TOP_CARDS)
        panel.current_radar = _radar(mainboard=mainboard, sideboard=sideboard)

        panel._populate_top_cards()

        mb_lines = [line for line in panel.card_list.lines if line.startswith("1x MB ")]
        sb_lines = [line for line in panel.card_list.lines if line.startswith("1x SB ")]
        assert len(mb_lines) == props._TOP_MAINBOARD_LIMIT
        assert len(sb_lines) == props._TOP_SIDEBOARD_LIMIT

    def test_full_decklist_line_format_and_clamping(self):
        panel = _FakePanelHost(_RadarViewMode.FULL_DECKLIST)
        panel.current_radar = _radar(
            mainboard=[_card("Murktide Regent", 4.0), _card("Spell Pierce", 0.3)],
            sideboard=[_card("Mystical Dispute", 2.4)],
        )

        panel._populate_full_decklist()

        assert "4 Murktide Regent" in panel.card_list.lines
        # round(0.3) == 0 -> clamped to 1
        assert "1 Spell Pierce" in panel.card_list.lines
        # round(2.4) == 2
        assert "2 Mystical Dispute" in panel.card_list.lines
        # Mainboard header carries the clamped total (4 + 1 = 5).
        assert "─── Mainboard (5) ───" in panel.card_list.lines
        assert "─── Sideboard (2) ───" in panel.card_list.lines

    def test_display_radar_sets_header_and_shows(self):
        panel = _FakePanelHost(_RadarViewMode.TOP_CARDS)
        radar = _radar(mainboard=[_card("Murktide Regent", 4.0)])

        panel.display_radar(radar)

        assert panel.current_radar is radar
        assert panel.header_label.label == "Radar: UR Murktide"
        assert panel.view_toggle_btn.shown is True
        assert panel.shown is True
        assert any("Murktide Regent" in line for line in panel.card_list.lines)


# --------------------------------------------------------------------------- #
# services.archetype_resolver                                                 #
# --------------------------------------------------------------------------- #
class _FakeRepo:
    def __init__(self, archetypes, raises: bool = False) -> None:
        self._archetypes = archetypes
        self._raises = raises

    def get_archetypes_for_format(self, format_name):
        if self._raises:
            raise RuntimeError("scrape failed")
        return self._archetypes


class TestArchetypeResolver:
    def test_normalize(self):
        from services.archetype_resolver import normalize_archetype_name

        assert normalize_archetype_name("  UR   Murktide ") == "ur murktide"
        assert normalize_archetype_name("UR Murktide") == normalize_archetype_name("ur murktide")

    def test_exact_match(self):
        from services.archetype_resolver import find_archetype_by_name

        repo = _FakeRepo([{"name": "UR Murktide"}, {"name": "Azorius Control"}])
        result = find_archetype_by_name("ur murktide", "Modern", repo)
        assert result == {"name": "UR Murktide"}

    def test_forward_containment_partial_match(self):
        from services.archetype_resolver import find_archetype_by_name

        # input ("murktide") is contained in a candidate name.
        repo = _FakeRepo([{"name": "UR Murktide"}])
        result = find_archetype_by_name("Murktide", "Modern", repo)
        assert result == {"name": "UR Murktide"}

    def test_reverse_containment_partial_match(self):
        from services.archetype_resolver import find_archetype_by_name

        # candidate name ("murktide") is contained in the input.
        repo = _FakeRepo([{"name": "Murktide"}])
        result = find_archetype_by_name("UR Murktide Tempo", "Modern", repo)
        assert result == {"name": "Murktide"}

    def test_no_match_returns_none(self):
        from services.archetype_resolver import find_archetype_by_name

        repo = _FakeRepo([{"name": "Azorius Control"}])
        assert find_archetype_by_name("Burn", "Modern", repo) is None

    def test_repo_error_returns_none(self):
        from services.archetype_resolver import find_archetype_by_name

        repo = _FakeRepo([], raises=True)
        assert find_archetype_by_name("Burn", "Modern", repo) is None


# --------------------------------------------------------------------------- #
# RadarData / CardFrequency models                                            #
# --------------------------------------------------------------------------- #
def test_radar_data_structure():
    radar = _radar(mainboard=[_card("Murktide Regent", 4.0, inclusion_rate=100.0)])
    assert radar.archetype_name == "UR Murktide"
    assert radar.format_name == "Modern"
    assert len(radar.mainboard_cards) == 1
    assert radar.mainboard_cards[0].card_name == "Murktide Regent"
    assert radar.mainboard_cards[0].inclusion_rate == 100.0
