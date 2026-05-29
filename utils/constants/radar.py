"""Radar analysis defaults."""

RADAR_AVG_COPIES_ROUND_DIGITS = 2
RADAR_INCLUSION_RATE_ROUND_DIGITS = 1
RADAR_EXPECTED_COPIES_ROUND_DIGITS = 2
RADAR_MIN_EXPECTED_COPIES_DEFAULT = 0.0
RADAR_MIN_COPY_COUNT = 1

# Opponent Tracker — radar deck analysis limits
RADAR_MAX_DECKS_OPPONENT_TRACKER = 10  # max decks analyzed for opponent radar view

# Concurrency — cache-missing deck downloads are network-bound, so fetch them
# through a bounded thread pool instead of one round trip at a time.
RADAR_MAX_DOWNLOAD_WORKERS = 8  # concurrent deck-text download threads
