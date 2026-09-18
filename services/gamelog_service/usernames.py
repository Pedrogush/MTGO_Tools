"""Username helpers: bridge lookup, normalization, and inference from matches."""

from __future__ import annotations

import json
import subprocess  # nosec B404 - used to invoke trusted MTGO bridge helper

from loguru import logger

from utils.constants import BRIDGE_PATH


# Measured against a live client: ~3.1s cold, ~4.4s when another bridge process
# is attached (SDK reads serialise on MTGO's UI thread). 10s left little headroom.
BRIDGE_USERNAME_TIMEOUT_SECONDS = 25.0


def get_current_username() -> str | None:
    """Get current MTGO username via bridge.

    Returns None when the username cannot be determined, but never silently:
    every failure mode logs at WARNING. The bridge exits 0 and prints
    ``{"error": ...}`` when it cannot reach the client, so a plain
    ``data.get("username")`` miss is a real failure, not a quiet no-op.
    """
    try:
        result = subprocess.run(
            [BRIDGE_PATH, "username"],
            capture_output=True,
            text=True,
            # text=True alone decodes with the Windows locale codec, which raises
            # UnicodeDecodeError on a non-ASCII MTGO account name.
            encoding="utf-8",
            errors="replace",
            timeout=BRIDGE_USERNAME_TIMEOUT_SECONDS,
        )  # nosec B603 - args are fixed for bridge helper
    except subprocess.TimeoutExpired:
        logger.warning(
            "MTGO bridge 'username' timed out after {}s", BRIDGE_USERNAME_TIMEOUT_SECONDS
        )
        return None
    except OSError as exc:
        logger.warning("Could not run MTGO bridge 'username': {}", exc)
        return None

    if result.returncode != 0:
        logger.warning(
            "MTGO bridge 'username' exited {}: {}",
            result.returncode,
            (result.stderr or "").strip()[:300],
        )
        return None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.warning("MTGO bridge 'username' returned non-JSON: {!r}", result.stdout[:300])
        return None

    username = data.get("username") if isinstance(data, dict) else None
    if username:
        logger.debug("Current MTGO user: {}", username)
        return username

    # Previously this path returned None with no logging at any level, so a
    # failing bridge was indistinguishable from "not logged in".
    logger.warning(
        "MTGO bridge could not determine username: {}",
        (isinstance(data, dict) and data.get("error")) or "no 'username' field in response",
    )
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
