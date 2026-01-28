"""Resolves stored image paths to usable filesystem Paths.

Handles Windows-style separators, WSL drive prefixes, and relative cache
entries when running on any platform.
"""

from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath

from loguru import logger


class CardImagePathResolver:
    """Convert stored path strings into usable filesystem Paths.

    Accounts for cross-platform differences such as Windows back-slashes
    and WSL drive-letter translations (e.g. ``C:\\`` -> ``/mnt/c/``).
    """

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir.resolve()
        self._path_roots = self._build_path_roots()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_path_roots(self) -> list[Path]:
        """Precompute base directories used to resolve relative cache entries."""
        roots: list[Path] = []
        candidates = [
            Path.cwd(),
            self._cache_dir,
            self._cache_dir.parent,
        ]
        try:
            candidates.append(self._cache_dir.parents[1])
        except IndexError:
            pass
        seen: set[Path] = set()
        for entry in candidates:
            resolved = entry.resolve()
            if resolved not in seen:
                seen.add(resolved)
                roots.append(resolved)
        return roots

    def _normalize_path(self, path: Path) -> Path:
        """Resolve absolute paths or attempt to rebuild relatives under known roots."""
        try:
            if path.is_absolute():
                return path
        except OSError:
            pass

        rel = self._resolve_relative_path(path)
        if rel is not None:
            return rel

        return path

    def _resolve_relative_path(self, relative: Path) -> Path | None:
        """Attempt to resolve a relative cache entry against known roots."""
        for root in self._path_roots:
            candidate = (root / relative).resolve()
            if candidate.exists():
                return candidate
        return None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def resolve_path(self, stored_path: str) -> Path:
        """Convert a stored path string into a usable filesystem Path.

        Handles Windows-style separators and WSL drive prefixes when running
        on POSIX systems.
        """
        raw = stored_path.strip()
        path = Path(raw)
        resolved = self._normalize_path(path)
        if resolved.exists():
            return resolved

        # Normalize backslashes to forward slashes (works on all OSes)
        if "\\" in raw:
            normalized = raw.replace("\\", "/")
            path = Path(normalized)
            normalized_resolved = self._normalize_path(path)
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

        return resolved
