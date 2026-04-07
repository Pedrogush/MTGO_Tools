"""Filesystem persistence for current deck and saved deck files."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from utils.atomic_io import atomic_write_text, locked_path
from utils.constants import CURR_DECK_FILE, DECKS_DIR
from utils.deck import sanitize_filename

LEGACY_CURR_DECK_CACHE = Path("cache") / "curr_deck.txt"
LEGACY_CURR_DECK_ROOT = Path("curr_deck.txt")


class DeckFileStore:
    """Store for deck files on disk."""

    def __init__(
        self,
        *,
        current_deck_file: Path = CURR_DECK_FILE,
        decks_dir: Path = DECKS_DIR,
        legacy_current_deck_files: tuple[Path, ...] | None = None,
    ) -> None:
        self.current_deck_file = current_deck_file
        self.decks_dir = decks_dir
        self.legacy_current_deck_files = legacy_current_deck_files or (
            LEGACY_CURR_DECK_CACHE,
            LEGACY_CURR_DECK_ROOT,
        )

    def read_current_deck_file(self) -> str:
        candidates = [self.current_deck_file, *self.legacy_current_deck_files]
        for candidate in candidates:
            if candidate.exists():
                with locked_path(candidate):
                    with candidate.open("r", encoding="utf-8") as fh:
                        contents = fh.read()
                if candidate != self.current_deck_file:
                    self._migrate_current_deck_file(candidate, contents)
                return contents
        raise FileNotFoundError("Current deck file not found")

    def _migrate_current_deck_file(self, legacy_path: Path, contents: str) -> None:
        try:
            atomic_write_text(self.current_deck_file, contents)
            try:
                legacy_path.unlink()
            except OSError:
                logger.debug(f"Unable to remove legacy deck file {legacy_path}")
        except OSError as exc:
            logger.debug(f"Failed to migrate curr_deck.txt from {legacy_path}: {exc}")

    def save_deck_to_file(
        self, deck_name: str, deck_content: str, directory: Path | None = None
    ) -> Path:
        directory = directory or self.decks_dir
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
        directory = directory or self.decks_dir

        if not directory.exists():
            return []

        return sorted(directory.glob("*.txt"))
