"""
MTGO GameLog Parser

Parses Magic: The Gathering Online GameLog files to extract match history,
opponent names, and game results.

Adapted from cderickson/MTGO-Tracker:
https://github.com/cderickson/MTGO-Tracker

Key modifications:
- Simplified to focus on match history and opponent extraction
- Integrated with MongoDB storage
- Added support for locating log files via MTGOSDK
"""

from __future__ import annotations

import json
import os
import re
import subprocess  # nosec B404 - used to invoke trusted MTGO bridge helper
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from utils.constants import BRIDGE_PATH

if TYPE_CHECKING:
    from utils.card_data import CardDataManager

# MTGO competitive formats in priority order (most → least restrictive card pool)
_COMPETITIVE_FORMATS: list[str] = ["standard", "pioneer", "modern", "legacy", "vintage", "pauper"]
_FORMAT_DISPLAY: dict[str, str] = {
    "standard": "Standard",
    "pioneer": "Pioneer",
    "modern": "Modern",
    "legacy": "Legacy",
    "vintage": "Vintage",
    "pauper": "Pauper",
}


def get_current_username() -> str | None:
    """Get current MTGO username via bridge."""

    try:
        result = subprocess.run(
            [BRIDGE_PATH, "username"], capture_output=True, text=True, timeout=10
        )  # nosec B603 - args are fixed for bridge helper

        if result.returncode == 0:
            data = json.loads(result.stdout)
            username = data.get("username")
            if username:
                logger.debug(f"Current MTGO user: {username}")
                return username
    except Exception as e:
        logger.debug(f"Could not get username via bridge: {e}")

    return None


def detect_format_from_cards(
    cards: list[str],
    card_manager: CardDataManager | None = None,
) -> str:
    """Detect the MTGO format from a card list using legality data.

    When *card_manager* is supplied and loaded the function intersects each
    card's legal competitive formats and returns the most restrictive one that
    covers the whole deck.  Requires at least 5 cards with legality data to
    make a confident call; returns ``"Unknown"`` otherwise.
    """
    if card_manager is not None and card_manager.is_loaded:
        return _detect_format_via_legalities(cards, card_manager)
    return "Unknown"


def _detect_format_via_legalities(
    cards: list[str],
    card_manager: CardDataManager,
) -> str:
    legal_format_sets: list[set[str]] = []
    for card_name in set(cards):
        entry = card_manager.get_card(card_name)
        if entry is None:
            continue
        legal = {fmt for fmt in _COMPETITIVE_FORMATS if entry.legalities.get(fmt) == "Legal"}
        if legal:
            legal_format_sets.append(legal)

    if len(legal_format_sets) < 5:
        return "Unknown"

    common: set[str] = legal_format_sets[0].copy()
    for s in legal_format_sets[1:]:
        common &= s

    for fmt in _COMPETITIVE_FORMATS:
        if fmt in common:
            return _FORMAT_DISPLAY[fmt]

    return "Unknown"


def detect_archetype(cards: list[str]) -> str:
    """Detect deck archetype from card list."""
    if not cards or len(cards) < 5:
        return "Unknown"

    card_set = set(cards)

    # Modern archetypes
    archetype_signatures = {
        "Murktide": ["Murktide Regent", "Dragon's Rage Channeler"],
        "Hammer Time": ["Colossus Hammer", "Puresteel Paladin", "Sigarda's Aid"],
        "Tron": ["Urza's Tower", "Urza's Mine", "Urza's Power Plant", "Karn Liberated"],
        "Amulet Titan": ["Amulet of Vigor", "Primeval Titan"],
        "Living End": ["Living End", "Violent Outburst"],
        "Burn": ["Lightning Bolt", "Lava Spike", "Rift Bolt"],
        "Death's Shadow": ["Death's Shadow", "Street Wraith"],
        "Yawgmoth": ["Yawgmoth, Thran Physician", "Chord of Calling"],
        "Scales": ["Hardened Scales", "Walking Ballista", "Arcbound Ravager"],
        "Rhinos": ["Crashing Footfalls", "Shardless Agent"],
        "Scam": ["Grief", "Undying Malice", "Ephemerate"],
        "4C Omnath": ["Omnath, Locus of Creation", "Leyline Binding"],
        "Domain Zoo": ["Leyline Binding", "Scion of Draco"],
        "Elementals": ["Solitude", "Fury", "Risen Reef"],
        "Affinity": ["Cranial Plating", "Ornithopter", "Mox Opal"],
        "Infect": ["Glistener Elf", "Blighted Agent", "Inkmoth Nexus"],
        "Storm": ["Grapeshot", "Gifts Ungiven", "Past in Flames"],
        "Mill": ["Hedron Crab", "Archive Trap", "Visions of Beyond"],
        "Control": ["Teferi, Hero of Dominaria", "Cryptic Command", "Supreme Verdict"],
        "Jund": ["Tarmogoyf", "Dark Confidant", "Liliana of the Veil"],
    }

    # Check signatures (require at least 1 signature card)
    matches = []
    for archetype, signature in archetype_signatures.items():
        signature_matches = sum(1 for card in signature if card in card_set)
        if signature_matches > 0:
            matches.append((archetype, signature_matches, len(signature)))

    # Sort by match count, then by signature size (prefer specific archetypes)
    if matches:
        matches.sort(key=lambda x: (x[1], -x[2]), reverse=True)
        best_match = matches[0]
        if best_match[1] >= 1:  # At least 1 signature card
            return best_match[0]

    # Fallback: generic classification by card types
    lands = sum(
        1
        for card in cards
        if any(x in card for x in ["Plains", "Island", "Swamp", "Mountain", "Forest", "Land"])
    )

    if lands < 10:
        return "Aggro"
    elif lands > 25:
        return "Control"
    else:
        return "Midrange"


def locate_gamelog_directory_via_bridge() -> str | None:
    """Use MTGOBridge to locate GameLog files through MTGOSDK."""
    try:
        from utils.constants import CONFIG
    except ImportError:
        logger.debug("CONFIG module not available; using defaults for MTGO bridge path")
        CONFIG = {}
    BRIDGE_PATH = CONFIG.get(
        "mtgo_BRIDGE_PATH", "dotnet/MTGOBridge/bin/Release/net9.0-windows7.0/win-x64/MTGOBridge.exe"
    )

    try:
        result = subprocess.run(
            [BRIDGE_PATH, "logfiles"], capture_output=True, text=True, timeout=10
        )  # nosec B603 - bridge path/args are controlled

        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data.get("files") and len(data["files"]) > 0:
                # Get directory from first file path
                first_file = data["files"][0]
                return str(Path(first_file).parent)

    except Exception as e:
        logger.debug(f"Error locating log files via bridge: {e}")

    return None


def _candidate_appdata_bases() -> list[Path]:
    """Return candidate AppData/Local/Apps/2.0/Data paths for the current platform."""
    paths = []

    # WSL: scan all user home dirs under /mnt/c/Users/
    wsl_users = Path("/mnt/c/Users")
    if wsl_users.is_dir():
        for user_dir in wsl_users.iterdir():
            candidate = user_dir / "AppData" / "Local" / "Apps" / "2.0" / "Data"
            if candidate.is_dir():
                paths.append(candidate)

    # Windows native: USERNAME env var is set by cmd/PowerShell
    win_username = os.environ.get("USERNAME", "")
    if win_username:
        candidate = Path(rf"C:\Users\{win_username}\AppData\Local\Apps\2.0\Data")
        if candidate.is_dir() and candidate not in paths:
            paths.append(candidate)

    return paths


def find_all_gamelog_dirs(appdata_base: str | None = None) -> list[str]:
    """
    Scan MTGO ClickOnce installation directories for folders containing GameLog files.

    MTGO ClickOnce layout:
        AppData/Local/Apps/2.0/Data/{hash}/{hash}/mtgo*/Data/AppFiles/{hash}/
        Match_GameLog_*.dat files live directly in the innermost hash folder.

    ``appdata_base`` auto-detects for both Windows and WSL when None.
    Returns paths sorted newest-first by the most recent log file's mtime.
    """
    if appdata_base:
        bases = [Path(appdata_base)]
    else:
        bases = _candidate_appdata_bases()

    found: list[Path] = []
    for base in bases:
        # ClickOnce layout: Data/{hash}/{hash}/mtgo*/Data/AppFiles/{hash}/
        for candidate in base.glob("*/*/mtgo*/Data/AppFiles/*/"):
            if candidate.is_dir() and any(candidate.glob("Match_GameLog_*.dat")):
                found.append(candidate)

    def _newest_mtime(d: Path) -> float:
        mtimes = [f.stat().st_mtime for f in d.glob("Match_GameLog_*.dat")]
        return max(mtimes) if mtimes else 0.0

    found.sort(key=_newest_mtime, reverse=True)
    dirs = [str(d) for d in found]
    logger.debug(
        f"Found {len(dirs)} MTGO GameLog director{'y' if len(dirs) == 1 else 'ies'}: {dirs}"
    )
    return dirs


def locate_gamelog_directory() -> str | None:
    """
    Locate the most recent MTGO GameLog directory.

    Strategy:
    1. Try using MTGOBridge + MTGOSDK (if MTGO is running)
    2. Fall back to scanning the ClickOnce AppData tree
    """
    path = locate_gamelog_directory_via_bridge()
    if path:
        logger.debug(f"Located GameLogs via MTGOSDK: {path}")
        return path

    dirs = find_all_gamelog_dirs()
    if dirs:
        logger.debug(f"Located GameLogs via filesystem scan: {dirs[0]}")
        return dirs[0]

    logger.warning("Could not locate MTGO GameLog directory")
    return None


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


def normalize_player_name(name: str, to_storage: bool = True) -> str:
    """Convert player names between display and storage formats.

    Storage format: spaces->'+', periods->'*'. Display format: reverse.
    """
    if to_storage:
        return name.replace(" ", "+").replace(".", "*")
    else:
        return name.replace("+", " ").replace("*", ".")


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


def parse_gamelog_file(
    file_path: str,
    card_manager: CardDataManager | None = None,
) -> dict | None:
    try:
        with open(file_path, encoding="latin1") as f:
            content = f.read()

        # Extract metadata from first line (timestamp)
        first_line = content.split("\n")[0]
        timestamp = parse_timestamp(first_line, file_path)

        # Extract players
        players = extract_players(content)
        if len(players) < 2:
            return None

        # Normalize player names
        players_normalized = [normalize_player_name(p, False) for p in players]

        # Extract game results
        game_results = parse_game_results(content)

        # Parse match score directly from log (more reliable than counting games)
        match_score_data = parse_match_score(content)
        if match_score_data:
            winner_name, winner_score, loser_score = match_score_data
            # Normalize the winner name
            match_winner = normalize_player_name(winner_name, False)
            player1_wins = winner_score if winner_name == players[0] else loser_score
            player2_wins = loser_score if winner_name == players[0] else winner_score
        else:
            # Fallback: count from game results
            player1_wins = sum(
                1
                for g in game_results
                if g.get("winner") == players[0] or g.get("loser") == players[1]
            )
            player2_wins = sum(
                1
                for g in game_results
                if g.get("winner") == players[1] or g.get("loser") == players[0]
            )

            if player1_wins > player2_wins:
                match_winner = players_normalized[0]
            elif player2_wins > player1_wins:
                match_winner = players_normalized[1]
            else:
                match_winner = None

        # Extract deck lists (cards played)
        player1_deck = extract_cards_played(content, players[0])
        player2_deck = extract_cards_played(content, players[1])

        # Extract mulligan data
        mulligan_data = parse_mulligan_data(content)
        player1_mulligans = mulligan_data.get(players[0], [])
        player2_mulligans = mulligan_data.get(players[1], [])

        # Extract match ID from filename
        match_id = os.path.basename(file_path).replace("Match_GameLog_", "").replace(".dat", "")

        # Detect format and archetypes
        detected_format = detect_format_from_cards(player1_deck + player2_deck, card_manager)
        player1_archetype = detect_archetype(player1_deck)
        player2_archetype = detect_archetype(player2_deck)

        return {
            "match_id": match_id,
            "file_path": file_path,
            "timestamp": timestamp,
            "players": players_normalized,
            "opponent": players_normalized[1],
            "winner": match_winner,
            "match_score": f"{player1_wins}-{player2_wins}",
            "games": game_results,
            "format": detected_format,
            "player1_deck": player1_deck,
            "player2_deck": player2_deck,
            "player1_archetype": player1_archetype,
            "player2_archetype": player2_archetype,
            "player1_mulligans": player1_mulligans,
            "player2_mulligans": player2_mulligans,
            "total_mulligans": sum(player1_mulligans) if player1_mulligans else 0,
            "notes": "",
        }

    except Exception as exc:
        logger.warning("Failed to parse GameLog file %s: %s", file_path, exc)
        # Silently skip unparseable files
        return None


def infer_username_from_matches(matches: list[dict]) -> str | None:
    """
    Infer the current user's username from a list of parsed matches.

    The local user appears in every match because GameLog files are stored on
    their machine.  Any player present in ≥80% of matches is treated as the
    local user.
    """
    if not matches:
        return None

    from collections import Counter

    player_counts: Counter[str] = Counter()
    for match in matches:
        for player in match.get("players", []):
            player_counts[player] += 1

    if not player_counts:
        return None

    total = len(matches)
    threshold = total * 0.8

    name, count = player_counts.most_common(1)[0]
    if count >= threshold:
        logger.debug(f"Inferred current username as '{name}' ({count}/{total} matches)")
        return name

    return None


def find_gamelog_files(directory: str, since_date: datetime | None = None) -> list[str]:
    files = []

    for filename in os.listdir(directory):
        if filename.startswith("Match_GameLog_") and filename.endswith(".dat"):
            file_path = os.path.join(directory, filename)

            if since_date:
                mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if mtime < since_date:
                    continue

            files.append(file_path)

    # Sort by modification time (newest first)
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)

    return files


def parse_all_gamelogs(
    directory: str | list[str] | None = None,
    limit: int = None,
    progress_callback=None,
    card_manager: CardDataManager | None = None,
) -> list[dict]:
    if directory is None:
        directories = find_all_gamelog_dirs()
        if not directories:
            raise RuntimeError("Could not locate any MTGO GameLog directories")
    elif isinstance(directory, list):
        directories = directory
    else:
        directories = [directory]

    log_files: list[str] = []
    seen: set[str] = set()
    for d in directories:
        for f in find_gamelog_files(d):
            # Deduplicate by filename in case dirs overlap
            name = os.path.basename(f)
            if name not in seen:
                seen.add(name)
                log_files.append(f)

    if limit:
        log_files = log_files[:limit]

    matches = []
    total_files = len(log_files)

    for i, file_path in enumerate(log_files):
        if progress_callback:
            progress_callback(i + 1, total_files)

        match_data = parse_gamelog_file(file_path, card_manager)
        if match_data:
            matches.append(match_data)

    logger.debug(
        f"Parsed {len(matches)} matches from {len(log_files)} log files"
        f" across {len(directories)} director{'y' if len(directories) == 1 else 'ies'}"
    )

    return matches


if __name__ == "__main__":
    # Test the parser
    print("MTGO GameLog Parser Test")
    print("=" * 50)

    # Locate log directory
    log_dir = locate_gamelog_directory()
    if log_dir:
        print(f"Found GameLog directory: {log_dir}")

        # Parse recent matches
        matches = parse_all_gamelogs(log_dir, limit=10)

        print(f"\nFound {len(matches)} recent matches:")
        for match in matches[:5]:
            print(
                f"  {match['timestamp'].strftime('%Y-%m-%d %H:%M')} - "
                f"{match['players'][0]} vs {match['opponent']} - "
                f"Winner: {match['winner'] or 'Unknown'}"
            )
    else:
        print("Could not locate GameLog directory")
        print("Make sure MTGO is installed or provide path manually")
