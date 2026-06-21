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
module is injected before the handler modules are imported by file path. So the
marshalled UI calls can be asserted directly, the handler modules loaded under
test get their module-global ``wx`` rebound to a proxy whose ``CallAfter`` runs
synchronously. Crucially this rebind is scoped to *these* modules only -- the
shared ``wx`` module in ``sys.modules`` is left untouched, because other test
files (e.g. the wxPython UI tests) rely on the real, asynchronous
``wx.CallAfter`` to defer work off the construction path. Globally forcing
``CallAfter`` synchronous makes deferred callbacks such as the opponent
tracker's tutorial dialog fire mid-construction and block the whole suite on a
modal ``ShowModal()``.
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


class _SyncCallAfterWx(types.ModuleType):
    """Proxy around the resolved ``wx`` whose ``CallAfter`` runs synchronously.

    Bound as the *loaded-under-test* handler modules' ``wx`` global so the
    worker's marshalled UI calls execute inline (and can be asserted) without
    a ``wx.App``. Every other attribute delegates to the real/stub ``wx``. This
    proxy is NEVER placed in ``sys.modules``: mutating the shared ``wx`` module
    would make ``CallAfter`` synchronous for the whole test session and hang the
    wxPython UI tests, whose harness depends on deferred callbacks.
    """

    def __init__(self, base: types.ModuleType) -> None:
        super().__init__("wx")
        self.__dict__["_base"] = base

    def __getattr__(self, name: str) -> Any:
        return getattr(self.__dict__["_base"], name)

    @staticmethod
    def CallAfter(func: Any, *args: Any, **kwargs: Any) -> Any:  # noqa: N802
        return func(*args, **kwargs)


def _ensure_wx_importable() -> types.ModuleType:
    """Return the ``wx`` module the handlers should import, leaving it untouched.

    On the Windows CI runner the real ``wx`` is importable and is returned as-is
    (no global mutation). On the WSL dev box ``wx`` is absent, so a permissive
    stub is injected into ``sys.modules`` -- required because importing the
    handler modules transitively imports ``wx`` (e.g. ``services.radar_service``
    pulls in ``utils.constants.keyboard``).
    """
    try:
        import wx as real_wx

        return real_wx
    except Exception:
        stub = _WxStub("wx")
        sys.modules["wx"] = stub
        return stub


def _load_module(name: str, *parts: str) -> types.ModuleType:
    """Import a module by file path and give it a synchronous ``wx.CallAfter``.

    The module's own ``import wx`` binds the shared ``wx`` object; we rebind the
    module global to a per-module proxy so its marshalled UI calls run inline
    without affecting any other module's ``wx``.
    """
    path = Path(__file__).resolve().parent.parent.joinpath(*parts)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if hasattr(module, "wx"):
        module.wx = _SyncCallAfterWx(module.wx)
    return module


# wx must be importable before loading anything that transitively imports it
# (services.radar_service pulls in utils.constants.keyboard, which imports wx).
_ensure_wx_importable()

from services.radar_service import CardFrequency, RadarData  # noqa: E402

RadarMixin = _load_module(
    "_radar_handler_under_test",
    "widgets",
    "frames",
    "identify_opponent",
    "handlers",
    "radar.py",
).RadarMixin
_compact_radar_handlers_module = _load_module(
    "_compact_radar_handlers_under_test",
    "widgets",
    "panels",
    "compact_radar_panel",
    "handlers.py",
)
CompactRadarHandlersMixin = _compact_radar_handlers_module.CompactRadarHandlersMixin


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


class _RecordingResolver:
    """Wraps the real resolver, recording each call's arguments.

    Bound onto the host controller as ``find_archetype_by_name`` so the
    resolution-branch tests drive the *production* resolver
    (:func:`services.archetype_resolver.find_archetype_by_name`) against a
    :class:`_FakeRepo` (the network seam) instead of a hand-stubbed return.
    """

    def __init__(self) -> None:
        self.resolve_calls: list[tuple] = []

    def __call__(self, archetype_name, format_name, repo):
        from services.archetype_resolver import find_archetype_by_name

        self.resolve_calls.append((archetype_name, format_name, repo))
        return find_archetype_by_name(archetype_name, format_name, repo)


class _FakeController:
    """Controller seam that resolves archetypes via the real resolver.

    ``archetypes`` is the list the backing :class:`_FakeRepo` returns for the
    requested format; the production resolver matches against it. ``resolve_calls``
    captures the arguments the mixin forwarded.
    """

    def __init__(self, archetypes: list[dict[str, Any]] | None) -> None:
        self._resolver = _RecordingResolver()
        self.repo = _FakeRepo(list(archetypes or []))
        self.find_archetype_by_name = self._resolver

    @property
    def resolve_calls(self) -> list[tuple]:
        return self._resolver.resolve_calls


class _FakeHost(RadarMixin):
    """Concrete :class:`RadarMixin` host with the collaborators it touches."""

    def __init__(self, last_seen_decks, archetypes):
        self.last_seen_decks = last_seen_decks
        self._last_radar_archetype = ""
        self._radar_worker_thread = None
        self._radar_cancel_requested = False
        self.current_radar = None
        self._last_guide_archetype = "stale"
        self.radar_panel = _FakePanel()
        self.sideboard_panel = _FakePanel()
        self.controller = _FakeController(archetypes)
        # The mixin forwards this repo into the resolver as its network seam.
        self.metagame_service = types.SimpleNamespace(metagame_repo=self.controller.repo)
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
        host = _FakeHost({}, archetypes=[{"name": "UR Murktide"}])
        host._trigger_radar_load()
        assert host.controller.resolve_calls == []
        assert host._radar_worker_thread is None

    def test_unknown_archetype_skipped(self):
        host = _FakeHost({"Modern": "Unknown"}, archetypes=[{"name": "x"}])
        host._trigger_radar_load()
        assert host.controller.resolve_calls == []
        assert host._last_radar_archetype == ""

    def test_unresolved_archetype_sets_error(self):
        # Repo has no matching archetype, so the real resolver returns None.
        host = _FakeHost({"Modern": "UR Murktide"}, archetypes=[{"name": "Burn"}])
        host._trigger_radar_load()
        # The production resolver was invoked with the forwarded repo.
        assert host.controller.resolve_calls == [
            ("UR Murktide", "Modern", host.metagame_service.metagame_repo)
        ]
        assert host.radar_panel.set_error_calls == ["Archetype 'UR Murktide' not found"]
        assert host._radar_worker_thread is None
        assert host._last_radar_archetype == ""

    def test_valid_archetype_starts_worker_and_sets_loading(self):
        resolved = {"name": "UR Murktide", "href": "/archetype/ur-murktide"}
        host = _FakeHost({"Modern": "UR Murktide"}, archetypes=[resolved])

        captured: dict[str, Any] = {}

        def calculate_radar(archetype_dict, format_name, max_decks, progress_callback):
            captured["args"] = (archetype_dict, format_name, max_decks)
            return _radar(mainboard=[_card("Murktide Regent", 4.0)])

        host.radar_service.calculate_radar = calculate_radar
        host._trigger_radar_load()
        _join_worker(host)

        assert host._last_radar_archetype == "UR Murktide"
        assert any("Loading radar" in m for m in host.radar_panel.set_loading_calls)
        # The real resolver returned the matching archetype dict from the repo.
        assert captured["args"][0] is resolved
        assert captured["args"][1] == "Modern"
        # On success the worker marshals the radar to _display_radar.
        assert host.current_radar is not None
        assert host.radar_panel.display_radar_calls

    def test_duplicate_archetype_skipped(self):
        host = _FakeHost({"Modern": "UR Murktide"}, archetypes=[{"name": "UR Murktide"}])
        host._last_radar_archetype = "UR Murktide"
        host._trigger_radar_load()
        # Early-return before resolving / starting a worker.
        assert host.controller.resolve_calls == []
        assert host.radar_panel.set_loading_calls == []

    def test_in_progress_thread_skipped(self):
        host = _FakeHost({"Modern": "UR Murktide"}, archetypes=[{"name": "UR Murktide"}])

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
        host = _FakeHost({"Modern": "UR Murktide"}, archetypes=[{"name": "x"}])
        host._radar_worker_thread = "sentinel"

        def calculate_radar(*_a, **_k):
            raise RuntimeError("Network error")

        host.radar_service.calculate_radar = calculate_radar
        host._generate_radar_worker({"name": "x"}, "Modern")

        assert host.radar_panel.set_error_calls == ["Failed to load radar"]
        assert host._radar_worker_thread is None  # finally block ran

    def test_cancellation_clears_panel(self):
        host = _FakeHost({"Modern": "UR Murktide"}, archetypes=[{"name": "x"}])
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
        host = _FakeHost({"Modern": "UR Murktide"}, archetypes=[{"name": "x"}])
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
        host = _FakeHost({"Modern": "UR Murktide"}, archetypes=[{"name": "x"}])
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


# Use the SAME ``RadarViewMode`` enum the handler module compares against. The
# handler module imports it from the canonical ``sys.modules`` properties module,
# so a fresh file-path reload would yield a distinct, non-identical enum and the
# handler's ``self._view_mode == RadarViewMode.TOP_CARDS`` checks would never match.
_RadarViewMode = _compact_radar_handlers_module.RadarViewMode


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
        # avg_copies 0.3 must clamp up to 1; inclusion_rate 95.0 renders as "95%".
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

    def test_top_cards_inclusion_rate_rounds_via_format(self):
        # The ``:.0f`` format rounds half-to-even at the boundary: 95.6 -> "96".
        panel = _FakePanelHost(_RadarViewMode.TOP_CARDS)
        panel.current_radar = _radar(
            mainboard=[_card("Counterspell", 3.0, inclusion_rate=95.6)],
        )

        panel._populate_top_cards()

        assert "3x Counterspell (96%)" in panel.card_list.lines

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

    def test_display_radar_in_full_decklist_mode_uses_full_populator(self):
        # display_radar -> _populate_card_list must dispatch on the view mode.
        panel = _FakePanelHost(_RadarViewMode.FULL_DECKLIST)
        radar = _radar(mainboard=[_card("Murktide Regent", 4.0)])

        panel.display_radar(radar)

        # FULL_DECKLIST lines have no "x" multiplier and carry a count header.
        assert "4 Murktide Regent" in panel.card_list.lines
        assert "─── Mainboard (4) ───" in panel.card_list.lines
        assert not any(line.startswith("4x ") for line in panel.card_list.lines)


class TestCompactRadarToggle:
    def test_toggle_flips_mode_relabels_and_repopulates(self):
        panel = _FakePanelHost(_RadarViewMode.TOP_CARDS)
        panel.current_radar = _radar(mainboard=[_card("Murktide Regent", 4.0)])

        panel._on_toggle_view(None)

        assert panel._view_mode is _RadarViewMode.FULL_DECKLIST
        # Label now advertises the *other* mode you can switch back to.
        assert panel.view_toggle_btn.label == "Top Cards"
        # Re-populated in FULL_DECKLIST format.
        assert "4 Murktide Regent" in panel.card_list.lines

        panel._on_toggle_view(None)

        assert panel._view_mode is _RadarViewMode.TOP_CARDS
        assert panel.view_toggle_btn.label == "Full Decklist"
        assert any(line.startswith("4x ") for line in panel.card_list.lines)

    def test_update_toggle_button_label_reflects_mode(self):
        panel = _FakePanelHost(_RadarViewMode.TOP_CARDS)
        panel._update_toggle_button_label()
        assert panel.view_toggle_btn.label == "Full Decklist"

        panel._view_mode = _RadarViewMode.FULL_DECKLIST
        panel._update_toggle_button_label()
        assert panel.view_toggle_btn.label == "Top Cards"


class TestCompactRadarNoRadarGuards:
    def test_populate_card_list_no_radar_is_noop(self):
        panel = _FakePanelHost(_RadarViewMode.TOP_CARDS)
        panel.current_radar = None
        panel._populate_card_list()
        assert panel.card_list.lines == []

    def test_populate_top_cards_no_radar_is_noop(self):
        panel = _FakePanelHost(_RadarViewMode.TOP_CARDS)
        panel.current_radar = None
        panel._populate_top_cards()
        assert panel.card_list.lines == []

    def test_populate_full_decklist_no_radar_is_noop(self):
        panel = _FakePanelHost(_RadarViewMode.FULL_DECKLIST)
        panel.current_radar = None
        panel._populate_full_decklist()
        assert panel.card_list.lines == []


class TestCompactRadarProperties:
    def test_view_mode_property_reflects_internal_state(self):
        props = _load_module(
            "_compact_radar_props_accessor",
            "widgets",
            "panels",
            "compact_radar_panel",
            "properties.py",
        )

        class _Host(props.CompactRadarPropertiesMixin):
            def __init__(self, mode):
                self._view_mode = mode

        host = _Host(props.RadarViewMode.FULL_DECKLIST)
        assert host.view_mode is props.RadarViewMode.FULL_DECKLIST
        host._view_mode = props.RadarViewMode.TOP_CARDS
        assert host.view_mode is props.RadarViewMode.TOP_CARDS


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
