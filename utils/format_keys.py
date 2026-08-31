"""Canonical format keys for the archetype-list cache.

``cache/archetype_list.json`` is written by three unrelated code paths — the
MTGGoldfish scraper, :class:`~repositories.metagame_repository.MetagameRepository`
and the bundle snapshot client — and read back by the first two. They used to
disagree about the key: two lowercased the format name, one used it verbatim,
so a single file grew both ``modern`` (bundle list) and ``Modern`` (repository
list) with different contents and timestamps, and neither writer could ever see
the other's work.

Everything that touches that file now goes through :func:`normalize_format_key`,
and every read/write first runs the mapping through
:func:`normalize_archetype_list_cache` so files already carrying both cases are
migrated instead of half-ignored.
"""

from __future__ import annotations

from typing import Any


def normalize_format_key(mtg_format: str) -> str:
    """Return the canonical archetype-cache key for *mtg_format*.

    ``"Modern"``, ``"modern"`` and ``" Modern "`` all key the same entry.
    """
    return (mtg_format or "").strip().lower()


def _archetype_identity(archetype: Any) -> str:
    """Identity used to union archetype lists during a key migration."""
    if not isinstance(archetype, dict):
        return repr(archetype)
    href = archetype.get("href") or archetype.get("url") or ""
    if href:
        return f"href:{href.lower()}"
    return f"name:{str(archetype.get('name', '')).lower()}"


def _merge_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Fold case-variant entries for one format into a single entry.

    The freshest entry wins — its timestamp and item order are kept — and
    archetypes only the older entries knew about are appended rather than
    dropped, so migrating a dual-case file never loses data the user already
    had. Any residue is transient: the next refresh overwrites the canonical
    key with a freshly fetched list.
    """
    ordered = sorted(entries, key=lambda entry: entry.get("timestamp", 0), reverse=True)
    winner = ordered[0]
    merged_items: list[Any] = list(winner.get("items") or [])
    seen = {_archetype_identity(item) for item in merged_items}
    for entry in ordered[1:]:
        for item in entry.get("items") or []:
            identity = _archetype_identity(item)
            if identity not in seen:
                seen.add(identity)
                merged_items.append(item)
    merged = dict(winner)
    merged["items"] = merged_items
    return merged


def normalize_archetype_list_cache(data: Any) -> dict[str, Any]:
    """Return *data* re-keyed by :func:`normalize_format_key`.

    Entries whose keys differ only by case (or by surrounding whitespace) are
    merged by :func:`_merge_entries`. Non-mapping input, or entries that are not
    mappings, are passed through untouched so a corrupt file degrades exactly as
    it did before.
    """
    if not isinstance(data, dict):
        return {}

    grouped: dict[str, list[dict[str, Any]]] = {}
    normalized: dict[str, Any] = {}
    for key, entry in data.items():
        canonical = normalize_format_key(key) if isinstance(key, str) else key
        if isinstance(entry, dict) and isinstance(canonical, str):
            grouped.setdefault(canonical, []).append(entry)
        else:
            normalized[canonical] = entry

    for canonical, entries in grouped.items():
        normalized[canonical] = entries[0] if len(entries) == 1 else _merge_entries(entries)

    return normalized
