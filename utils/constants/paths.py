"""Filesystem paths and config/cache locations."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

BASE_DATA_DIR_ENV_VAR = "MTGO_TOOLS_BASE_DATA_DIR"

# Matches a WSL mount path like "/mnt/c" or "/mnt/c/foo/bar".
_WSL_MOUNT_RE = re.compile(r"^/mnt/([a-zA-Z])(?:/(.*))?$")
# Matches a Windows drive path like "C:\foo\bar" or "C:/foo/bar".
_WINDOWS_DRIVE_RE = re.compile(r"^([a-zA-Z]):[\\/](.*)$")


def _running_under_wsl() -> bool:
    if sys.platform != "linux":
        return False
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        with open("/proc/version", encoding="utf-8") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def _translate_worktree_path(raw: str) -> str:
    """Bridge path styles between WSL and Windows in .git worktree pointers.

    Git worktree markers are plain text pointing at the primary repo's
    ``.git/worktrees/<name>``. A worktree created by WSL git encodes the path
    as ``/mnt/<drive>/…``; Windows git encodes it as ``<drive>:\\…``. When the
    process reading the pointer runs on the other OS, the raw string can't be
    interpreted as an absolute path and silently resolves to the wrong place
    (e.g. ``C:\\mnt\\c\\…`` on Windows), so the caller has to translate.
    """
    if os.name == "nt":
        match = _WSL_MOUNT_RE.match(raw)
        if match:
            drive = match.group(1).upper()
            rest = match.group(2) or ""
            rest = rest.replace("/", "\\")
            return f"{drive}:\\{rest}" if rest else f"{drive}:\\"
    elif _running_under_wsl():
        match = _WINDOWS_DRIVE_RE.match(raw)
        if match:
            drive = match.group(1).lower()
            rest = match.group(2).replace("\\", "/")
            return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"
    return raw


def _resolved_env_base_dir() -> Path | None:
    """Return an explicit base-data directory override, if configured."""
    raw_value = os.getenv(BASE_DATA_DIR_ENV_VAR)
    if not raw_value:
        return None
    return Path(raw_value).expanduser().resolve()


def _safe_cwd() -> Path | None:
    try:
        return Path.cwd().resolve()
    except OSError:
        return None


def _find_git_marker(start: Path) -> Path | None:
    """Find the nearest .git marker from a directory inside a worktree."""
    current = start if start.is_dir() else start.parent
    for candidate in (current, *current.parents):
        marker = candidate / ".git"
        if marker.exists():
            return marker
    return None


def _resolve_gitdir(worktree_git_marker: Path) -> Path | None:
    """Resolve a .git directory or linked-worktree gitdir file."""
    if worktree_git_marker.is_dir():
        return worktree_git_marker.resolve()
    try:
        content = worktree_git_marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    prefix = "gitdir:"
    if not content.startswith(prefix):
        return None
    raw = content[len(prefix) :].strip()
    raw = _translate_worktree_path(raw)
    gitdir = Path(raw).expanduser()
    if not gitdir.is_absolute():
        gitdir = worktree_git_marker.parent / gitdir
    return gitdir.resolve()


def _primary_worktree_root_from_marker(worktree_git_marker: Path) -> Path:
    """Return the primary checkout root for a Git worktree marker."""
    gitdir = _resolve_gitdir(worktree_git_marker)
    if gitdir is None:
        return worktree_git_marker.parent.resolve()

    if gitdir.parent.name == "worktrees":
        common_git_dir = gitdir.parent.parent
        if common_git_dir.name == ".git":
            return common_git_dir.parent.resolve()

    if gitdir.name == ".git":
        return gitdir.parent.resolve()

    return worktree_git_marker.parent.resolve()


def _base_dir_from_cwd() -> Path | None:
    """Resolve the shared data root from the current working directory."""
    cwd = _safe_cwd()
    if cwd is None:
        return None
    git_marker = _find_git_marker(cwd)
    if git_marker is None:
        return None
    return _primary_worktree_root_from_marker(git_marker)


def _default_base_dir() -> Path:
    """Return the writable base directory for config/cache/logging."""
    env_base_dir = _resolved_env_base_dir()
    if env_base_dir is not None:
        return env_base_dir
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _base_dir_from_cwd() or Path(__file__).resolve().parent.parent.parent


BASE_DATA_DIR = _default_base_dir()
CONFIG_DIR = BASE_DATA_DIR / "config"
CACHE_DIR = BASE_DATA_DIR / "cache"
DECKS_DIR = Path.home() / "Documents" / "mtgo_decks"
DECK_SAVE_DIR = DECKS_DIR
LOGS_DIR = BASE_DATA_DIR / "logs"
CARD_DATA_DIR = BASE_DATA_DIR / "data"


def ensure_base_dirs() -> None:
    """Ensure base config/cache/deck/log directories exist without importing side effects."""
    BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path in (CONFIG_DIR, CACHE_DIR, DECKS_DIR, LOGS_DIR, CARD_DATA_DIR):
        path.mkdir(parents=True, exist_ok=True)


CONFIG_FILE = CONFIG_DIR / "config.json"
DECK_MONITOR_CONFIG_FILE = CONFIG_DIR / "deck_monitor_config.json"
DECK_SELECTOR_SETTINGS_FILE = CONFIG_DIR / "deck_selector_settings.json"
LEADERBOARD_POSITIONS_FILE = CONFIG_DIR / "leaderboard_positions.json"

DECK_MONITOR_CACHE_FILE = CACHE_DIR / "deck_monitor_cache.json"
ARCHETYPE_CACHE_FILE = CACHE_DIR / "archetype_cache.json"
ARCHETYPE_LIST_CACHE_FILE = CACHE_DIR / "archetype_list.json"
MTGO_ARTICLES_CACHE_FILE = CACHE_DIR / "mtgo_articles.json"
MTGO_DECK_CACHE_FILE = CACHE_DIR / "mtgo_decks.json"
MTGO_METADATA_CACHE_FILE = CACHE_DIR / "mtgo_deck_metadata.json"
DECK_CACHE_DB_FILE = CACHE_DIR / "deck_cache.db"
DECK_TEXT_CACHE_FILE = CACHE_DIR / "deck_text_cache.json"  # Individual deck content
ARCHETYPE_DECKS_CACHE_FILE = CACHE_DIR / "archetype_decks_cache.json"  # Deck lists per archetype
FORMAT_CARD_POOL_DB_FILE = CACHE_DIR / "format_card_pool.db"
RADAR_CACHE_DB_FILE = CACHE_DIR / "radar_cache.db"
DECK_CACHE_FILE = DECK_TEXT_CACHE_FILE
CURR_DECK_FILE = DECKS_DIR / "curr_deck.txt"

# Remote snapshot staging — downloaded artifacts live here before hydrating local caches
REMOTE_SNAPSHOT_CACHE_DIR = CACHE_DIR / "remote_snapshots"
REMOTE_SNAPSHOT_MANIFEST_FILE = REMOTE_SNAPSHOT_CACHE_DIR / "manifest.json"
REMOTE_SNAPSHOT_BUNDLE_STAMP_FILE = REMOTE_SNAPSHOT_CACHE_DIR / "bundle_stamp.json"
