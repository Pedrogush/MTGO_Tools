"""Local storage files and logs."""

from utils.constants.paths import CACHE_DIR, CONFIG_DIR

NOTES_STORE = CACHE_DIR / "deck_notes.json"
OUTBOARD_STORE = CACHE_DIR / "deck_outboard.json"
GUIDE_STORE = CACHE_DIR / "deck_sbguides.json"
# Computed archetype baselines, keyed by "<format>::<archetype>". A deck
# created for an archetype is rooted at whatever this held at that moment;
# later recomputations overwrite the entry but never the decks already rooted.
ARCHETYPE_BASELINE_STORE = CACHE_DIR / "archetype_baselines.json"
CARD_INSPECTOR_LOG = CACHE_DIR / "card_inspector_debug.log"
ACTIVE_GUIDE_FILE = CONFIG_DIR / "active_guide.json"
