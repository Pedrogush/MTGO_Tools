"""Card image display sizing and animation constants."""

# Deck Builder Panel — mana cost column icon rendering
BUILDER_MANA_ROW_HEIGHT = 26  # row image height; matches ManaIconFactory default icon_size
BUILDER_MANA_CANVAS_WIDTH = 200  # canvas width; matches the "Mana Cost" column width
BUILDER_MANA_ICON_GAP = 1  # pixels between adjacent mana icons in the canvas

# ManaIconFactory — icon sizing and rendering
MANA_ICON_DEFAULT_SIZE = 26  # default icon_size argument for ManaIconFactory
MANA_ICON_MIN_SIZE = 8  # minimum clamped icon size (px)
MANA_ICON_SPAN_PADDING = 2  # extra px added to icon_size to compute the icon span
MANA_ICON_PANEL_HEIGHT_PADDING = 6  # extra px added to icon_size for panel min-height
MANA_COST_BITMAP_GAP = 2  # gap (px) between adjacent bitmaps in bitmap_for_cost
MANA_GLYPH_FONT_SIZE_BASE = 13  # base point size (before render-scale multiply) for glyph font
MANA_GLYPH_FONT_SIZE_MIN = 6  # minimum point size when scaling a glyph font down
MANA_ICON_BLUR_RADIUS = 1  # blur radius applied to rendered icon before downscale
MANA_TEXT_DARK_RGB = 20  # RGB component for dark text drawn on mana icons
MANA_OUTLINE_DARK_RGB = 25  # RGB component for the dark outline ring around mana icons

CARD_IMAGE_DISPLAY_WIDTH = 260
CARD_IMAGE_DISPLAY_HEIGHT = 360
CARD_IMAGE_CORNER_RADIUS = 12
CARD_IMAGE_FLIP_ICON_SIZE = 32
CARD_IMAGE_FLIP_ICON_MARGIN = 10
CARD_IMAGE_ANIMATION_INTERVAL_MS = 16
CARD_IMAGE_ANIMATION_ALPHA_STEP = 0.15
CARD_IMAGE_PLACEHOLDER_INSET = 5
CARD_IMAGE_FLIP_ICON_TEXT_SCALE = 0.65
CARD_IMAGE_NAV_BUTTON_SIZE = (38, 30)
CARD_IMAGE_PRINTING_LABEL_MIN_WIDTH = 80
CARD_IMAGE_TEXT_MIN_HEIGHT = 120
CARD_IMAGE_COST_MIN_HEIGHT = 36

# Deck workspace card display sizing
DECK_CARD_WIDTH = 160
DECK_CARD_HEIGHT = 224
DECK_CARD_CORNER_RADIUS = 10
DECK_CARD_BADGE_PADDING = 4
DECK_CARD_BUTTON_MARGIN = 6
DECK_CARD_ACTION_BUTTON_SIZE = (28, 28)  # min/max size of +/−/× buttons (px)
DECK_CARD_TEMPLATE_BORDER_WIDTH = 2  # pen width for the template placeholder border
DECK_CARD_TEMPLATE_BORDER_ALPHA = 120  # alpha channel for the template placeholder border
DECK_CARD_ACTIVE_BORDER_WIDTH = 3  # pen width for the active-selection highlight border

# Deck Stats Panel — mana SVG icon sizing
STATS_MANA_SVG_SOURCE_SIZE = 32  # original width/height in SVG files
STATS_MANA_SVG_DISPLAY_SIZE = 18  # rendered width/height in the stats HTML

# Unit conversion for display formatting
BYTES_PER_MB = 1024 * 1024  # bytes in one mebibyte; used for human-readable size labels
