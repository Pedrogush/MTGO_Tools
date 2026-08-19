"""The preferences dialog (§4.7).

What this replaces
------------------
The unlabeled gear popup held twelve items mixing three taxonomies. Phase 3b
(#968) split them by taxonomy into a menu bar and noted that ``Settings`` was a
top-level menu *only* so that this phase could collapse it into one
``Preferences…`` item. This is that dialog.

Why a dialog rather than a better menu
--------------------------------------
A menu can show a label and a check mark and nothing else. Four of the five
settings here are one-of-N choices whose options are not self-explanatory
("Karsten's" vs "Arithmetic"; "Both" vs "MTGGoldfish" vs "MTGO.com"), and a
radio submenu shows you the current value only after you have opened it and
found the tick. A dialog shows every setting, its current value **and** a
sentence of explanation at once — which is the reason the review called the gear
"one flat list mixing actions, navigation/help and preferences" rather than
merely "too long".

What is *not* here
------------------
``Load Collection``, ``Enable Offline Images Mode``, ``Update Card Database`` and
``Export Diagnostics`` are **actions**: they do something once and finish, they
have progress and failure, and two of them open dialogs of their own. They stay
in ``File``. A preference is a value that persists and changes how the app
behaves afterwards; nothing in this dialog has a "run" verb.

Apply-on-change, not OK/Cancel
------------------------------
Every control writes through immediately, exactly as its menu item did. Two
reasons: the settings already applied live from the menu, so an OK/Cancel model
would be a behaviour change rather than a presentation one; and ``Language``
re-translates the running UI (including this dialog's parent menu bar) the moment
it is set, so a "Cancel" would have to unwind a re-translation. The one button is
``Close``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import wx

from utils.constants import SPACE_MD, SPACE_SM, SPACE_XS
from widgets.checkbox import DarkCheckBox
from widgets.preferences.spec import Preference, PreferenceGroup
from widgets.section import SectionPanel
from widgets.stylize import (
    init_top_level_window,
    stylize_button,
    stylize_checkbox,
    stylize_choice,
    stylize_label,
    surface_colour,
)

#: The dialog's content width. Wide enough that no help sentence wraps to more
#: than two lines at the 10pt base, narrow enough to stay a dialog.
PREFERENCES_DIALOG_WIDTH = 460


class PreferencesDialog(wx.Dialog):
    """Renders a :mod:`widgets.preferences.spec` tree into real controls."""

    def __init__(
        self,
        parent: wx.Window | None,
        groups: Sequence[PreferenceGroup],
        *,
        title: str = "Preferences",
        close_label: str = "Close",
    ) -> None:
        super().__init__(parent, title=title)
        # Must be the first statement after super().__init__(): a child captures
        # its parent's font when it is constructed, and the dark caption is
        # non-client area phase 1's process dark mode never reached.
        init_top_level_window(self)
        self.SetBackgroundColour(surface_colour("base"))

        self._groups = list(groups)
        self._controls: dict[str, wx.Window] = {}

        outer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(outer)

        for index, group in enumerate(self._groups):
            section = SectionPanel(self, title=group.title, padding=SPACE_SM)
            for item_index, item in enumerate(group.items):
                if item_index:
                    section.sizer.AddSpacer(SPACE_MD)
                self._add_item(section, item)
            outer.Add(
                section,
                0,
                wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP,
                SPACE_MD if index == 0 else SPACE_SM,
            )

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.AddStretchSpacer(1)
        close_btn = wx.Button(self, wx.ID_CANCEL, label=close_label)
        # The only button on the surface, and it is what the user came here to
        # press when they are done -- so it is the primary, not a grey escape
        # hatch beside an absent OK.
        stylize_button(close_btn, kind="primary")
        close_btn.SetDefault()
        buttons.Add(close_btn, 0)
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, SPACE_MD)

        self.SetClientSize(self._preferred_client_size(outer))
        self.SetMinSize(self.GetSize())
        self.Centre()

    # ------------------------------------------------------------------
    def _preferred_client_size(self, outer: wx.Sizer) -> wx.Size:
        width = self.FromDIP(PREFERENCES_DIALOG_WIDTH)
        # Ask the sizer how tall it wants to be *at* that width rather than at
        # its own best width: every help label is wrapped to the content width,
        # so a best-size query taken before the wrap reports a single-line row.
        self.SetClientSize((width, outer.GetMinSize().GetHeight()))
        self.Layout()
        return wx.Size(width, outer.GetMinSize().GetHeight())

    def _add_item(self, section: SectionPanel, item: Preference) -> None:
        body = section.body
        if item.kind == "toggle":
            check = DarkCheckBox(body, label=item.label)
            stylize_checkbox(check, surface="panel")
            check.SetValue(item.checked)
            check.Bind(
                wx.EVT_CHECKBOX,
                lambda evt, pref=item: self._on_toggle(pref, evt.IsChecked()),
            )
            section.sizer.Add(check, 0, wx.EXPAND)
            self._controls[item.key] = check
            self._add_help(section, item.help, indent=check.GetMinSize().GetHeight() + SPACE_XS)
            return

        label = wx.StaticText(body, label=item.label)
        stylize_label(label, level="body", surface="panel", tone="primary")
        section.sizer.Add(label, 0, wx.EXPAND)

        choice = wx.Choice(body, choices=[option_label for _value, option_label in item.options])
        stylize_choice(choice)
        values = [value for value, _label in item.options]
        if item.current in values:
            choice.SetSelection(values.index(item.current))
        choice.Bind(
            wx.EVT_CHOICE,
            lambda evt, pref=item, vals=values: self._on_choice(pref, vals, evt.GetSelection()),
        )
        section.sizer.Add(choice, 0, wx.EXPAND | wx.TOP, SPACE_XS)
        self._controls[item.key] = choice
        self._add_help(section, item.help)

    def _add_help(self, section: SectionPanel, text: str, *, indent: int = 0) -> None:
        if not text:
            return
        help_label = wx.StaticText(section.body, label=text)
        stylize_label(help_label, level="caption", surface="panel", tone="secondary")
        help_label.Wrap(self.FromDIP(PREFERENCES_DIALOG_WIDTH) - SPACE_MD * 4 - indent)
        section.sizer.Add(help_label, 0, wx.EXPAND | wx.TOP | wx.LEFT, SPACE_XS)

    # ------------------------------------------------------------------
    def _on_choice(self, pref: Preference, values: list[str], selection: int) -> None:
        if pref.on_select is None or not 0 <= selection < len(values):
            return
        pref.on_select(values[selection])

    def _on_toggle(self, pref: Preference, checked: bool) -> None:
        if pref.on_toggle is not None:
            pref.on_toggle(checked)

    def control_for(self, key: str) -> wx.Window | None:
        """The rendered control for ``key``. Exists for tests and captures."""
        return self._controls.get(key)


def show_preferences_dialog(
    parent: wx.Window,
    groups: Sequence[PreferenceGroup],
    *,
    title: str = "Preferences",
    close_label: str = "Close",
    on_closed: Callable[[], None] | None = None,
) -> None:
    """Open the preferences dialog modally and run ``on_closed`` afterwards."""
    dialog = PreferencesDialog(parent, groups, title=title, close_label=close_label)
    try:
        dialog.ShowModal()
    finally:
        dialog.Destroy()
    if on_closed is not None:
        on_closed()


__all__ = ["PREFERENCES_DIALOG_WIDTH", "PreferencesDialog", "show_preferences_dialog"]
