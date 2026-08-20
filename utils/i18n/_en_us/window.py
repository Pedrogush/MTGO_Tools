"""Window title UI strings. (English (United States))

C8: three of these carried an ``MTGO`` prefix and four did not, so the same
kind of window announced itself two different ways. The prefix is dropped
rather than added everywhere, for two reasons: it is the name of *Magic: The
Gathering Online*, not of this app (which is "MTGO Tools"), so "MTGO Match
History" reads as a claim to be one of MTGO's own windows; and every one of
these windows is opened from a Tools menu entry that already names it without
the prefix (``toolbar.match_history`` = "Match History"), so the menu and the
window it opens now agree.

Phase 9 added the six below. Seven of the app's eighteen top-level windows
carried hard-coded English titles (found by phase 4); the seventh, the
comp-rules popup, reuses ``window.title.rules_browser`` because it opens showing
the same thing the rules browser does. None of the seven is handed a locale --
they are opened from wherever the user happens to be, and the splash frame
exists before a controller does -- so they read the ambient locale via
``utils.i18n.t``. ``tests/test_window_titles.py`` fails on a new literal title.
"""

MESSAGES: dict[str, str] = {
    "window.title.opponent_tracker": "Opponent Tracker",
    "window.title.match_history": "Match History",
    "window.title.timer_alert": "Timer Alert",
    "window.title.metagame_analysis": "Metagame Analysis",
    "window.title.top_cards": "Top Cards",
    "window.title.radar": "Archetype Radar — {format}",
    "window.title.diagnostics": "Export Diagnostics",
    "window.title.guide_entry": "Sideboard Guide Entry",
    "window.title.guide_import_options": "Import Options",
    "window.title.offline_images": "Offline Images Mode",
    "window.title.mana_keyboard": "Mana Keyboard",
    "window.title.splash": "Loading MTGO Tools",
    "window.title.rules_browser": "Comprehensive Rules",
}
