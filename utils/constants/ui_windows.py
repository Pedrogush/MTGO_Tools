"""Window sizing constants for auxiliary frames."""

OPPONENT_TRACKER_FRAME_SIZE = (740, 600)
# The old (600, 400) minimum could not fit this window's own contents: the
# headline runs to a line per format (five lines for a player with results in
# four of them) and the calculator pane below it is ~290px of fixed-height
# controls, so at 400px the calculator and the radar were both cut off and the
# preset buttons overlapped each other. This is the smallest size at which
# every section is still whole.
OPPONENT_TRACKER_MIN_SIZE = (620, 600)
OPPONENT_TRACKER_DEFAULT_X_GAP = 8
# Floor for the header labels' wrap width. The real width is measured from the
# frame at runtime (`_header_wrap_width`); this only stops the wrap collapsing
# to nothing while the frame is still being built and has no client size yet.
OPPONENT_TRACKER_LABEL_MIN_WRAP_WIDTH = 240
OPPONENT_TRACKER_SECTION_PADDING = 6
OPPONENT_TRACKER_LEFT_SASH_POS = 280
OPPONENT_TRACKER_RADAR_PANEL_HEIGHT = 160  # px allocated to radar panel in left splitter

# Horizontal split of the tracker's main area. The calculator/radar column
# carries the long strings (archetype names, card lists) and the sideboard
# guide is a handful of lines, so the spare width goes mostly to the left.
OPPONENT_TRACKER_LEFT_COLUMN_PROPORTION = 2
OPPONENT_TRACKER_GUIDE_COLUMN_PROPORTION = 1
OPPONENT_TRACKER_GUIDE_MIN_WIDTH = 220

# Sideboard Guide — Import Options dialog
GUIDE_IMPORT_OPTIONS_DIALOG_WIDTH = 400
GUIDE_IMPORT_OPTIONS_DIALOG_HEIGHT = 150
