"""Shared UI colors.

Every value here now comes from :mod:`utils.constants.theme`, which is the design
system's single source of truth. The names below are kept as **aliases** so the
~17 modules that import them keep working unchanged; they are deprecated and will
be removed once phases 1-4 have migrated their call sites onto the semantic tokens.

Import ``utils.constants.theme`` directly in new code.
"""

from utils.constants.theme import (
    ACCENT_PRIMARY,
    SUCCESS_SURFACE,
    SURFACE_ALT,
    SURFACE_BASE,
    SURFACE_PANEL,
    TEXT_ON_FILL,
    TEXT_PLACEHOLDER,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING_TEXT,
)

# --- Deprecated aliases: same value, new name lives in theme.py ---------------
SUBDUED_TEXT = TEXT_SECONDARY  # -> TEXT_SECONDARY
DARK_BG = SURFACE_BASE  # -> SURFACE_BASE
DARK_PANEL = SURFACE_PANEL  # -> SURFACE_PANEL
DARK_ALT = SURFACE_ALT  # -> SURFACE_ALT
DARK_ACCENT = ACCENT_PRIMARY  # -> ACCENT_PRIMARY
LIGHT_TEXT = TEXT_PRIMARY  # -> TEXT_PRIMARY

# --- Deprecated aliases whose *value* changes, to fix a measured defect -------
# HINT_TEXT was (87, 87, 87): 1.89:1 against the field background it is drawn on
# (widgets/panels/mana_rich_text_ctrl/frame.py:119), i.e. effectively invisible.
# Repointing the alias fixes it in place with no call-site change. 5.17:1 on the
# field surface, 4.60:1 on the lightest surface in the scale.
HINT_TEXT = TEXT_PLACEHOLDER  # -> TEXT_PLACEHOLDER

# Deck workspace card display colors
DECK_CARD_ACTION_BUTTON_FG = TEXT_ON_FILL  # -> TEXT_ON_FILL (same value)
DECK_CARD_IMAGE_BG = (0, 0, 0)  # black fill used when centering card images; not a theme token

# Sideboard Guide Panel — inline warning label.
WARNING_LABEL_COLOR = WARNING_TEXT  # -> WARNING_TEXT (was (255, 165, 0); 8.35:1 on panel)
# FLEX_SLOT_HIGHLIGHT_COLOR was (55, 70, 45); the flex-slot rows in the sideboard
# card selector are the only remaining call site.
FLEX_SLOT_HIGHLIGHT_COLOR = SUCCESS_SURFACE  # -> SUCCESS_SURFACE
#
# Phase 2 deleted three constants that used to live here:
#   CALC_BUTTON_GREEN     -> stylize_button(kind="success")   (5.49:1 -> 7.25:1)
#   PIN_BUTTON_COLOR      -> stylize_button(kind="secondary") (was the contrast
#                            suite's one documented xfail, 4.15:1)
#   FLEX_SLOT_BUTTON_COLOR-> stylize_button(kind="success")
# Every one of them was a bespoke hue on exactly one button. The button system is
# where a button's colour is decided now, so a hex here would have no way to be
# right.
