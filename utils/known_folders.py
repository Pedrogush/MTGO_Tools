"""The user's Documents folder, as Windows itself names it.

``Path.home() / "Documents"`` is only the *default* location. Windows lets that
folder be moved -- Folder Redirection on a domain, OneDrive's "Back up your
Documents folder", or a user simply dragging it to another drive in its
Properties dialog -- and after any of those the literal path either does not
exist or is a stale, empty folder the user never looks at. The shell's known
folder API (``SHGetKnownFolderPath(FOLDERID_Documents)``) is the one answer that
follows the move, and it is where Windows' own file dialogs send a new
application that has no recent folder of its own.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

#: ``FOLDERID_Documents`` -- ``{FDD39AD0-238F-46AF-ADB4-6C85480369C7}`` (KnownFolders.h).
_FOLDERID_DOCUMENTS = "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"


def _known_folder_path(folder_id: str) -> Path | None:
    """Resolve a Windows known folder GUID, or ``None`` when the shell cannot."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        guid = GUID()
        ole32 = ctypes.windll.ole32
        if ole32.CLSIDFromString(ctypes.c_wchar_p(folder_id), ctypes.byref(guid)) != 0:
            return None
        raw = ctypes.c_wchar_p()
        shell32 = ctypes.windll.shell32
        result = shell32.SHGetKnownFolderPath(
            ctypes.byref(guid), wintypes.DWORD(0), wintypes.HANDLE(0), ctypes.byref(raw)
        )
        try:
            if result != 0 or not raw.value:
                return None
            return Path(raw.value)
        finally:
            # The shell allocates the string; the caller frees it, success or not.
            ole32.CoTaskMemFree(raw)
    except (OSError, AttributeError, ValueError) as exc:
        logger.debug(f"Known folder lookup failed for {folder_id}: {exc}")
        return None


def documents_dir() -> Path:
    """The user's Documents folder, falling back to the home directory.

    Order: the shell's ``FOLDERID_Documents`` when it resolves to a real
    directory; then ``~/Documents``; then ``~`` itself, which always exists.
    """
    known = _known_folder_path(_FOLDERID_DOCUMENTS)
    if known is not None and known.is_dir():
        return known
    fallback = Path.home() / "Documents"
    if fallback.is_dir():
        return fallback
    return Path.home()


__all__ = ["documents_dir"]
