"""Tests for wx-independent methods of CardBoxPanel."""

from __future__ import annotations

import importlib.util
import sys
from typing import Any

import pytest

from utils.background_worker import BackgroundWorker

pytest.importorskip("wx")


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

    def __init__(self, name: str = "", **kwargs: Any) -> None:
        self._data = {"name": name, **kwargs}

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
        # When meta has no "name" key (plain dict), no DFC promotion happens even
        # if there is a "//" alias — only meta.name drives the promotion.
        ({"name": "A"}, {"aliases": ["A // B", "Other"]}, ["A", "A // B", "Other"]),
        # When base_name is itself the combined name, the new promotion branch is
        # not entered (requires no "//" in base_name).
        ({"name": "A // B"}, {"aliases": ["A // B", "A", "B"]}, ["A // B", "A", "B"]),
        ({"name": "A"}, {"aliases": "bad"}, ["A"]),
        ({"name": ""}, {}, []),
        # CardEntry-like object: isinstance(meta, dict) is False but .get() works.
        # When meta.name is a combined DFC name, it is promoted to position 0 so
        # the reliable combined-name → front-face DB entry is tried first.
        # Regression guard for the msgspec fix + promotion logic.
        (
            {"name": "Witch Enchanter"},
            _CardEntryStub(
                name="Witch Enchanter // Witch-Blessed Meadow",
                aliases=[
                    "Witch Enchanter",
                    "Witch Enchanter // Witch-Blessed Meadow",
                    "Witch-Blessed Meadow",
                ],
            ),
            [
                "Witch Enchanter // Witch-Blessed Meadow",
                "Witch Enchanter",
                "Witch-Blessed Meadow",
            ],
        ),
        # CardEntry with combined base name: new promotion branch not entered
        # (base_name already contains "//"); aliases stay in insertion order.
        (
            {"name": "Witch Enchanter // Witch-Blessed Meadow"},
            _CardEntryStub(
                name="Witch Enchanter // Witch-Blessed Meadow",
                aliases=["Witch Enchanter", "Witch-Blessed Meadow"],
            ),
            ["Witch Enchanter // Witch-Blessed Meadow", "Witch Enchanter", "Witch-Blessed Meadow"],
        ),
    ],
    ids=[
        "simple-card",
        "dfc-combined-name",
        "non-dfc-alias",
        "dfc-alias-no-promotion-without-meta-name",
        "dfc-combined-base-with-face-aliases",
        "non-list-aliases",
        "empty-name",
        "cardentry-face-name-promotes-combined-to-front",
        "cardentry-combined-base-no-promotion",
    ],
)
def test_build_image_name_candidates(card: dict[str, Any], meta: Any, expected: list[str]) -> None:
    """_build_image_name_candidates must return the correct candidate list for each input."""
    result = CardBoxPanel._build_image_name_candidates(None, card, meta)
    assert result == expected


def test_image_load_worker_skips_ui_callback_after_worker_shutdown(monkeypatch) -> None:
    """Late image lookups must not queue wx callbacks after panel teardown."""
    panel = CardBoxPanel.__new__(CardBoxPanel)
    panel._image_worker = BackgroundWorker()
    panel._image_worker.shutdown(timeout=0.1)
    callbacks: list[tuple[int, object]] = []
    panel._on_image_load_done = lambda gen, image: callbacks.append((gen, image))

    monkeypatch.setattr(_cbp_mod, "get_card_image", lambda *_args, **_kwargs: None)

    CardBoxPanel._image_load_worker(panel, 7, ["Island"])

    assert callbacks == []


def test_on_destroy_stops_image_worker_without_waiting() -> None:
    panel = CardBoxPanel.__new__(CardBoxPanel)
    shutdown_calls: list[float] = []
    panel._image_worker = type(
        "Worker",
        (),
        {"shutdown": lambda self, timeout=10.0: shutdown_calls.append(timeout)},
    )()
    skipped = []
    event = type(
        "Event",
        (),
        {
            "GetEventObject": lambda self: panel,
            "Skip": lambda self: skipped.append(True),
        },
    )()

    CardBoxPanel._on_destroy(panel, event)

    assert shutdown_calls == [0.0]
    assert skipped == [True]
