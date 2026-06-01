"""Bridge discovery / process resolution for the MTGO bridge CLI.

Locates the compiled ``MTGOBridge.exe`` from explicit paths, the
``MTGO_BRIDGE_PATH`` environment variable, or known install/dev build
locations.
"""

from __future__ import annotations

import os
from pathlib import Path

# Manual download URL shown to users when the bridge is missing.
BRIDGE_MANUAL_DOWNLOAD_URL = "https://github.com/Pedrogush/MTGOBridge/releases/latest"


def _installed_app_dir() -> Path | None:
    """Return the directory containing the running executable, if determinable."""
    import sys

    exe = getattr(sys, "frozen", False) and sys.executable
    if exe:
        return Path(exe).parent
    return None


def _default_bridge_candidates() -> list[Path]:
    """Return probe paths for MTGOBridge.exe in priority order.

    Order:
    1. Install-time path: ``{app_dir}/mtgo_integration/MTGOBridge.exe``
    2. Local dev build paths (Release then Debug)
    """
    candidates: list[Path] = []

    app_dir = _installed_app_dir()
    if app_dir is not None:
        candidates.append(app_dir / "mtgo_integration" / "MTGOBridge.exe")

    candidates += [
        Path("dotnet/MTGOBridge/bin/Release/net9.0-windows7.0/win-x64/publish/MTGOBridge.exe"),
        Path("dotnet/MTGOBridge/bin/Release/net9.0-windows7.0/MTGOBridge.exe"),
        Path("dotnet/MTGOBridge/bin/Debug/net9.0-windows7.0/win-x64/publish/MTGOBridge.exe"),
        Path("dotnet/MTGOBridge/bin/Debug/net9.0-windows7.0/MTGOBridge.exe"),
    ]
    return candidates


def _resolve_bridge_path(explicit: str | os.PathLike[str] | None = None) -> Path | None:
    if explicit:
        candidate = Path(explicit)
        if candidate.exists():
            return candidate
        return None

    env_path = os.getenv("MTGO_BRIDGE_PATH")
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate

    for candidate in _default_bridge_candidates():
        if candidate.exists():
            return candidate
    return None


def _require_bridge_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    resolved = _resolve_bridge_path(explicit)
    if resolved is None:
        raise FileNotFoundError(
            "MTGO bridge executable not found. "
            "Set MTGO_BRIDGE_PATH, build the project, or download the bridge from: "
            f"{BRIDGE_MANUAL_DOWNLOAD_URL}"
        )
    return resolved
