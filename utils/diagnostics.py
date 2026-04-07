"""Diagnostics: opt-in local event logging and diagnostics bundle export."""

from __future__ import annotations

import json
import platform
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class EventLogger:
    """Opt-in, anonymised feature-usage logger persisted locally as JSONL.

    No network calls are ever made.  All events are written to a single
    rotating file inside the application's logs directory.

    Usage::

        el = EventLogger(logs_dir)
        el.log("archetype_loaded", {"format": "Modern"})
    """

    _FILENAME = "events.jsonl"
    _MAX_BYTES = 2 * 1024 * 1024  # 2 MB – rotate by renaming to .1

    def __init__(self, logs_dir: Path, *, enabled: bool = False) -> None:
        self._logs_dir = logs_dir
        self._enabled = enabled
        self._path = logs_dir / self._FILENAME

    # ------------------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def path(self) -> Path:
        return self._path

    # ------------------------------------------------------------------
    def log(self, event: str, data: dict[str, Any] | None = None) -> None:
        """Record an event if logging is enabled.

        ``data`` must not contain usernames, IP addresses, or personal data.
        """
        if not self._enabled:
            return
        entry = {
            "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "event": event,
        }
        if data:
            entry["data"] = data
        self._write(entry)

    # ------------------------------------------------------------------
    def _write(self, entry: dict[str, Any]) -> None:
        try:
            self._logs_dir.mkdir(parents=True, exist_ok=True)
            if self._path.exists() and self._path.stat().st_size >= self._MAX_BYTES:
                self._path.replace(self._path.with_suffix(".jsonl.1"))
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except Exception as exc:  # pragma: no cover – I/O failure is non-fatal
            logger.debug("EventLogger write failed: {}", exc)


# ---------------------------------------------------------------------------
# Diagnostics bundle export
# ---------------------------------------------------------------------------


def _system_info() -> dict[str, str]:
    """Return basic, anonymised system metadata."""
    return {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "python_version": sys.version,
        "app_version": _get_app_version(),
    }


def _get_app_version() -> str:
    try:
        from importlib.metadata import version

        return version("mtgo_tools")
    except Exception:
        pass
    try:
        from utils.constants import APP_VERSION  # type: ignore[import-untyped]

        return str(APP_VERSION)
    except Exception:
        pass
    return "unknown"


def export_diagnostics_bundle(
    output_path: Path,
    *,
    logs_dir: Path,
    notes: str = "",
    include_events: bool = True,
) -> Path:
    """Package log files and system info into a zip archive.

    No network activity.  The resulting file can be shared manually.
    """
    output_path = output_path.with_suffix(".zip") if output_path.suffix != ".zip" else output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # System info
        zf.writestr(
            "system_info.json",
            json.dumps(_system_info(), indent=2),
        )

        # User notes
        if notes.strip():
            zf.writestr("notes.txt", notes.strip())

        # Log files
        if logs_dir.is_dir():
            for log_file in sorted(logs_dir.glob("mtgo_tools_*.log")):
                zf.write(log_file, f"logs/{log_file.name}")

            # Event log
            if include_events:
                for events_file in sorted(logs_dir.glob("events.jsonl*")):
                    zf.write(events_file, f"logs/{events_file.name}")

    logger.info("Diagnostics bundle written to {}", output_path)
    return output_path
