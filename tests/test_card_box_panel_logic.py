"""Tests for wx-independent methods of CardBoxPanel."""

from __future__ import annotations

from typing import Any

import pytest

from widgets.panels.card_box_panel import CardBoxPanel


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
