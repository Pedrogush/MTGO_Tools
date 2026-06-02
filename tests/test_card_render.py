"""Tests for the wx-independent card-render helpers."""

from __future__ import annotations

from typing import Any

import pytest

from widgets.mana_icon_factory import ManaIconFactory
from widgets.panels.card_table_panel.card_render import (
    build_image_name_candidates,
    resolve_card_color,
)


class _CardEntryStub:
    """Minimal stand-in for repositories.card_repository.CardEntry (a msgspec.Struct).

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
        # meta=None must short-circuit the alias/promotion branches (lines 31, 36)
        # and return only the base name.
        ({"name": "Island"}, None, ["Island"]),
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
        "none-meta",
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
    """build_image_name_candidates must return the correct candidate list for each input."""
    result = build_image_name_candidates(card, meta)
    assert result == expected


# ---------------------------------------------------------------------------
# resolve_card_color
# ---------------------------------------------------------------------------
_FALLBACK = ManaIconFactory.FALLBACK_COLORS


@pytest.mark.parametrize(
    "meta, expected",
    [
        # No color info at all -> colorless fallback.
        ({}, _FALLBACK["c"]),
        ({"color_identity": []}, _FALLBACK["c"]),
        ({"color_identity": [], "colors": []}, _FALLBACK["c"]),
        # Single known color, already lowercase.
        ({"color_identity": ["w"]}, _FALLBACK["w"]),
        # Single known color, normalized from uppercase.
        ({"color_identity": ["W"]}, _FALLBACK["w"]),
        ({"color_identity": ["U"]}, _FALLBACK["u"]),
        # Single unknown color -> colorless fallback via .get() default.
        ({"color_identity": ["X"]}, _FALLBACK["c"]),
        # color_identity takes precedence over colors when non-empty.
        ({"color_identity": ["R"], "colors": ["G"]}, _FALLBACK["r"]),
        # color_identity empty -> falls back to colors.
        ({"color_identity": [], "colors": ["G"]}, _FALLBACK["g"]),
        ({"colors": ["B"]}, _FALLBACK["b"]),
        # Falsy entries (None, "") are filtered out before counting.
        ({"color_identity": [None, "", "W"]}, _FALLBACK["w"]),
        ({"color_identity": [None, ""]}, _FALLBACK["c"]),
        # Two or more colors -> multicolor fallback.
        ({"color_identity": ["W", "U"]}, _FALLBACK["multicolor"]),
        ({"color_identity": ["w", "u", "b"]}, _FALLBACK["multicolor"]),
    ],
    ids=[
        "empty-meta",
        "empty-identity",
        "empty-identity-and-colors",
        "single-lowercase",
        "single-uppercase-normalized",
        "single-u",
        "single-unknown-color-falls-back-to-c",
        "identity-wins-over-colors",
        "empty-identity-falls-back-to-colors",
        "colors-only",
        "falsy-entries-filtered-single",
        "falsy-entries-filtered-empty",
        "multicolor-two",
        "multicolor-three",
    ],
)
def test_resolve_card_color(meta: dict[str, Any], expected: tuple[int, int, int]) -> None:
    """resolve_card_color must map metadata to the correct placeholder RGB color."""
    assert resolve_card_color(meta) == expected
