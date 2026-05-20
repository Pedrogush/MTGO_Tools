"""Raw text → structured records: timestamps, players, cards, mulligans, scores, results."""

from __future__ import annotations

import os
import re
from datetime import datetime

from loguru import logger

from services.gamelog_service.usernames import normalize_player_name


def extract_players(content: str) -> list[str]:
    players = []

    # Split by player markers
    sections = content.split("@P")

    for section in sections:
        if " joined the game" in section:
            player_name = section.split(" joined the game")[0].strip()
            if player_name and player_name not in players:
                players.append(player_name)

    # Sort by length descending (helps with replacement later)
    players.sort(key=len, reverse=True)

    return players


def parse_timestamp(timestamp_str: str, file_path: str = None) -> datetime:
    # Check if this looks like binary data (UUIDs, special characters, etc.)
    if "$" in timestamp_str or any(ord(c) > 127 for c in timestamp_str[:50]):
        # Binary format - use file modification time as fallback
        if file_path and os.path.exists(file_path):
            return datetime.fromtimestamp(os.path.getmtime(file_path))
        return datetime.now()

    month_map = {
        "Jan": "01",
        "Feb": "02",
        "Mar": "03",
        "Apr": "04",
        "May": "05",
        "Jun": "06",
        "Jul": "07",
        "Aug": "08",
        "Sep": "09",
        "Oct": "10",
        "Nov": "11",
        "Dec": "12",
    }

    try:
        parts = timestamp_str.strip().split()
        # Format: Wed Dec 04 14:23:10 PST 2024
        month = month_map.get(parts[1], "01")
        day = parts[2].zfill(2)
        time_parts = parts[3].split(":")
        hour = time_parts[0].zfill(2)
        minute = time_parts[1]
        year = parts[5] if len(parts) > 5 else parts[4]

        # Create datetime string
        dt_str = f"{year}-{month}-{day} {hour}:{minute}:00"
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")

    except Exception as exc:
        logger.debug(
            "Failed to parse timestamp '%s' from %s: %s",
            timestamp_str,
            file_path or "unknown file",
            exc,
        )
        # Silent fallback to file modification time or current time
        if file_path and os.path.exists(file_path):
            return datetime.fromtimestamp(os.path.getmtime(file_path))
        return datetime.now()


def extract_cards_played(content: str, player_name: str) -> list[str]:
    cards = set()

    # Convert to display format for matching
    display_name = normalize_player_name(player_name, False)

    # The GameLog binary format uses non-newline binary bytes as record
    # separators; the file may contain only a handful of actual '\n' characters
    # across thousands of action records.  Splitting on '\n' produces huge
    # multi-action chunks containing both players' actions, making it
    # impossible to attribute cards to the correct player.
    #
    # Splitting on '@P' instead gives one segment per game action.  Each
    # segment starts with the acting player's name, so a simple startswith()
    # check unambiguously identifies who performed the action.
    #
    # Within each segment we use a verb whitelist to extract only the card
    # that is the grammatical object of that verb (the player's own card).
    # This avoids cross-contamination from patterns like:
    #   "player is being attacked by @[Opponent's Creature]"
    #   "player draws 3 cards with @[Opponent's Spell]"      (Burning Inquiry etc.)
    #   "player casts @[Own Spell] targeting @[Opponent's Permanent]"
    # In the last case the verb pattern captures only the spell, not the target.
    _CARD_REF = r"@\[([^@]+)@:\d+,\d+:@\]"
    _OWN_CARD_PATTERNS = [
        re.compile(r"(?:plays|casts)\s+" + _CARD_REF),
        re.compile(r"activates an ability of " + _CARD_REF),
        re.compile(r"puts a triggered ability from " + _CARD_REF),
        re.compile(r"(?:discards|cycles|reveals)\s+" + _CARD_REF),
    ]

    for segment in content.split("@P"):
        if not (segment.startswith(player_name) or segment.startswith(display_name)):
            continue
        for pattern in _OWN_CARD_PATTERNS:
            for m in pattern.finditer(segment):
                cards.add(m.group(1))

    return sorted(cards)


def parse_mulligan_data(content: str) -> dict[str, list[int]]:
    """Extract mulligan counts per player per game.

    Example: ``{"Player1": [0, 2, 1], "Player2": [1, 0, 0]}``
    """
    mulligan_data = {}
    current_game = 0
    lines = content.split("\n")

    for line in lines:
        # New game starts
        if "chooses to play first" in line or "chooses to not play first" in line:
            current_game += 1

        # Mulligan detected: "PlayerName mulligans to X cards"
        mulligan_match = re.search(r"@P([^@]+)\smulligans to (\w+) cards?", line)
        if mulligan_match:
            player = mulligan_match.group(1).strip()
            count_word = mulligan_match.group(2)

            # Convert word to number
            word_to_num = {
                "zero": 0,
                "one": 1,
                "two": 2,
                "three": 3,
                "four": 4,
                "five": 5,
                "six": 6,
                "seven": 7,
            }
            mulligan_count = 7 - word_to_num.get(count_word.lower(), 7)

            if player not in mulligan_data:
                mulligan_data[player] = {}
            if current_game not in mulligan_data[player]:
                mulligan_data[player][current_game] = 0
            mulligan_data[player][current_game] = max(
                mulligan_data[player][current_game], mulligan_count
            )

    # Convert to lists (games in order)
    result = {}
    for player, games in mulligan_data.items():
        result[player] = [games.get(i, 0) for i in range(1, max(games.keys()) + 1)] if games else []

    return result


def parse_match_score(content: str) -> tuple[str, int, int] | None:
    lines = content.split("\n")

    # Look for "PlayerName wins the match X-Y" or "PlayerName leads the match X-Y"
    for line in reversed(lines):  # Start from end
        match_win = re.search(r"@P([^@]+)\swins the match (\d)-(\d)", line)
        if match_win:
            winner = match_win.group(1).strip()
            winner_score = int(match_win.group(2))
            loser_score = int(match_win.group(3))
            return (winner, winner_score, loser_score)

        match_lead = re.search(r"@P([^@]+)\sleads the match (\d)-(\d)", line)
        if match_lead:
            leader = match_lead.group(1).strip()
            leader_score = int(match_lead.group(2))
            other_score = int(match_lead.group(3))
            return (leader, leader_score, other_score)

    return None


def parse_game_results(content: str) -> list[dict[str, str]]:
    games = []
    lines = content.split("\n")
    current_game_num = 0
    game_ended_in_current_game = False

    for line in lines:
        # New game starts
        if "chooses to play first" in line or "chooses to not play first" in line:
            current_game_num += 1
            game_ended_in_current_game = False

        # Skip if we already recorded a result for this game
        if game_ended_in_current_game:
            continue

        # Game win/concession - record ONLY ONCE per game
        if "wins the game" in line:
            winner_match = re.search(r"@P([^@]+)\swins the game", line)
            if winner_match:
                games.append(
                    {
                        "game_num": current_game_num,
                        "winner": winner_match.group(1).strip(),
                        "method": "win",
                    }
                )
                game_ended_in_current_game = True
        elif "has conceded from the game" in line:
            loser_match = re.search(r"@P([^@]+)\shas conceded", line)
            if loser_match:
                # Winner is the other player (determined later)
                games.append(
                    {
                        "game_num": current_game_num,
                        "loser": loser_match.group(1).strip(),
                        "method": "concession",
                    }
                )
                game_ended_in_current_game = True

    return games
