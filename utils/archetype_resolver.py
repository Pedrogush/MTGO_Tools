"""Utility to resolve archetype name strings to archetype dictionaries."""

from __future__ import annotations

import re
from typing import Any

from loguru import logger

from repositories.metagame_repository import MetagameRepository, get_metagame_repository


def normalize_archetype_name(name: str) -> str:
    """Normalize archetype name for comparison.

    Lowercases, strips whitespace, collapses multiple spaces.
    """
    name = name.lower().strip()
    name = re.sub(r"\s+", " ", name)
    return name


def find_archetype_by_name(
    archetype_name: str,
    format_name: str,
    metagame_repo: MetagameRepository | None = None,
) -> dict[str, Any] | None:
    """Find an archetype dict by name string.

    Fetches the archetype list for the given format and finds the
    archetype whose name matches (case-insensitive, normalized).

    Args:
        archetype_name: Archetype name string (e.g. "UR Murktide")
        format_name: MTG format (e.g. "Modern")
        metagame_repo: Optional metagame repository instance

    Returns:
        Archetype dictionary with 'name', 'href' keys, or None if not found.
    """
    repo = metagame_repo or get_metagame_repository()
    normalized_input = normalize_archetype_name(archetype_name)

    try:
        archetypes = repo.get_archetypes_for_format(format_name)
    except Exception:
        logger.warning(f"Failed to fetch archetypes for {format_name}")
        return None

    for archetype in archetypes:
        name = archetype.get("name", "")
        if normalize_archetype_name(name) == normalized_input:
            return archetype

    # Try partial matching as fallback
    for archetype in archetypes:
        name = archetype.get("name", "")
        normalized_name = normalize_archetype_name(name)
        if normalized_input in normalized_name or normalized_name in normalized_input:
            logger.debug(f"Partial match: '{archetype_name}' -> '{name}'")
            return archetype

    logger.debug(f"No archetype match for '{archetype_name}' in {format_name}")
    return None


__all__ = ["find_archetype_by_name", "normalize_archetype_name"]
