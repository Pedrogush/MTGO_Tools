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
    DeckVcsService,
    ExternalEdit,
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
        """Load a checked-out version's decklist into the deck workspace.

        The graph is repainted by the load itself, which wakes whichever deck
        tab is on screen -- and after a checkout that is this one.
        """
        self._on_deck_content_ready(deck_text, source="file")

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

        The identification reads and fingerprints a blob per commit, so it runs
        on the background worker: a deck with a long history used to hold the
        load up while every version was hashed. The deck is on screen by the
        time the answer arrives, and only the prompt needs the UI thread.
        """
        deck_key = deck_key_for(self.controller.deck_repo.get_current_deck(), file_path)
        service = get_deck_vcs_service()

        def work() -> ExternalEdit:
            return service.identify(deck_key, deck_text)

        def done(verdict: ExternalEdit) -> None:
            if verdict.status is not ExternalEditStatus.UNATTRIBUTED:
                logger.info(f"Loaded deck matches history: {deck_key} ({verdict.status.value})")
                return
            self._offer_to_record(service, deck_key, deck_text)

        def failed(exc: Exception) -> None:  # the file itself already loaded
            logger.warning(f"Could not identify deck version for {file_path}: {exc}")

        worker = getattr(self.controller, "_worker", None)
        if worker is None:
            try:
                done(work())
            except Exception as exc:  # noqa: BLE001
                failed(exc)
            return
        worker.submit(work, on_success=done, on_error=failed)

    def _offer_to_record(
        self: AppFrame, service: DeckVcsService, deck_key: str, deck_text: str
    ) -> None:
        """Ask whether an unrecognised decklist should become a version."""
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
