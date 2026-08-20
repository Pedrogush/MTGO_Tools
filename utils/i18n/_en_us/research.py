"""Deck research UI strings. (English (United States))"""

MESSAGES: dict[str, str] = {
    "research.format": "Format",
    "research.archetype": "Archetype",
    "research.event": "Event",
    "research.player_name": "Player name",
    "research.placement": "Placement",
    "research.placement_hint": "value",
    "research.player_name_hint": "Player name…",
    "research.date": "Date",
    "research.info": "Deck research: search MTG decks by property",
    "research.search_hint": "Search archetypes...",
    "research.reload_archetypes": "Reload Archetypes",
    "research.loading_archetypes": "Loading...",
    "research.failed_archetypes": "Failed to load archetypes.",
    "research.no_archetypes": "No archetypes found.",
    "research.tooltip.format": "Select the format to research",
    "research.tooltip.search": "Filter the archetype list by name",
    "research.tooltip.archetypes": "Click an archetype to load its decklists",
    "research.tooltip.reload": "Refresh archetype data from MTGGoldfish",
    "research.switch_to_builder.tooltip": "Switch to Deck Builder mode",
    "research.result": "Result",
    # The two option lists under the Result and Event labels. Both were built
    # straight from their canonical value tuples, so phase 7's translated
    # "Result" heading sat above untranslated options in pt-BR. The MTGO event
    # series -- Challenge, League, Showcase, Last Chance -- are proper nouns and
    # deliberately have no key: they fall through to the value in both locales.
    "research.placement_field.placement": "Placement",
    "research.placement_field.wins": "Wins",
    "research.event_type.all": "All",
}
