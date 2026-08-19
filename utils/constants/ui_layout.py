"""Shared UI layout constants."""

# Re-exported so `from utils.constants import SPACE_MD` works alongside the colour
# tokens. theme.py is the single source of truth for the 4px spacing scale.
from utils.constants.theme import SPACE_GRID as SPACE_GRID
from utils.constants.theme import SPACE_LG as SPACE_LG
from utils.constants.theme import SPACE_MD as SPACE_MD
from utils.constants.theme import SPACE_SM as SPACE_SM
from utils.constants.theme import SPACE_XL as SPACE_XL
from utils.constants.theme import SPACE_XS as SPACE_XS
from utils.constants.theme import css_font_size

# Preferred size on first launch / on displays large enough to host it. On a
# smaller display the frame auto-maximizes instead (see _apply_window_preferences).
APP_FRAME_SIZE = (1480, 860)
# Hard floor for the window. Sized to fit a budget 13"–14" laptop: such panels
# are commonly 1366x768 (and some 1280x800), whose taskbar+title-bar leave
# ~1366x720 / ~1280x752 of usable area. 1200x680 clears both with margin, so the
# window can shrink to fit rather than being clipped. The collapsible side panels
# (left sidebar + card inspector) and the 2-column grid floor are what let the
# real content minimum drop to this size; see _apply_min_size, which raises the
# floor dynamically when a tall panel (the inspector) is expanded.
# Measured against this floor in phase 3b: the window meets it with the card
# inspector collapsed (content floor 1067x562) and misses it with the inspector
# expanded (1393x902, inspector-content dependent). The comment above described
# an intent, not a measurement -- the real floor was 1310 before phase 3 and 1381
# after it. Reducing the expanded case below 1200 is phase 8's column work.
APP_FRAME_MIN_SIZE = (1200, 680)
APP_FRAME_SUMMARY_MIN_HEIGHT = 90

# Width (px) of the thin gutter buttons that collapse/expand the left sidebar
# and the right card-inspector column.
COLLAPSE_TOGGLE_WIDTH = 16

# C5/C6: the widest an empty state's message is allowed to get before it wraps.
# The Sideboard Guide's empty state is a ~1600x850 void with a 300px cluster in
# it and Deck Notes' is nearly as large, so an unconstrained wx.StaticText there
# sets a line ~180 characters long. This is a measure-based cap, not a panel
# fraction, because the readable-line-length problem is the same at 1481px and
# at 2560px.
EMPTY_STATE_MAX_WIDTH = 360

# F8: width (px) reserved for the right-hand status label in the Match History,
# Metagame Analysis and Top Cards toolbars. All three were a proportion-0
# wx.StaticText after an AddStretchSpacer(1): the spacer took every spare pixel,
# the label took its natural width on top of that, and the overflow ran off the
# window edge mid-word ("Failed to", "Loade", "To"). The label takes the spare
# space itself now (proportion 1, right-aligned, ST_ELLIPSIZE_END) and this is
# the floor the toolbar reserves for it before the controls to its left start
# losing room.
STATUS_LABEL_MIN_WIDTH = 120

# F4: the deck workspace's compact header buttons -- the Grid/Table/Pile
# toggles, the pile-sort "..." and the printing "Art" button. All five are
# wx.BU_EXACTFIT, which is the only way past wx.Button's 75x23 best-size floor
# but sizes them to the text extent plus ~2px: measured 30x18 before phase 4.
# See widgets.stylize.size_compact_button for why BU_EXACTFIT has to stay.
VIEW_TOGGLE_HEIGHT = 26
VIEW_TOGGLE_PADDING_X = 10

# Width (px) of the status bar's right-hand field, which holds the "update
# available" note (issue #142) and is empty the rest of the time. Fixed rather
# than proportional so the status message on the left keeps all remaining width.
STATUS_BAR_UPDATE_FIELD_WIDTH = 200

# ARCHETYPE_LIST_ITEM_HEIGHT / _VISIBLE_ITEMS / _HEIGHT lived here until phase 3.
# They were dead: the archetype selector is a wx.ComboBox and nothing in widgets/
# referenced them. Phase 0 costed ARCHETYPE_LIST_ITEM_HEIGHT=22 as "survives at
# 10pt, overflows at 11pt"; it does neither, because it was never applied to a
# widget. Deleted rather than re-tuned.

# --- Spacing --------------------------------------------------------------
# SPACE_* (the 4px scale) is re-exported from theme.py at the top of this module
# and is now the app's only spacing vocabulary.
#
# PADDING_XS/SM/MD/BASE/LG/XL = 2/4/6/8/10/12 lived here until phase 3. They were
# a linear 2px scale, and a 2px difference is below the threshold at which a
# viewer reads two gaps as *different* gaps -- so proximity, the strongest
# grouping cue available, could not group anything. Phase 3 migrated every call
# site onto SPACE_* with this mapping:
#
#     PADDING_XS   2  -> SPACE_XS   4
#     PADDING_SM   4  -> SPACE_XS   4
#     PADDING_MD   6  -> SPACE_SM   8
#     PADDING_BASE 8  -> SPACE_SM   8
#     PADDING_LG  10  -> SPACE_MD  16
#     PADDING_XL  12  -> SPACE_MD  16
#
# Six levels collapse to three because only three were ever distinguishable.
#
# The 129 raw literals in .Add() calls (2/3/4/5/6/8/10/12/15/16/20; an explicit 0
# is left alone, since "no gap" is on the grid and naming it buys nothing) snap to
# the nearest grid value rather than to a semantic level, because a bare literal
# carries no recoverable intent:
#
#     2, 3, 4, 5   -> SPACE_XS   4
#     6, 8, 10     -> SPACE_SM   8
#     12, 15, 16   -> SPACE_MD  16
#     20           -> SPACE_LG  24
#
# Note 10 -> 8, not 16, even though PADDING_LG (also 10) goes to 16. The constant
# named a window-edge margin; the literal was almost always the gap between two
# adjacent form rows. Rounding those up to 16 grew the Export Diagnostics dialog's
# content from 343px to 433px inside a 380px window -- measured, then corrected.

# DECK_CARD_BASE_FONT_SIZE / DECK_CARD_NAME_FONT_SIZE lived here until phase 3.
# They were hard-coded point sizes for text the card grid paints itself with
# dc.SetFont(), which font inheritance cannot reach -- so the own-drawn surfaces
# were the only part of the app whose type did not move with the base font. They
# now call widgets.stylize.type_font(level), which derives from the type ladder.

# Deck workspace card views (grid + pile) — scrolling. Shared so both views
# behave identically. A 1px scroll rate gives the scrollbar thumb single-pixel
# granularity; the mouse-wheel handler (utils in card_table_panel/scrolling.py)
# then scrolls CARD_VIEW_WHEEL_LINES_PER_NOTCH "lines" of CARD_VIEW_WHEEL_LINE_PX
# each per notch, matching what wx's built-in handler did at the old 20px rate.
CARD_VIEW_SCROLL_RATE = 1  # pixels per scroll unit (fine scrollbar granularity)
CARD_VIEW_WHEEL_LINE_PX = 20  # pixels scrolled per wheel "line"
CARD_VIEW_WHEEL_LINES_PER_NOTCH = 3  # fallback when the OS lines-per-action is unknown

# Top Cards viewer. Column widths are measured against the widest realistic
# value and the (now expanded) header, at the 10pt base. "Copies" is the sort
# key and is deliberately wider than the columns beside it -- the review's
# "near-uniform column widths, so Copies gets the same weight as SB avg-K".
TOP_CARDS_FRAME_SIZE = (1400, 740)
TOP_CARDS_COL_RANK_WIDTH = 44
TOP_CARDS_COL_CARD_WIDTH = 220
TOP_CARDS_COL_COPIES_WIDTH = 88
TOP_CARDS_COL_DECKS_WIDTH = 84
TOP_CARDS_COL_AVG_WIDTH = 104
TOP_CARDS_COL_ARCHETYPES_WIDTH = 136
# Wide enough for the longest comma-joined legality list the data produces
# ("Legacy, Modern, Pauper, Pioneer, Standard, Vintage"), so it no longer
# truncates mid-word -- and fixed, so it can no longer autosize past the window
# edge the way LIST_AUTOSIZE did.
TOP_CARDS_COL_FORMATS_WIDTH = 264

# Archetype summary strip (H4). The height was an unnamed 62; the sparkline
# needs room for a value row, seven bars and a day label under each.
ARCHETYPE_SUMMARY_DAYS = 7
ARCHETYPE_SUMMARY_HEIGHT = 68
ARCHETYPE_SPARK_WIDTH = 168

# Own-drawn data grids (widgets/grids/data_grid.py)
GRID_ROW_HEIGHT = 24  # comfortable scan height at the 10pt base
GRID_HEADER_HEIGHT = 42  # two lines of caption text plus breathing room
GRID_CELL_PADDING = 8  # inset between a cell edge and its text, both alignments

# Shared bar-chart geometry (px unless noted). Used by both dialects of
# widgets/charts/bars.py, so the WebView and wxHTML renderings of the same chart
# stay proportionally identical.
CHART_ROW_HEIGHT = 24  # >= the 24px pointer-target floor, and readable at a glance
CHART_BAR_TRACK_HEIGHT = 14
CHART_BAR_RADIUS = 3
CHART_LABEL_COLUMN_PCT = 34  # archetype names; right-aligned against the bars
CHART_VALUE_COLUMN_PCT = 10  # "12.3%" — right-aligned so the digits line up
# A row that exists but rounds to a hairline still has to be visible: length is
# the encoding, and a 0px bar reads as absent rather than small.
CHART_BAR_MIN_WIDTH_PCT = 1.5

# Deck Stats Panel — font sizes (px)
# Derived from the same integer point ladder the wx widgets use rather than
# tabulated. The hand-written values were 12 / 11 / 10 / 15: three of them sat at
# 1.09-1.10x steps, i.e. the panel had its own copy of root cause 3 (no type
# scale). The panel was permanently hidden until phase 5, so this is the first
# time those sizes have been on screen.
STATS_FONT_SIZE_BODY = css_font_size("body")
STATS_FONT_SIZE_LABEL = css_font_size("caption")
#: Same step as LABEL. The old 11/10 pair was a 1.10x difference -- below the
#: perceptual floor for "these are different levels" -- so it is now one level,
#: kept as a separate name because the two call sites mean different things
#: (chart chrome vs. in-bar values) and may diverge again on purpose.
STATS_FONT_SIZE_SMALL = css_font_size("caption")
STATS_FONT_SIZE_VALUE = css_font_size("heading")

# Deck Stats Panel — layout
STATS_CHART_BORDER_RADIUS = 6
STATS_BAR_BORDER_RADIUS = 3
STATS_VBAR_XAXIS_PADDING_BOTTOM = 22  # room for x-axis labels (icons up to 18px tall)
STATS_VBAR_XAXIS_BOTTOM_OFFSET = -22  # matches STATS_VBAR_XAXIS_PADDING_BOTTOM (negative)
STATS_HBAR_ROW_HEIGHT = 20
STATS_HBAR_LABEL_WIDTH = 82
STATS_HBAR_TRACK_HEIGHT = 12
# The bar is the encoding, so it gets floor priority over the label beside it.
STATS_HBAR_TRACK_MIN_WIDTH = 40
STATS_HBAR_COUNT_WIDTH = 28
STATS_HBAR_ZERO_OPACITY = 0.35
STATS_TOOLTIP_Z_INDEX = 999
STATS_TOOLTIP_PADDING = "4px 9px"
STATS_TOOLTIP_BORDER_RADIUS = 4

# Deck Stats Panel — JS tooltip positioning offsets (px)
STATS_TOOLTIP_OFFSET_X = 12
STATS_TOOLTIP_OFFSET_Y = 28
STATS_TOOLTIP_FLIP_OFFSET_X = 8
STATS_TOOLTIP_EDGE_MARGIN = 4
STATS_TOOLTIP_BELOW_OFFSET_Y = 14

# Sideboard Guide Panel — column widths
GUIDE_COL_ARCHETYPE_WIDTH = 150  # width of Archetype column (px)
# A two-card cell ("3x Wrath of God, 2x Path") measures 131px at 9pt and 146px at
# the 10pt base, so 150 went from 19px of headroom to 4px. 168 restores it.
GUIDE_COL_CARDS_WIDTH = 168  # width of Play/Draw In/Out card-list columns (px)
GUIDE_COL_NOTES_WIDTH = 180  # width of Notes column (px)

# Deck Builder Panel — search results list layout
BUILDER_NAME_COL_MIN_WIDTH = 40  # minimum width of the Name column (px)
BUILDER_NAME_COL_DEFAULT_WIDTH = 180  # initial width of the Name column (px)
BUILDER_FORMATS_GRID_COLS = 3  # number of columns in the formats FlexGridSizer
BUILDER_FORMATS_GRID_HGAP = 8  # horizontal gap between format checkbox cells (px)
BUILDER_MANA_ALL_BTN_SIZE = (52, 28)  # size of the "All" mana keyboard button (px)

# Compact Sideboard Panel — button sizing
# "On Play"/"On Draw" measure 51px at the 10pt base and need 75x25 with chrome;
# the old 70x22 clipped on both axes. 80x28 on the 4px grid.
COMPACT_SIDEBOARD_TOGGLE_BTN_SIZE = (80, 28)  # size of the On Play/On Draw toggle button (px)

# Compact radar panel — the Full Decklist / Top Cards view toggle. Was an inline
# (90, 22) literal in compact_radar_panel/frame.py and 3px short of its own label
# at the 10pt base; phase 3's overflow sweep is what found it, not phase 0's list.
COMPACT_RADAR_TOGGLE_BTN_SIZE = (96, 28)

# Opponent Tracker — hypergeometric calculator panel layout
CALC_SECTION_PADDING = 6  # uniform padding around calculator sections
CALC_GRID_ROWS = 4  # rows in the input FlexGridSizer
CALC_GRID_COLS = 2  # columns in the input FlexGridSizer
CALC_GRID_VGAP = 4  # vertical gap between grid cells
CALC_GRID_HGAP = 8  # horizontal gap between grid cells
CALC_SPIN_WIDTH = 70  # width of SpinCtrl widgets (px); -1 = default height
# Re-measured against the running app at the 10pt base (issue #962, phase 3).
# 72x24 was short on BOTH axes, and the width was already short at 9pt: wxMSW
# gives every wx.Button a best size of 75x23 at 9pt and 75x25 at 10pt whatever
# its label, so any fixed size under that floor reports a deficit. "Calculate"
# itself needs 76x25 at 10pt (52px of text + 24px of button chrome), which is
# what actually sets the width. 88x28 clears both and sits on the 4px grid.
CALC_PRESET_BUTTON_WIDTH = 88  # width of preset buttons (px); wide enough for "Calculate"
CALC_PRESET_BUTTON_HEIGHT = 28  # height of preset buttons (px)
CALC_PRESET_BUTTON_SPACING = 4  # right-margin between preset buttons
CALC_ACTION_BUTTON_SPACING = 8  # right-margin between action buttons
