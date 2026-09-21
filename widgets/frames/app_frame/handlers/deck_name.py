"""Frame-side deck-name display and editing.

The name is one piece of state shown in two places -- the deck tables header and
the history tab's toolbar -- so both are repainted from the record rather than
from each other, and either can start an edit. Everything about what a name *is*
(sanitizing, the empty-means-unset rule, which file it implies) lives in
:mod:`services.deck_name`; this module is the wx around it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
from loguru import logger

from services.deck_name import clean_deck_name, deck_name_of, set_deck_name

if TYPE_CHECKING:
    from widgets.frames.app_frame import AppFrame
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class DeckNameHandlers(_Base):
    """Show the deck's name, and let the user set or change it."""

    def current_deck_name(self: AppFrame) -> str:
        """The loaded deck's name, or ``""`` when it has none."""
        return deck_name_of(self.controller.deck_repo.get_current_deck())

    def deck_name_display_text(self: AppFrame) -> str:
        """What the name reads as on screen.

        The placeholder is produced *here*, on the way to a label, and is never
        stored: an unnamed deck holds ``""`` so it cannot be keyed, saved, or
        confused for a deck the user actually named.
        """
        return self.current_deck_name() or self._t("deck_name.unset")

    def refresh_deck_name_displays(self: AppFrame) -> None:
        """Repaint every view of the name from the record.

        One piece of state, two views: the mainboard header and the history
        tab. Both are written from the record rather than from each other, so
        neither can drift, and a view that has not been built yet is simply
        skipped.
        """
        text = self.deck_name_display_text()
        named = bool(self.current_deck_name())

        main_table = getattr(self, "main_table", None)
        label = getattr(main_table, "deck_name_label", None) if main_table else None
        if label is not None:
            try:
                label.set_name(text, named=named)
            except RuntimeError:  # pragma: no cover - window already destroyed
                pass

        history = getattr(self, "deck_history_panel", None)
        if history is not None:
            try:
                history.set_deck_name_text(text, named=named)
            except RuntimeError:  # pragma: no cover - window already destroyed
                pass

    def on_deck_name_clicked(self: AppFrame) -> None:
        """Ask for a new name, and adopt it if the user gives one.

        Renaming does not touch the file or the history the deck already has --
        the new name simply points the *next* save at a new file, and therefore
        at a new history. Nothing is moved, rewritten or deleted, so a rename
        can never orphan versions the user still has.
        """
        deck = self.controller.deck_repo.get_current_deck()
        if deck is None:
            wx.MessageBox(
                self._t("deck_name.no_deck"),
                self._t("deck_name.title"),
                wx.OK | wx.ICON_INFORMATION,
            )
            return

        current = deck_name_of(deck)
        dlg = wx.TextEntryDialog(
            self,
            self._t("deck_name.prompt"),
            self._t("deck_name.title"),
            value=current,
        )
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return
            typed = dlg.GetValue()
        finally:
            dlg.Destroy()

        cleaned = clean_deck_name(typed)
        if not cleaned:
            wx.MessageBox(
                self._t("deck_name.rejected"),
                self._t("deck_name.title"),
                wx.OK | wx.ICON_WARNING,
            )
            return
        if cleaned == current:
            return

        set_deck_name(deck, cleaned)
        logger.info(f"Deck renamed: {current or '(unnamed)'} -> {cleaned}")
        self.refresh_deck_name_displays()
        self._set_status("app.status.deck_renamed", name=cleaned)
        # The name decides the key, so the history the tab should be showing
        # changed even though nothing was written.
        self.refresh_deck_history()


__all__ = ["DeckNameHandlers"]
