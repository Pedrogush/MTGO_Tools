"""Version-history handlers: reloading after a checkout, and unrecognised files.

Two jobs, both at the seam between the history and the rest of the frame.

A checkout rewrites the user's decklist file, so the zones showing the old
decklist are stale the moment it returns -- :meth:`_on_history_checkout` is what
puts the new one on screen through the same path a file load uses.

:meth:`_check_external_edit` covers the case the doc calls out: a ``.txt`` the
user edited outside the app. Because the file deliberately carries no version
metadata, the only way to tell whether it is a version already held is to hash
its normalized content and look. If it is not there, the user is *asked* --
guessing would either invent a version they did not make or bury an edit they did.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
from loguru import logger

from services.deck_vcs_service import (
    ExternalEditStatus,
    deck_key_for,
    get_deck_vcs_service,
)

if TYPE_CHECKING:
    from pathlib import Path

    from widgets.frames.app_frame import AppFrame
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class DeckHistoryHandlers(_Base):
    """Frame-side reactions to version-history actions."""

    def _on_history_checkout(self: AppFrame, deck_text: str) -> None:
        """Load a checked-out version's decklist into the deck workspace."""
        self._on_deck_content_ready(deck_text, source="file")
        self.refresh_deck_history()

    def refresh_deck_history(self: AppFrame) -> None:
        """Repaint the version graph, if the tab has been built."""
        panel = getattr(self, "deck_history_panel", None)
        if panel is None:
            return
        try:
            panel.refresh_history()
        except Exception as exc:  # noqa: BLE001 - a graph problem must not break a save
            logger.warning(f"Could not refresh deck history: {exc}")

    def _check_external_edit(self: AppFrame, file_path: Path, deck_text: str) -> None:
        """Offer to record a decklist that the history has never seen.

        Only asks when there *is* a history to compare against: a deck being
        opened for the first time is not an "external edit", it is just a deck.
        """
        deck_key = deck_key_for(self.controller.deck_repo.get_current_deck(), file_path)
        service = get_deck_vcs_service()
        try:
            verdict = service.identify(deck_key, deck_text)
        except Exception as exc:  # noqa: BLE001 - the file itself already loaded
            logger.warning(f"Could not identify deck version for {file_path}: {exc}")
            return

        if verdict.status is not ExternalEditStatus.UNATTRIBUTED:
            logger.info(f"Loaded deck matches history: {deck_key} ({verdict.status.value})")
            return

        answer = wx.MessageBox(
            self._t("history.external.prompt"),
            self._t("history.external.title"),
            wx.YES_NO | wx.ICON_QUESTION,
        )
        if answer != wx.YES:
            return
        try:
            service.attach_unattributed(deck_key, deck_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Could not record external edit for {deck_key}: {exc}")
            return
        self.refresh_deck_history()
