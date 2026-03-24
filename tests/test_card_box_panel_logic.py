"""Tests for wx-independent methods of CardBoxPanel.

These tests cover pure-Python logic that does not require a wx display or
event loop. wx is stubbed out via sys.modules so the tests run in headless
CI environments without wxPython installed.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub wx BEFORE importing any wx-dependent module.
# card_box_panel.py is loaded directly (bypassing widgets/panels/__init__.py)
# to avoid pulling in unrelated panel modules that have additional
# transitive dependencies (bs4, services, etc.).
# ---------------------------------------------------------------------------
if "wx" not in sys.modules:
    _wx_stub = MagicMock()
    # wx.Panel must be a real Python class so CardBoxPanel can inherit from it.
    _wx_stub.Panel = type("_WxPanel", (object,), {})
    sys.modules["wx"] = _wx_stub


def _load_card_box_panel_module():
    """Load widgets/panels/card_box_panel.py directly, bypassing the package __init__."""
    import pathlib

    src = pathlib.Path(__file__).parent.parent / "widgets" / "panels" / "card_box_panel.py"
    spec = importlib.util.spec_from_file_location("widgets.panels.card_box_panel", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["widgets.panels.card_box_panel"] = mod
    spec.loader.exec_module(mod)
    return mod


_cbp_mod = _load_card_box_panel_module()
CardBoxPanel = _cbp_mod.CardBoxPanel


class _CardEntryStub:
    """Minimal stand-in for utils.card_data.CardEntry (a msgspec.Struct).

    isinstance(stub, dict) is False, but stub.get(key) works — mirroring the
    real CardEntry behaviour.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._data = kwargs

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)


# ---------------------------------------------------------------------------
# _build_image_name_candidates
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "card, meta, expected",
    [
        ({"name": "Island"}, {}, ["Island"]),
        ({"name": "A // B"}, {}, ["A // B"]),
        ({"name": "A"}, {"aliases": ["Alias1"]}, ["A", "Alias1"]),
        # When base_name is a single face name the combined DFC alias must NOT
        # be promoted to position 0 — the face-specific name should remain
        # first so the image lookup returns the correct face image.
        ({"name": "A"}, {"aliases": ["A // B", "Other"]}, ["A", "A // B", "Other"]),
        # When base_name is itself the combined name, any duplicate combined
        # alias is a no-op (it is already candidates[0]).
        ({"name": "A // B"}, {"aliases": ["A // B", "A", "B"]}, ["A // B", "A", "B"]),
        ({"name": "A"}, {"aliases": "bad"}, ["A"]),
        ({"name": ""}, {}, []),
        # CardEntry-like object: isinstance(meta, dict) is False but .get() works.
        # Aliases must still be extracted — regression guard for the msgspec fix.
        (
            {"name": "Witch Enchanter"},
            _CardEntryStub(
                aliases=["Eriette's Temptation // Witch Enchanter", "Eriette's Temptation"]
            ),
            ["Witch Enchanter", "Eriette's Temptation // Witch Enchanter", "Eriette's Temptation"],
        ),
        # CardEntry with combined base name: combined alias stays at position 0.
        (
            {"name": "Eriette's Temptation // Witch Enchanter"},
            _CardEntryStub(aliases=["Eriette's Temptation", "Witch Enchanter"]),
            ["Eriette's Temptation // Witch Enchanter", "Eriette's Temptation", "Witch Enchanter"],
        ),
    ],
    ids=[
        "simple-card",
        "dfc-combined-name",
        "non-dfc-alias",
        "dfc-alias-not-promoted-for-face-name",
        "dfc-combined-base-with-face-aliases",
        "non-list-aliases",
        "empty-name",
        "cardentry-back-face-aliases-extracted",
        "cardentry-combined-base-aliases-extracted",
    ],
)
def test_build_image_name_candidates(card: dict[str, Any], meta: Any, expected: list[str]) -> None:
    """_build_image_name_candidates must return the correct candidate list for each input."""
    result = CardBoxPanel._build_image_name_candidates(None, card, meta)
    assert result == expected


# ---------------------------------------------------------------------------
# preload_image
# ---------------------------------------------------------------------------
def test_preload_image_is_no_op() -> None:
    """preload_image() is now a no-op; it must not crash or call _refresh_card_bitmap."""
    call_count = 0

    def fake_refresh() -> None:
        nonlocal call_count
        call_count += 1

    stub = types.SimpleNamespace(_image_attempted=False, _refresh_card_bitmap=fake_refresh)

    CardBoxPanel.preload_image(stub)
    CardBoxPanel.preload_image(stub)

    assert call_count == 0


def test_preload_image_does_not_raise_regardless_of_state() -> None:
    """preload_image() must be safe to call whether or not _image_attempted is set."""
    for attempted in (True, False):
        stub = types.SimpleNamespace(_image_attempted=attempted)
        CardBoxPanel.preload_image(stub)  # must not raise
