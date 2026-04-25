"""Deck text file read/write and legacy-path migration."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from utils.atomic_io import atomic_write_text, locked_path
from utils.constants import CURR_DECK_FILE, DECKS_DIR
from utils.deck import sanitize_filename

if TYPE_CHECKING:
    from repositories.deck_repository.protocol import DeckRepositoryProto

    _Base = DeckRepositoryProto
else:
    _Base = object

# Legacy file paths for migration
LEGACY_CURR_DECK_CACHE = Path("cache") / "curr_deck.txt"
LEGACY_CURR_DECK_ROOT = Path("curr_deck.txt")


class FilesystemMixin(_Base):
    """Filesystem I/O for deck text files plus one-off legacy migration."""

    def read_current_deck_file(self) -> str:
        candidates = [CURR_DECK_FILE, LEGACY_CURR_DECK_CACHE, LEGACY_CURR_DECK_ROOT]
        for candidate in candidates:
            if candidate.exists():
                with locked_path(candidate):
                    with candidate.open("r", encoding="utf-8") as fh:
                        contents = fh.read()
                if candidate != CURR_DECK_FILE:
                    try:
                        atomic_write_text(CURR_DECK_FILE, contents)
                        try:
                            candidate.unlink()
                        except OSError:
                            logger.debug(f"Unable to remove legacy deck file {candidate}")
                    except OSError as exc:
                        logger.debug(f"Failed to migrate curr_deck.txt from {candidate}: {exc}")
                return contents
        raise FileNotFoundError("Current deck file not found")

    def save_deck_to_file(
        self, deck_name: str, deck_content: str, directory: Path | None = None
    ) -> Path:
        if directory is None:
            directory = DECKS_DIR

        directory.mkdir(parents=True, exist_ok=True)

        safe_name = sanitize_filename(deck_name, fallback="saved_deck")
        file_path = directory / f"{safe_name}.txt"

        counter = 1
        while file_path.exists():
            file_path = directory / f"{safe_name}_{counter}.txt"
            counter += 1

        atomic_write_text(file_path, deck_content)

        logger.info(f"Saved deck to file: {file_path}")
        return file_path

    def list_deck_files(self, directory: Path | None = None) -> list[Path]:
        if directory is None:
            directory = DECKS_DIR

        if not directory.exists():
            return []

        return sorted(directory.glob("*.txt"))
