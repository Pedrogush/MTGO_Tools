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

# F3/F7 made the deck-workspace header row wider: it gained a "View" caption, a
# pile-sort button labelled with the current grouping key rather than "...", and
# a caret on the printing button. Measured in pt-BR at the window's 1200px
# minimum with the inspector collapsed, the row then wanted 551px in a 506px
# panel and clipped the printing button to 14px. The count label is the one item
# in the row that degrades gracefully -- its leading number survives an ellipsis,
# and a control that gets cut off does not -- so it is the flexible one, floored
# here rather than at its natural ~111px.
DECK_COUNT_LABEL_MIN_WIDTH = 48

# §4.5. The left column is added to the root sizer with **proportion 0**, so it
# is always exactly its own minimum width -- at every window size, not only at
# the floor. Every pixel of that minimum is therefore a pixel the deck workspace
# never gets, at 1200 and at 2560 alike.
#
# Attributed by ablation (phase 3b's lesson: a max() can only be attributed by
# removing terms, never by summing them): 100% of the research panel's 564px
# minimum came from the Result row. `-` (45) + `Placement` (95) + a value field
# whose wx.TextCtrl best-width floor is 110 make 266, and the row pairs that
# against the player-name field at equal proportion, so wxBoxSizer's
# proportional CalcMin doubles the wider column: 2 x 266 = 532 of the 564.
# Ablating the value field alone gave back 102px and handed the binding term to
# the player-name field's own 110px floor.
#
# The field holds a placement (`8`) or a win count (`5`) -- one or two digits.
# 110 is wxMSW's floor for any wx.TextCtrl regardless of content, the same kind
# of native floor phase 3 found behind wx.Button's 75x23; it is not a measure of
# what this field has to show. 64 is four digits at the 10pt base plus the
# InputFrame's 2 DIP ring on each side, on the 4px grid.
RESEARCH_VALUE_FIELD_MIN_WIDTH = 64

# Phase 3b left phase 8 an explicit item: **bound the inspector's minimum
# width**. The both-panels-expanded floor was inspector-*content* dependent --
# the Card panel's minimum measured 267px with one card loaded and 350px with
# another, giving a 1393 vs 1433 window floor for the same layout, and the floor
# that actually got enforced was whichever one happened to be measured at
# restore time. A snapshot, correct when taken and not continuously true.
#
# The art block above the tabs (CardInspectorPanel) pins its own width with
# SetMinSize *and* SetMaxSize, so it has always been bounded. Only the tabs
# under it were not: a wx.StaticText reports its full single line as its best
# width, so the Stats tab's card name / format / archetype headers set the
# column's width from their content. Two changes bound it:
#   * those three labels now re-wrap to the panel (card_panel.set_flowing_label),
#     so nothing inside the tabs reports an unbounded best width, and
#   * the tab area is given an explicit min size on **both** axes. wxWidgets'
#     GetEffectiveMinSize consults GetBestSize only for the components of
#     SetMinSize left at -1, so a min size with a real width in it is the one
#     API that stops best size leaking through at all.
# The width is not spelled out here: it is read from the art block's own pinned
# width at construction, so the two halves of the column cannot drift apart.
CARD_PANEL_MIN_HEIGHT = 240
# The Oracle tab's HtmlWindow floor, and it has to be derived from the number
# above rather than picked. The tab area is CARD_PANEL_MIN_HEIGHT less the
# panel's own SPACE_SM ring, less the FlatNotebook's ~27px tab strip, less the
# page's SPACE_SM ring: 240 - 16 - 27 - 16 = 181. The hand-set 200 was 19px over
# that, so at the inspector column's own floor the notebook was 19px short of
# what its first page claimed to need -- silently, since a wxBoxSizer with one
# item just gives it everything there is. Raising CARD_PANEL_MIN_HEIGHT to
# match would have put those 19px straight onto the window's minimum height,
# which is the one dimension the inspector column already sets.
CARD_ORACLE_MIN_HEIGHT = 180

# F2: the Deck Research / Deck Builder mode switch (widgets.mode_switch). Taller
# than VIEW_TOGGLE_HEIGHT because it is the only control on the left panel that
# changes what the whole panel is, and it is the first thing on that panel; the
# view toggles are chrome inside a region the mode switch selects.
MODE_SWITCH_HEIGHT = 30
MODE_SWITCH_PADDING_X = 14

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

# S5. The two defects the review filed as "the last row is sliced in half by the
# pane edge with no fade, no partial-row suppression and no scroll affordance"
# are answered here, and *not* by quantising the pane (measured in phase 8: at
# the 1200x680 floor the mainboard grid's viewport is 285px against a 232px row,
# so rounding it down would spend up to 231px of the primary content region, and
# the 118px sideboard pane would round to an empty pane).
#
# CARD_VIEW_EDGE_FADE_PX: how tall the fade at a clipped edge is. It is drawn
# only on an edge that actually has content past it, so it doubles as the
# "there is more this way" affordance the review asked for.
CARD_VIEW_EDGE_FADE_PX = 24

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

# Deck workspace table view -- the minimum the *view* reports, not the size it
# renders at.
#
# ``wx.grid.Grid.GetBestSize()`` returns the grid's whole scrollable content:
# every column's width and every row's height, for all 30-odd rows of a
# decklist. It is a scrolling control, so that number is not a minimum in any
# useful sense -- and it propagates. The three views share a wx.Simplebook,
# whose CalcMin is the max over **all** pages including hidden ones, so once the
# table view has been populated even once the whole deck workspace reports it,
# and the workspace's minimum reaches the frame's root sizer.
#
# Measured in phase 8 with a 60-card deck loaded: visiting Table view once and
# then toggling any side panel took the frame's enforced minimum height from
# **882 to 1461px** -- taller than the display on any laptop the app claims to
# target, and the window can then never be made smaller again. The view mode is
# persisted per zone, so leaving the app in Table view reproduced it on the next
# launch, via the _apply_min_size that _restore_session_state already schedules.
# The grid and pile views were never affected: neither has a child window, so
# wx reports 1x1 for them and the panel's own floor governs.
#
# Height is the header plus three rows; width is the four unshrinkable columns
# (_fit_to_width in table_columns.py shrinks Type/Text/Name and drops the oracle
# text column entirely below _COLLAPSE_TEXT_BELOW, so the table stays usable
# well under its natural width).
DECK_TABLE_VIEW_MIN_SIZE = (240, 96)

# The deck workspace's mainboard/sideboard splitter: the smallest either pane
# may be dragged (or laid out) to.
#
# It was a bare 80, and 80 is below what a CardTablePanel's own controls need.
# Measured at the window's floor: the sideboard pane was 84px of which 30 was
# its header row, leaving 54px of a 232px card cell -- less than a quarter of one
# card, which is the "the whole sideboard strip is cut in half by the pane edge"
# the review recorded as S5. In table view the panel's minimum is 126 and the
# pane was simply short of it.
#
# 148 = a two-row header (the row wraps in pt-BR at this width; see
# CardTablePanelToolbarMixin._reflow_header) + the 4px gap under it +
# DECK_TABLE_VIEW_MIN_SIZE's 96px of grid. It is the panel's own content
# minimum, not a comfortable browsing height: a full card row is 232px and two
# of those plus the sash do not fit the 680px window floor, so how the *grid*
# views should treat the leftover strip is a separate question from this one.
DECK_ZONE_MIN_PANE_HEIGHT = 148

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
# Phase 4 logged this for phase 8: at 1200x680 with the advanced filters
# expanded, the builder's results list collapsed to **zero** height and
# "Showing N cards." fell below the window edge. The panel is one long vertical
# wx.BoxSizer in which everything except the results list has proportion 0, so
# when the fixed items alone exceed the client height wxBoxSizer hands the
# proportional item a negative share, clamps it at 0 -- and *still* lays out the
# items after it, off the bottom of the pane. It is the vertical twin of the
# horizontal row overflow phase 7 measured, and just as silent.
#
# The panel now scrolls (see DeckBuilderPanel._build_ui). A wxScrolled with a
# sizer lays out to max(client, virtual): when the pane is tall enough there is
# no scrollbar and the results list expands exactly as before, and when it is
# not, the list keeps this floor and the rest is reachable by scrolling instead
# of being drawn past the edge. Six rows at GRID_ROW_HEIGHT plus the header.
BUILDER_RESULTS_MIN_HEIGHT = 168
# Pixels per scroll unit for that scroller. Matches the deck notes panel, the
# other place in the app where a form-shaped column scrolls.
BUILDER_SCROLL_RATE_Y = 12

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
