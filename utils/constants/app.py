"""Application-level constants."""

from utils.constants.paths import resource_path

BRIDGE_PATH = "dotnet/MTGOBridge/bin/Release/net9.0-windows7.0/win-x64/MTGOBridge.exe"
APP_NAME = "MTGO Tools"

# Deck hash display — number of characters shown in status messages
DECK_HASH_DISPLAY_LENGTH = 8


def _read_app_version() -> str:
    """Return the version this build was cut from.

    The repo-root ``VERSION`` file is the single source of truth (docs/VERSIONING.md);
    ``packaging/mtgo_tools.spec`` bundles it as a data file so the same read works
    from source and from a frozen build.

    ``"unknown"`` rather than a fake ``0.0.0`` on failure: that string is what the
    diagnostics bundle prints, and it parses as *no* version at all, so the update
    check declines to compare instead of reporting a bogus "update available".
    """
    try:
        version = resource_path("VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return version or "unknown"


APP_VERSION = _read_app_version()
