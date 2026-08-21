"""Regression guards for the visible defects closed in phase 4 of #962.

Each of these encodes an invariant that was violated on screen, so that the
specific pixel-level bug cannot come back silently. They deliberately assert the
*rule*, not the current numbers, except where the number is the point.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from utils.constants import (
    DECK_CARD_ACTION_BUTTON_SIZE,
    DECK_CARD_BADGE_ANCHOR_FRACTION,
    DECK_CARD_BUTTON_MARGIN,
    DECK_CARD_COUNT_MAX_DOTS,
    DECK_CARD_HEIGHT,
    DECK_CARD_WIDTH,
)
from utils.i18n import MESSAGES, SUPPORTED_LOCALES

# A Magic card's title bar occupies roughly the top 9% of the frame; the art box
# runs from there to ~52%. These are the two bands the quantity badge has to
# stay out of and inside of respectively (H1).
_TITLE_BAND_BOTTOM_FRACTION = 0.10


def _badge_rect(text_w: int = 8, text_h: int = 17):
    """``badge_rect`` for a card at the origin, without importing wx at module scope."""
    import wx

    from widgets.panels.card_table_panel.grid_layout import badge_rect

    return badge_rect(wx.Rect(0, 0, DECK_CARD_WIDTH, DECK_CARD_HEIGHT), text_w, text_h)


# ---------------------------------------------------------------- H1


def test_quantity_badge_clears_the_card_title_band() -> None:
    """H1: the badge used to be painted at ``rect.x + pad, rect.y + pad``.

    On every Magic frame that is the *title*, which is why the review could read
    "gatha's Soul Cauldron" and "rds of Paradise" straight off the captures.
    """
    _x, y, _w, _h = _badge_rect()
    assert (
        y > DECK_CARD_HEIGHT * _TITLE_BAND_BOTTOM_FRACTION
    ), "the quantity badge is back inside the card's title band"


def test_quantity_badge_stays_inside_the_art_box() -> None:
    """The badge's bottom sits on the art box's lower edge, not past it."""
    _x, y, _w, h = _badge_rect()
    assert y + h <= DECK_CARD_HEIGHT * DECK_CARD_BADGE_ANCHOR_FRACTION


def test_quantity_badge_does_not_collide_with_the_action_chips() -> None:
    """The +/-/x chips are pinned to the bottom margin and appear on hover.

    A badge that overlapped them would flicker under the pointer, which is how
    "move it to the bottom-left" would have gone wrong.
    """
    _x, y, _w, h = _badge_rect()
    _btn_w, btn_h = DECK_CARD_ACTION_BUTTON_SIZE
    chips_top = DECK_CARD_HEIGHT - DECK_CARD_BUTTON_MARGIN - btn_h
    assert y + h <= chips_top


# ---------------------------------------------------------------- #987


def _count_dots(count: int):
    """``count_dot_layout`` for a card at the origin, wx imported lazily."""
    import wx

    from widgets.panels.card_table_panel.grid_layout import count_dot_layout

    return count_dot_layout(wx.Rect(0, 0, DECK_CARD_WIDTH, DECK_CARD_HEIGHT), count)


@pytest.mark.parametrize("count", range(1, DECK_CARD_COUNT_MAX_DOTS + 1))
def test_count_strip_draws_one_dot_per_copy(count: int) -> None:
    """#987: the count is a stack of filled dots -- one per copy."""
    _strip, dots = _count_dots(count)
    assert len(dots) == count


def test_count_dots_are_stacked_without_overlapping() -> None:
    """Dots sit in one vertical column, bottom-anchored, and never touch."""
    _strip, dots = _count_dots(DECK_CARD_COUNT_MAX_DOTS)
    assert len({dot.x for dot in dots}) == 1, "the dots are not in a single column"
    ordered = sorted(dots, key=lambda dot: dot.y)
    for upper, lower in zip(ordered, ordered[1:]):
        assert upper.y + upper.height < lower.y, "adjacent count dots overlap"


def test_count_strip_stays_inside_the_card() -> None:
    """The strip is a *strip*: it never draws off the card's left edge or its top."""
    for count in range(1, DECK_CARD_COUNT_MAX_DOTS + 1):
        strip, dots = _count_dots(count)
        assert strip.x >= 0
        assert strip.x + strip.width <= DECK_CARD_WIDTH
        assert strip.y >= 0
        assert strip.width < DECK_CARD_WIDTH * 0.15, "the count strip is no longer a thin strip"
        for dot in dots:
            assert strip.Contains(dot), "a count dot is drawn outside its strip"


def test_tallest_count_stack_clears_the_card_title_band() -> None:
    """H1's rule, re-applied to the dots: a full stack must stay below the title.

    This is what caps :data:`DECK_CARD_COUNT_MAX_DOTS` -- the stack grows upward
    from the art box's lower edge, so raising the cap is what would push it back
    into the card name.
    """
    strip, _dots = _count_dots(DECK_CARD_COUNT_MAX_DOTS)
    assert strip.y > DECK_CARD_HEIGHT * _TITLE_BAND_BOTTOM_FRACTION


def test_count_strip_does_not_collide_with_the_action_chips() -> None:
    """The +/-/x chips appear under the pointer; the strip must clear them."""
    strip, _dots = _count_dots(DECK_CARD_COUNT_MAX_DOTS)
    _btn_w, btn_h = DECK_CARD_ACTION_BUTTON_SIZE
    chips_top = DECK_CARD_HEIGHT - DECK_CARD_BUTTON_MARGIN - btn_h
    assert strip.y + strip.height <= chips_top


def test_dot_column_stays_inside_the_strips_round_caps() -> None:
    """The dots are blitted as one opaque rectangle inside the rounded strip.

    That blit is what keeps a repaint cheap (an alpha ``DrawBitmap`` into the
    grid's canvas bitmap measured ~5ms *per card*), but it only works while the
    rectangle's corners sit inside the strip's round caps -- otherwise it squares
    them off. This is the geometric condition the padding/diameter constants have
    to keep satisfying.
    """
    from math import hypot

    from utils.constants import DECK_CARD_COUNT_STRIP_PADDING

    pad = DECK_CARD_COUNT_STRIP_PADDING
    strip, _dots = _count_dots(DECK_CARD_COUNT_MAX_DOTS)
    radius = strip.width / 2
    cap_centre = (strip.x + radius, strip.y + radius)
    for corner_x in (strip.x + pad, strip.x + strip.width - pad):
        distance = hypot(corner_x - cap_centre[0], strip.y + pad - cap_centre[1])
        assert distance <= radius, "the dot column's corners poke out of the strip's cap"


def test_high_counts_degrade_to_the_numeral_instead_of_overflowing() -> None:
    """A 20x Dragon's Approach is a numeral, not twenty dots stacked off the card."""
    from widgets.panels.card_table_panel.grid_layout import count_fits_in_dots

    assert count_fits_in_dots(DECK_CARD_COUNT_MAX_DOTS)
    assert not count_fits_in_dots(DECK_CARD_COUNT_MAX_DOTS + 1)
    assert not count_fits_in_dots(20)
    # Nothing to draw for a zero/negative count, and no numeral either.
    assert not count_fits_in_dots(0)
    _strip, dots = _count_dots(0)
    assert dots == []


# ---------------------------------------------------------------- C7 / C8

#: Strings that legitimately end in a colon: prompts and sentence lead-ins, not
#: labels sitting beside a field. C7 is about *form field labels* only.
_COLON_ALLOWED = {
    "deck_results.recent_activity",
    "tabs.view.printing.date_prompt",
    "guide.record.mode_prompt",
    "guide.record.coverage_prompt",
}


@pytest.mark.parametrize("locale", sorted(SUPPORTED_LOCALES))
def test_no_form_field_label_ends_in_a_colon(locale: str) -> None:
    """C7: ``Format`` in three windows and ``Format:`` in two others."""
    offenders = sorted(
        key
        for key, value in MESSAGES[locale].items()
        if value.rstrip().endswith(":") and key not in _COLON_ALLOWED
    )
    assert offenders == [], f"{locale}: label punctuation drifted again: {offenders}"


@pytest.mark.parametrize("locale", sorted(SUPPORTED_LOCALES))
def test_window_titles_do_not_carry_a_product_prefix(locale: str) -> None:
    """C8: three windows were ``MTGO X`` / ``X MTGO`` and four were plain ``X``.

    ``MTGO`` is the game's name, not this app's ("MTGO Tools"), and the Tools
    menu entry that opens each of these windows names it without the token.

    The app's *own* name is removed before the check rather than allowlisted by
    key. That is the distinction C8 actually draws -- "MTGO Match History" claims
    to be one of the game's windows, "MTGO Tools" is what this program is called
    -- and expressing it as an exempt key would have made the next window named
    after the app fail for no reason. Phase 9's splash frame was that window.
    """
    product = MESSAGES[locale]["app.title.main_frame"]
    titles = {k: v for k, v in MESSAGES[locale].items() if k.startswith("window.title.")}
    assert titles, "window.title.* catalogue vanished"
    offenders = sorted(
        k for k, v in titles.items() if re.search(r"\bMTGO\b", v.replace(product, ""))
    )
    assert offenders == [], f"{locale}: window titles re-grew the MTGO token: {offenders}"


def test_window_titles_agree_with_the_menu_entries_that_open_them() -> None:
    """The Tools menu and the window it opens should say the same thing."""
    for menu_key, window_key in (
        ("toolbar.opponent_tracker", "window.title.opponent_tracker"),
        ("toolbar.timer_alert", "window.title.timer_alert"),
        ("toolbar.match_history", "window.title.match_history"),
        ("toolbar.metagame_analysis", "window.title.metagame_analysis"),
        ("toolbar.top_cards", "window.title.top_cards"),
    ):
        for locale in SUPPORTED_LOCALES:
            assert (
                MESSAGES[locale][menu_key] == MESSAGES[locale][window_key]
            ), f"{locale}: {menu_key} != {window_key}"


# ---------------------------------------------------------------- C5 / C6


@pytest.mark.parametrize("locale", sorted(SUPPORTED_LOCALES))
def test_empty_state_copy_does_not_name_a_button(locale: str) -> None:
    """C6: ``notes.empty`` said ``click "Add"``; the button is ``+ Add Note``.

    An empty state carries its own CTA now, so the copy has no business naming
    one -- and naming one is exactly how it went stale.
    """
    for key in ("notes.empty", "guide.empty", "builder.empty.no_results"):
        value = MESSAGES[locale][key]
        assert (
            "“" not in value and '"' not in value
        ), f"{locale}: {key} quotes a control name again: {value!r}"


def test_no_hand_rolled_empty_state_panels_remain() -> None:
    """C5: five surfaces had five different empty states. There is one component.

    Guards the pattern that produced them -- a panel whose only content is a
    centred ``empty``-named StaticText -- by forbidding the identifier that every
    one of them used outside the component itself.
    """
    root = Path(__file__).resolve().parent.parent / "widgets"
    offenders = []
    for path in root.rglob("*.py"):
        if path.name == "empty_state.py":
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"^\s*empty_(?:sizer|label)\s*=", text, re.M):
            offenders.append(str(path.relative_to(root)))
    assert offenders == [], f"hand-rolled empty states are back in: {offenders}"


# ---------------------------------------------------------------- C4


def test_no_glyph_is_used_as_a_separator() -> None:
    """C4: ``wx.StaticText(label="|")``. A rule is chrome; a glyph is content."""
    root = Path(__file__).resolve().parent.parent / "widgets"
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        # A real construction always passes a parent first; the prose in the
        # docstrings that record this fix does not, so it is not an offender.
        if re.search(
            r"""StaticText\(\s*\w[\w.]*\s*,[^)]*label=["']\|["']""",
            path.read_text(encoding="utf-8"),
        )
    ]
    assert offenders == [], f"a separator glyph is back in: {offenders}"
