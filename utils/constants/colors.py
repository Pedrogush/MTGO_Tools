"""Shared UI colors.

Every value here now comes from :mod:`utils.constants.theme`, which is the design
system's single source of truth. The names below are kept as **aliases** so the
~17 modules that import them keep working unchanged; they are deprecated and will
be removed once phases 1-4 have migrated their call sites onto the semantic tokens.

Import ``utils.constants.theme`` directly in new code.
"""

from utils.constants.theme import (
    ACCENT_PRIMARY,
    SUCCESS_FILL,
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

# Opponent Tracker — calculator button accent color.
# NOT aliased to SUCCESS_FILL: its only call site
# (identify_opponent/frame/calculator_panel.py:188-189) pairs it with LIGHT_TEXT,
# which measures 6.49:1 on this deep green but only 2.66:1 on SUCCESS_FILL. The
# semantic fills in theme.py are light fills carrying TEXT_ON_FILL, matching the
# app's primary-button idiom. Phase 2 should convert that button to
# stylize_button(kind="success") and delete this constant; remapping it here would
# break the contrast the call site currently has.
CALC_BUTTON_GREEN = "#2a6b2a"

# Sideboard Guide Panel — button and label colors.
# PIN_BUTTON_COLOR is left alone: "pin for tracker" is not success/warning/danger,
# and the design system has no purple. Phase 2 should make it a secondary button
# rather than give it a bespoke hue.
PIN_BUTTON_COLOR = (140, 90, 210)  # purple accent for the "Pin for Tracker" button
WARNING_LABEL_COLOR = WARNING_TEXT  # -> WARNING_TEXT (was (255, 165, 0); 8.35:1 on panel)
# FLEX_SLOT_BUTTON_COLOR was (60, 130, 80). Its call site
# (sideboard_guide_panel/frame.py:162-163) calls stylize_button() first, so the
# foreground is TEXT_ON_FILL: that measured 4.14:1 on the old green and measures
# 7.25:1 on SUCCESS_FILL. Aliasing both fixes the contrast and removes a hue.
FLEX_SLOT_BUTTON_COLOR = SUCCESS_FILL  # -> SUCCESS_FILL
FLEX_SLOT_HIGHLIGHT_COLOR = SUCCESS_SURFACE  # -> SUCCESS_SURFACE (was (55, 70, 45))
