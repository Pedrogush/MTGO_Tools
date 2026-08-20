"""Menu-bar UI strings. (English (United States))

The ``toolbar.*`` prefix is kept: phase 3b turned the toolbar into a menu bar and
the six window names plus the seven former gear actions carry over verbatim, so
renaming ~15 keys would have churned both locale files for no reader benefit.
The ``menu.*`` keys below are the ones the bar itself adds.
"""

MESSAGES: dict[str, str] = {
    "toolbar.opponent_tracker": "Opponent Tracker",
    "toolbar.timer_alert": "Timer Alert",
    "toolbar.match_history": "Match History",
    "toolbar.metagame_analysis": "Metagame Analysis",
    "toolbar.top_cards": "Top Cards",
    "toolbar.radar": "Radar",
    "toolbar.settings": "Settings",
    "menu.file": "File",
    "menu.tools": "Tools",
    "menu.preferences": "Preferences…",
    "menu.preferences.help": "Deck source, averages, language and updates",
    "menu.help": "Help",
    "menu.exit": "Exit",
    "toolbar.load_collection": "Load Collection",
    "toolbar.download_card_images": "Enable Offline Images Mode",
    "toolbar.update_card_database": "Update Card Database",
    "toolbar.export_diagnostics": "Export Diagnostics",
    "toolbar.show_tutorial": "Show Tutorial",
    "toolbar.help": "Help (F1)",
    "toolbar.comp_rules": "Comprehensive Rules",
    "toolbar.tooltip.opponent_tracker": "Detect your current MTGO opponent and look up their most-played archetypes",
    "toolbar.tooltip.timer_alert": "Set a countdown timer alert to warn you before round time runs out",
    "toolbar.tooltip.match_history": "Parse your MTGO GameLog files and view recent match results",
    "toolbar.tooltip.metagame_analysis": "Browse the format metagame breakdown and archetype share data",
    "toolbar.tooltip.top_cards": "Browse the most-played cards in each format from the local card-pool cache",
    "toolbar.tooltip.radar": "Open the archetype radar to analyze card frequencies",
}
