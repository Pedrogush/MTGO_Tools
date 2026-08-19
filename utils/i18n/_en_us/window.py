"""Window title UI strings. (English (United States))

C8: three of these carried an ``MTGO`` prefix and four did not, so the same
kind of window announced itself two different ways. The prefix is dropped
rather than added everywhere, for two reasons: it is the name of *Magic: The
Gathering Online*, not of this app (which is "MTGO Tools"), so "MTGO Match
History" reads as a claim to be one of MTGO's own windows; and every one of
these windows is opened from a Tools menu entry that already names it without
the prefix (``toolbar.match_history`` = "Match History"), so the menu and the
window it opens now agree.
"""

MESSAGES: dict[str, str] = {
    "window.title.opponent_tracker": "Opponent Tracker",
    "window.title.match_history": "Match History",
    "window.title.timer_alert": "Timer Alert",
    "window.title.metagame_analysis": "Metagame Analysis",
    "window.title.top_cards": "Top Cards",
    "window.title.radar": "Archetype Radar — {format}",
    "window.title.rules_browser": "Comprehensive Rules",
}
