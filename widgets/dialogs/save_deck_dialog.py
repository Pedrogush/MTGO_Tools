"""The Save Deck details dialog: which format, and which archetype (issue #1034).

Why a dialog of its own, ahead of the native Save As
----------------------------------------------------
The file name and folder belong to Windows' own Save As dialog -- that is where
people expect to type a name, create a folder, or see what is already there, and
it is what honours the default deck folder. What that dialog cannot hold is a
choice that depends on another choice: ``wx.FileDialog``'s customisation hook
(``wxFileDialogCustomize``) can add a ``wxFileDialogChoice``, but only with a
fixed item list given at creation -- it has no way to repopulate one. The
archetype list is per format, so it would go stale the moment the format was
corrected. Two short steps it is: this dialog for the metadata, then Save As.

Where the archetype list comes from
-----------------------------------
The dialog does not know. It is handed ``load_archetypes(format, deliver)``,
which the app wires to the metagame repository's archetype list -- the same one
the research panel shows, served from the remote bundle -- and which may answer
synchronously (a cached or in-memory list) or later, from a worker thread
marshalled back onto the UI thread. Deliveries for a format the user has since
moved away from are dropped.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import wx

from utils.constants import SPACE_MD, SPACE_SM, SPACE_XS
from widgets.stylize import (
    init_top_level_window,
    stylize_button,
    stylize_choice,
    stylize_label,
    surface_colour,
)

#: Content width. Matches the preferences dialog so the two read as one family.
SAVE_DECK_DIALOG_WIDTH = 420

ArchetypeLoader = Callable[[str, Callable[[list[str]], None]], None]


class SaveDeckDialog(wx.Dialog):
    """Pick the saved deck's format (pre-detected) and, optionally, its archetype."""

    def __init__(
        self,
        parent: wx.Window | None,
        *,
        formats: Sequence[str],
        initial_format: str,
        initial_archetype: str = "",
        load_archetypes: ArchetypeLoader,
        t: Callable[..., str],
    ) -> None:
        self._translate = t
        super().__init__(parent, title=self._t("deck_actions.save_deck"))
        init_top_level_window(self)
        self.SetBackgroundColour(surface_colour("base"))

        self._formats = list(formats)
        if initial_format and initial_format not in self._formats:
            self._formats.append(initial_format)
        self._load_archetypes = load_archetypes
        self._initial_format = initial_format
        self._initial_archetype = initial_archetype.strip()
        # The names behind archetype_choice's items 1..n (item 0 is "(none)").
        self._archetype_names: list[str] = []
        self._requested_format = ""

        outer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(outer)
        body = wx.BoxSizer(wx.VERTICAL)
        outer.Add(body, 0, wx.EXPAND | wx.ALL, SPACE_MD)

        format_label = wx.StaticText(self, label=self._t("deck_save.format"))
        stylize_label(format_label, level="body", surface="base", tone="primary")
        body.Add(format_label, 0, wx.EXPAND)
        self.format_choice = wx.Choice(self, choices=self._formats)
        stylize_choice(self.format_choice)
        if initial_format in self._formats:
            self.format_choice.SetSelection(self._formats.index(initial_format))
        elif self._formats:
            self.format_choice.SetSelection(0)
        self.format_choice.Bind(wx.EVT_CHOICE, self._on_format_changed)
        body.Add(self.format_choice, 0, wx.EXPAND | wx.TOP, SPACE_XS)
        self._add_help(body, self._t("deck_save.format_help"))

        body.AddSpacer(SPACE_MD)
        archetype_label = wx.StaticText(self, label=self._t("deck_save.archetype"))
        stylize_label(archetype_label, level="body", surface="base", tone="primary")
        body.Add(archetype_label, 0, wx.EXPAND)
        self.archetype_choice = wx.Choice(self, choices=[self._t("deck_save.archetype_none")])
        stylize_choice(self.archetype_choice)
        self.archetype_choice.SetSelection(0)
        body.Add(self.archetype_choice, 0, wx.EXPAND | wx.TOP, SPACE_XS)
        self.archetype_help = self._add_help(body, "")

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.AddStretchSpacer(1)
        cancel_btn = wx.Button(self, wx.ID_CANCEL, label=self._t("deck_save.cancel"))
        stylize_button(cancel_btn, kind="secondary")
        buttons.Add(cancel_btn, 0, wx.RIGHT, SPACE_SM)
        self.ok_button = wx.Button(self, wx.ID_OK, label=self._t("deck_save.continue"))
        stylize_button(self.ok_button, kind="primary")
        self.ok_button.SetDefault()
        buttons.Add(self.ok_button, 0)
        outer.Add(buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_MD)

        width = self.FromDIP(SAVE_DECK_DIALOG_WIDTH)
        self.SetClientSize((width, outer.GetMinSize().GetHeight()))
        self.Layout()
        self.SetClientSize((width, outer.GetMinSize().GetHeight()))
        self.SetMinSize(self.GetSize())
        self.CentreOnParent()

        self._request_archetypes(self.selected_format())

    # ------------------------------------------------------------------ public
    def selected_format(self) -> str:
        index = self.format_choice.GetSelection()
        if 0 <= index < len(self._formats):
            return self._formats[index]
        return ""

    def selected_archetype(self) -> str:
        """The chosen archetype's name, or ``""`` when left on "(none)"."""
        index = self.archetype_choice.GetSelection()
        if 1 <= index <= len(self._archetype_names):
            return self._archetype_names[index - 1]
        return ""

    def archetype_names(self) -> list[str]:
        """The names currently offered, in order. Exists for tests and captures."""
        return list(self._archetype_names)

    # ------------------------------------------------------------------ internals
    def _t(self, key: str, **kwargs: object) -> str:
        return self._translate(key, **kwargs)

    def _add_help(self, sizer: wx.BoxSizer, text: str) -> wx.StaticText:
        help_label = wx.StaticText(self, label=text)
        stylize_label(help_label, level="caption", surface="base", tone="secondary")
        help_label.Wrap(self.FromDIP(SAVE_DECK_DIALOG_WIDTH) - SPACE_MD * 2)
        sizer.Add(help_label, 0, wx.EXPAND | wx.TOP, SPACE_XS)
        return help_label

    def _set_archetype_help(self, text: str) -> None:
        self.archetype_help.SetLabel(text)
        self.archetype_help.Wrap(self.FromDIP(SAVE_DECK_DIALOG_WIDTH) - SPACE_MD * 2)
        self.Layout()

    def _on_format_changed(self, _event: wx.CommandEvent | None = None) -> None:
        self._request_archetypes(self.selected_format())

    def _request_archetypes(self, mtg_format: str) -> None:
        self._requested_format = mtg_format
        self.archetype_choice.Disable()
        self._set_archetype_help(self._t("deck_save.archetype_loading"))
        if not mtg_format:
            self._on_archetypes(mtg_format, [])
            return
        self._load_archetypes(
            mtg_format, lambda names, fmt=mtg_format: self._on_archetypes(fmt, names)
        )

    def _on_archetypes(self, mtg_format: str, names: list[str]) -> None:
        # A late delivery can land after the dialog closed (worker thread ->
        # CallAfter), or after the user switched formats again.
        if not self or mtg_format != self._requested_format:
            return
        previous = self.selected_archetype()
        unique = sorted({name.strip() for name in names if name and name.strip()}, key=str.lower)
        is_initial_format = mtg_format == self._initial_format
        # A deck saved with an archetype that has since dropped off the metagame
        # list keeps it: re-saving must not silently erase what was recorded.
        if is_initial_format and self._initial_archetype and self._initial_archetype not in unique:
            unique.append(self._initial_archetype)
        if previous in unique:
            wanted = previous
        else:
            wanted = self._initial_archetype if is_initial_format else ""
        self._archetype_names = unique
        self.archetype_choice.Set([self._t("deck_save.archetype_none"), *unique])
        self.archetype_choice.SetSelection(unique.index(wanted) + 1 if wanted in unique else 0)
        self.archetype_choice.Enable()
        if unique:
            self._set_archetype_help(self._t("deck_save.archetype_help", format=mtg_format))
        else:
            self._set_archetype_help(self._t("deck_save.archetype_unavailable", format=mtg_format))


__all__ = ["SAVE_DECK_DIALOG_WIDTH", "SaveDeckDialog"]
