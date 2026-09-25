"""Local storage files and logs."""

from utils.constants.paths import CACHE_DIR, CONFIG_DIR, DECK_RECORDS_DIR

# The three documents a person types by hand about their decks: the notes on a
# deck, the cards kept just outside it ("outboard"), and the sideboard guide.
# Siblings of config/ under DECK_RECORDS_DIR rather than children of cache/
# because nothing can recompute them: cache/, logs/ and data/ are swept wholesale
# by the uninstaller ([UninstallDelete] in packaging/installer.iss) and by
# scripts/clear_caches.py, under a promise that what the user made is preserved.
# They were under cache/ until then, which meant an uninstall threw away every
# deck's notes while keeping the .txt file it named as the thing being saved --
# the same hole that moved DECK_HISTORY_DIR and DECK_RECORDS_DIR, on three files
# that audit did not reach.
#
# Why DECK_RECORDS_DIR and not a fourth root of their own: see the argument on
# DECK_RECORDS_DIR in utils/constants/paths.py. In short, three fixed-name files
# are not a tree, and they hold the same kind of thing the records hold.
NOTES_STORE = DECK_RECORDS_DIR / "deck_notes.json"
OUTBOARD_STORE = DECK_RECORDS_DIR / "deck_outboard.json"
GUIDE_STORE = DECK_RECORDS_DIR / "deck_sbguides.json"
# Where the three were until they moved out of the swept cache/ directory.
# utils/deck_metadata_migration.py moves a shipped build's files off these paths
# on first use; nothing else may read them, and once moved they are gone.
LEGACY_NOTES_STORE = CACHE_DIR / "deck_notes.json"
LEGACY_OUTBOARD_STORE = CACHE_DIR / "deck_outboard.json"
LEGACY_GUIDE_STORE = CACHE_DIR / "deck_sbguides.json"
# Computed archetype baselines, keyed by "<format>::<archetype>". A deck
# created for an archetype is rooted at whatever this held at that moment;
# later recomputations overwrite the entry but never the decks already rooted.
ARCHETYPE_BASELINE_STORE = CACHE_DIR / "archetype_baselines.json"
CARD_INSPECTOR_LOG = CACHE_DIR / "card_inspector_debug.log"
ACTIVE_GUIDE_FILE = CONFIG_DIR / "active_guide.json"
