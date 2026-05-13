"""Locate MTGO GameLog directories and files on disk (and via MTGO bridge)."""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404 - used to invoke trusted MTGO bridge helper
from datetime import datetime
from pathlib import Path

from loguru import logger


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
