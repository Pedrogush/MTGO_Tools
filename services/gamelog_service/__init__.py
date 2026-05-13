"""GameLog Service package - parses MTGO Match_GameLog_*.dat files.

Split by responsibility into internal modules:

- ``usernames``: bridge username lookup, name normalization, inference helpers
- ``discovery``: locate GameLog directories/files (bridge + filesystem scan)
- ``parser``: raw text → records (timestamps, players, cards, mulligans, scores, results)
- ``formats``: format detection via legalities, archetype classification
- ``service``: top-level orchestrators (``parse_gamelog_file``, ``parse_all_gamelogs``)
"""

from __future__ import annotations

from services.gamelog_service.discovery import (
    find_all_gamelog_dirs,
    find_gamelog_files,
    locate_gamelog_directory,
    locate_gamelog_directory_via_bridge,
)
from services.gamelog_service.formats import (
    detect_archetype,
    detect_format_from_cards,
)
from services.gamelog_service.parser import (
    extract_cards_played,
    extract_players,
    parse_game_results,
    parse_match_score,
    parse_mulligan_data,
    parse_timestamp,
)
from services.gamelog_service.service import parse_all_gamelogs, parse_gamelog_file
from services.gamelog_service.usernames import (
    get_current_username,
    infer_username_from_matches,
    normalize_player_name,
)

__all__ = [
    "detect_archetype",
    "detect_format_from_cards",
    "extract_cards_played",
    "extract_players",
    "find_all_gamelog_dirs",
    "find_gamelog_files",
    "get_current_username",
    "infer_username_from_matches",
    "locate_gamelog_directory",
    "locate_gamelog_directory_via_bridge",
    "normalize_player_name",
    "parse_all_gamelogs",
    "parse_game_results",
    "parse_gamelog_file",
    "parse_match_score",
    "parse_mulligan_data",
    "parse_timestamp",
]
