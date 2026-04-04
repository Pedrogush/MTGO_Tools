"""Shared UI layout constants."""

APP_FRAME_SIZE = (1480, 860)
APP_FRAME_MIN_SIZE = (1480, 760)
APP_FRAME_SUMMARY_MIN_HEIGHT = 90

# Research panel — archetype list height for ~3 visible items (px)
ARCHETYPE_LIST_ITEM_HEIGHT = 22
ARCHETYPE_LIST_VISIBLE_ITEMS = 3
ARCHETYPE_LIST_HEIGHT = ARCHETYPE_LIST_ITEM_HEIGHT * ARCHETYPE_LIST_VISIBLE_ITEMS

PADDING_XS = 2
PADDING_SM = 4
PADDING_MD = 6
PADDING_LG = 10
PADDING_XL = 12
PADDING_BASE = 8

# Deck workspace card display — font sizes (pt)
DECK_CARD_BASE_FONT_SIZE = 11  # font size for the quantity badge label
DECK_CARD_NAME_FONT_SIZE = 10  # font size for the card name in the placeholder template

# Deck Stats Panel — font sizes (px)
STATS_FONT_SIZE_BODY = 12
STATS_FONT_SIZE_LABEL = 11
STATS_FONT_SIZE_SMALL = 10
STATS_FONT_SIZE_VALUE = 15

# Deck Stats Panel — layout
STATS_CHART_BORDER_RADIUS = 6
STATS_BAR_BORDER_RADIUS = 3
STATS_VBAR_XAXIS_PADDING_BOTTOM = 22  # room for x-axis labels (icons up to 18px tall)
STATS_VBAR_XAXIS_BOTTOM_OFFSET = -22  # matches STATS_VBAR_XAXIS_PADDING_BOTTOM (negative)
STATS_HBAR_ROW_HEIGHT = 20
STATS_HBAR_LABEL_WIDTH = 82
STATS_HBAR_TRACK_HEIGHT = 12
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
GUIDE_COL_CARDS_WIDTH = 150  # width of Play/Draw In/Out card-list columns (px)
GUIDE_COL_NOTES_WIDTH = 180  # width of Notes column (px)

# Deck Builder Panel — search results list layout
BUILDER_NAME_COL_MIN_WIDTH = 40  # minimum width of the Name column (px)
BUILDER_NAME_COL_DEFAULT_WIDTH = 180  # initial width of the Name column (px)
BUILDER_FORMATS_GRID_COLS = 3  # number of columns in the formats FlexGridSizer
BUILDER_FORMATS_GRID_HGAP = 8  # horizontal gap between format checkbox cells (px)
BUILDER_MANA_ALL_BTN_SIZE = (52, 28)  # size of the "All" mana keyboard button (px)

# Compact Sideboard Panel — button sizing
COMPACT_SIDEBOARD_TOGGLE_BTN_SIZE = (70, 22)  # size of the On Play/On Draw toggle button (px)

# Opponent Tracker — hypergeometric calculator panel layout
CALC_SECTION_PADDING = 6  # uniform padding around calculator sections
CALC_GRID_ROWS = 4  # rows in the input FlexGridSizer
CALC_GRID_COLS = 2  # columns in the input FlexGridSizer
CALC_GRID_VGAP = 4  # vertical gap between grid cells
CALC_GRID_HGAP = 8  # horizontal gap between grid cells
CALC_SPIN_WIDTH = 70  # width of SpinCtrl widgets (px); -1 = default height
CALC_PRESET_BUTTON_WIDTH = 55  # width of preset buttons (px)
CALC_PRESET_BUTTON_HEIGHT = 24  # height of preset buttons (px)
CALC_PRESET_BUTTON_SPACING = 4  # right-margin between preset buttons
CALC_ACTION_BUTTON_SPACING = 8  # right-margin between action buttons
