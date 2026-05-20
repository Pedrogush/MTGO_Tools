"""Top-level orchestrators: parse a single GameLog file or every file under a directory tree."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from loguru import logger

from services.gamelog_service.discovery import find_all_gamelog_dirs, find_gamelog_files
from services.gamelog_service.formats import detect_archetype, detect_format_from_cards
from services.gamelog_service.parser import (
    extract_cards_played,
    extract_players,
    parse_game_results,
    parse_match_score,
    parse_mulligan_data,
    parse_timestamp,
)
from services.gamelog_service.usernames import normalize_player_name

if TYPE_CHECKING:
    from services.card_data_service import CardDataManager


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
