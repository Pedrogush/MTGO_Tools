"""Local storage files and logs."""

from utils.constants.paths import CACHE_DIR

NOTES_STORE = CACHE_DIR / "deck_notes.json"
OUTBOARD_STORE = CACHE_DIR / "deck_outboard.json"
GUIDE_STORE = CACHE_DIR / "deck_sbguides.json"
CARD_INSPECTOR_LOG = CACHE_DIR / "card_inspector_debug.log"
