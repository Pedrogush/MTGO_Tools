from pathlib import Path

from loguru import logger

from utils import constants
from utils.atomic_io import atomic_write_text, locked_path

LEGACY_CURR_DECK_CACHE = Path("cache") / "curr_deck.txt"
LEGACY_CURR_DECK_ROOT = Path("curr_deck.txt")


def sanitize_filename(filename: str, fallback: str = "saved_deck") -> str:
    """
    Sanitize a filename by removing invalid characters and preventing path traversal.

    Handles:
    - Null bytes
    - Path traversal attempts (../, drive letters)
    - Invalid filesystem characters
    - Reserved Windows filenames
    - Leading/trailing dots and spaces

    Args:
        filename: Original filename
        fallback: Default filename if result is empty

    Returns:
        Sanitized filename safe for filesystem use
    """
    # Replace null bytes with underscores
    filename = filename.replace("\x00", "_")

    # Replace invalid filesystem characters (preserve spaces)
    safe_name = "".join(ch if ch not in '\\/:*?"<>|' else "_" for ch in filename)

    # Prevent path traversal by collapsing consecutive dots and removing leading dots
    # This prevents "..", "..." and leading "." while allowing single dots in filenames
    import re

    # Replace sequences of 2+ dots with single underscore
    safe_name = re.sub(r"\.{2,}", "_", safe_name)
    # Remove leading dots
    safe_name = safe_name.lstrip(".")

    # Collapse consecutive underscores into single underscore
    safe_name = re.sub(r"_{2,}", "_", safe_name)

    # Strip leading/trailing whitespace, dots, and underscores
    safe_name = safe_name.strip().strip("._")

    # Check for reserved Windows filenames (case-insensitive)
    # Split on dots to check the base name (before any extension)
    base_name = safe_name.split(".")[0] if "." in safe_name else safe_name
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
    if base_name.upper() in reserved:
        safe_name = f"_{safe_name}"

    # If the result is empty or only underscores/whitespace, use fallback
    if not safe_name or not safe_name.replace("_", "").replace(".", "").strip():
        return fallback

    return safe_name


def sanitize_zone_cards(entries: list) -> list[dict[str, int | float | str]]:
    """
    Validate and sanitize zone card entries.

    Filters out invalid entries and ensures all cards have valid names and quantities.

    Args:
        entries: List of card entries (each should be a dict with 'name' and 'qty')

    Returns:
        List of validated card dictionaries with 'name' (str) and 'qty' (int or float) keys
    """
    sanitized: list[dict[str, int | float | str]] = []

    for entry in entries:
        # Skip non-dict entries
        if not isinstance(entry, dict):
            continue

        name = entry.get("name")
        qty_raw = entry.get("qty", 0)

        # Skip entries without a name
        if not name:
            continue

        # Parse and preserve float quantities from average decks
        try:
            qty_float = float(qty_raw)
            # Convert to int only if it's a whole number
            qty = int(qty_float) if qty_float.is_integer() else qty_float
            qty = max(0, qty)
        except (TypeError, ValueError):
            continue

        # Skip zero-quantity entries
        if qty <= 0:
            continue

        sanitized.append({"name": name, "qty": qty})

    return sanitized


def read_curr_deck_file() -> str:
    curr_deck_file = constants.CURR_DECK_FILE
    candidates = [curr_deck_file, LEGACY_CURR_DECK_CACHE, LEGACY_CURR_DECK_ROOT]
    for candidate in candidates:
        if candidate.exists():
            with locked_path(candidate):
                with candidate.open("r", encoding="utf-8") as fh:
                    contents = fh.read()
            if candidate != curr_deck_file:
                try:
                    atomic_write_text(curr_deck_file, contents)
                    try:
                        candidate.unlink()
                    except OSError:
                        logger.debug(f"Unable to remove legacy deck file {candidate}")
                except OSError as exc:  # pragma: no cover
                    logger.debug(f"Failed to migrate curr_deck.txt from {candidate}: {exc}")
            return contents
    raise FileNotFoundError("Current deck file not found")
