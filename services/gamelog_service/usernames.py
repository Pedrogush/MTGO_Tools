"""Username helpers: bridge lookup, normalization, and inference from matches."""

from __future__ import annotations

import json
import subprocess  # nosec B404 - used to invoke trusted MTGO bridge helper

from loguru import logger

from utils.constants import BRIDGE_PATH


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


def normalize_player_name(name: str, to_storage: bool = True) -> str:
    """Convert player names between display and storage formats.

    Storage format: spaces->'+', periods->'*'. Display format: reverse.
    """
    if to_storage:
        return name.replace(" ", "+").replace(".", "*")
    else:
        return name.replace("+", " ").replace("*", ".")


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
