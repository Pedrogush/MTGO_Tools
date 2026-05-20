"""Path resolution helpers for stored cache entries.

Stored ``file_path`` values in the SQLite database may be:

* Absolute POSIX paths from the running machine
* Absolute Windows paths (with backslashes and drive letters) — possibly from a
  WSL bind-mount or a prior install of the app
* Relative paths under the cache directory

:func:`resolve_stored_path` normalizes any of those forms back into a usable
:class:`pathlib.Path` for the current platform and cache layout.
"""

from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath

from loguru import logger


def build_path_roots(cache_dir: Path) -> list[Path]:
    """Return the candidate filesystem roots used to resolve relative paths."""
    roots: list[Path] = []
    candidates = [
        Path.cwd(),
        cache_dir,
        cache_dir.parent,
    ]
    # Include grandparent (project root) if available
    try:
        candidates.append(cache_dir.parents[1])
    except IndexError:
        pass
    seen = set()
    for entry in candidates:
        resolved = entry.resolve()
        if resolved not in seen:
            seen.add(resolved)
            roots.append(resolved)
    return roots


def resolve_relative_path(relative: Path, roots: list[Path]) -> Path | None:
    """Try to resolve *relative* against any of the configured *roots*."""
    for root in roots:
        candidate = (root / relative).resolve()
        if candidate.exists():
            return candidate
    return None


def normalize_path(path: Path, roots: list[Path]) -> Path:
    """Return *path* as-is if absolute, else try to resolve against *roots*."""
    try:
        if path.is_absolute():
            return path
    except OSError:
        pass

    rel = resolve_relative_path(path, roots)
    if rel is not None:
        return rel

    return path


def resolve_stored_path(stored_path: str, cache_dir: Path, roots: list[Path]) -> Path:
    """Convert stored path strings into usable filesystem Paths.

    Handles Windows-style separators and WSL drive prefixes when running on
    POSIX, plus rebasing when the project root was renamed and only the
    last two components remain locatable under the current ``cache_dir``.
    """
    raw = stored_path.strip()
    path = Path(raw)
    resolved = normalize_path(path, roots)
    if resolved.exists():
        return resolved

    # Normalize backslashes to forward slashes (works on all OSes)
    if "\\" in raw:
        normalized = raw.replace("\\", "/")
        path = Path(normalized)
        normalized_resolved = normalize_path(path, roots)
        if normalized_resolved.exists():
            return normalized_resolved

        # Interpret as Windows path and convert to current platform
        try:
            win_path = Path(PureWindowsPath(raw))
            if win_path.exists():
                return win_path
        except Exception as exc:
            logger.debug("Failed to normalize Windows path '%s': %s", raw, exc)

        # Translate Windows drive letters for WSL paths (e.g., C:\ -> /mnt/c/)
        if os.name != "nt" and len(raw) >= 3 and raw[1] == ":" and raw[2] in ("\\", "/"):
            drive = raw[0].lower()
            remainder = raw[3:].replace("\\", "/")
            wsl_path = Path("/mnt") / drive / remainder
            if wsl_path.exists():
                return wsl_path

    # Project may have been renamed (e.g. magic_online_metagame_crawler →
    # mtgo_tools).  The stored absolute path no longer exists but the file
    # itself (identified by its UUID filename) lives under the current
    # cache_dir.  Reconstruct the path from just the last two components
    # (size-subfolder/uuid.jpg) relative to the current cache_dir.
    try:
        raw_path = Path(raw.replace("\\", "/"))
        rebased = cache_dir / raw_path.parts[-2] / raw_path.name
        if rebased.exists():
            return rebased
    except Exception:
        pass

    return resolved


__all__ = [
    "build_path_roots",
    "normalize_path",
    "resolve_relative_path",
    "resolve_stored_path",
]
