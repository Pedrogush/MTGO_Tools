"""Tests for the wx-independent card-render helpers.

The helpers under test are pure, but the schema (``CardEntry``) and the
``FALLBACK_COLORS`` table are reached through packages whose ``__init__`` /
module imports pull in ``wx`` (``repositories.card_repository.__init__`` ->
``utils.constants.keyboard`` and ``widgets.mana_icon_factory.factory``). This
module therefore only collects on Windows / CI where ``wx`` is installed; it is
not runnable from a wx-less WSL checkout.
"""

from __future__ import annotations

from typing import Any

import pytest

from repositories.card_repository.schemas import CardEntry
from widgets.mana_icon_factory import ManaIconFactory
from widgets.panels.card_table_panel.card_render import (
    build_image_name_candidates,
    resolve_card_color,
)


def _card_entry(name: str = "", aliases: list[str] | None = None, **kwargs: Any) -> CardEntry:
    """Build a real CardEntry with sensible defaults for its required fields.

    Exercises the production msgspec.Struct (isinstance(entry, dict) is False but
    entry.get(key) works) instead of a hand-rolled fake.
    """
    return CardEntry(
        name=name,
        name_lower=name.lower(),
        aliases=aliases if aliases is not None else [],
        colors=kwargs.pop("colors", []),
        color_identity=kwargs.pop("color_identity", []),
        legalities=kwargs.pop("legalities", {}),
        **kwargs,
    )


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
        # Falsy aliases (None, "") are skipped by the `if alias` filter; valid
        # ones (including duplicates of base_name) are de-duplicated.
        ({"name": "A"}, {"aliases": [None, "", "A", "Alias1"]}, ["A", "Alias1"]),
        # A "//" meta name that is NOT among the candidates must not be
        # spuriously inserted: the promotion branch only reorders an existing
        # candidate (lines 36-40), it never appends a new one.
        ({"name": "A"}, {"name": "X // Y", "aliases": ["Alias1"]}, ["A", "Alias1"]),
        ({"name": ""}, {}, []),
        # Empty base_name with non-empty aliases: no base name is appended, so
        # only the (filtered) aliases drive the candidate list.
        ({"name": ""}, {"aliases": ["Foo"]}, ["Foo"]),
        # CardEntry-like object: isinstance(meta, dict) is False but .get() works.
        # When meta.name is a combined DFC name, it is promoted to position 0 so
        # the reliable combined-name → front-face DB entry is tried first.
        # Regression guard for the msgspec fix + promotion logic.
        (
            {"name": "Witch Enchanter"},
            _card_entry(
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
            _card_entry(
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
        "falsy-aliases-filtered-and-deduped",
        "meta-name-combined-not-in-candidates-no-insert",
        "empty-name",
        "empty-name-with-aliases",
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
