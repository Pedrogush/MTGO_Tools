"""The in-app updater's window: confirm, then download, then hand over (issue #142).

Why this is one modeless window
-------------------------------
Every other dialog in the app is modal, and this one is not, for a reason that
outlives the dialog: the thing it does takes minutes. A 175 MB transfer behind a
modal loop would freeze the whole app for the length of the download -- for an
app people open mid-tournament to look decks up, that is worse than the update
being deferred. Modeless also keeps this off the "nested modal loops" ground
``docs/WXMSW_BEHAVIOUR.md`` documents: the Help-menu entry opens it from inside
``PopupMenu``'s own message drain, and the exit that follows a successful update
closes the main frame -- neither of which wants a modal loop between them.

The cost is that a modeless dialog has to be explicit about its own lifetime:
wx's default handling for both the window button and Escape ends in
``EndDialog``, which *hides* a modeless dialog rather than destroying it, and a
hidden one would go on taking progress callbacks for a download nothing on
screen owns any more. ``handlers._on_close`` therefore cancels and destroys.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import APP_VERSION, DARK_BG, LIGHT_TEXT, SPACE_MD, SPACE_SM, SUBDUED_TEXT
from utils.i18n import t
from widgets.dialogs.update_dialog.handlers import GAUGE_RANGE, UpdateDialogHandlersMixin
from widgets.dialogs.update_dialog.properties import PHASE_CONFIRM, UpdateDialogPropertiesMixin
from widgets.stylize import apply_type_level, init_top_level_window, stylize_button, stylize_gauge

if TYPE_CHECKING:
    from controllers.app_controller import AppController
    from services.update_service import UpdateInfo

#: Width the prose is wrapped to. The window has no natural width of its own --
#: it is fitted to its contents -- so this is what sets it.
WRAP_WIDTH = 420


class UpdateDialog(UpdateDialogHandlersMixin, UpdateDialogPropertiesMixin, wx.Dialog):
    """Confirms the update, then shows the download it started.

    Only ever opened for an update :func:`services.update_installer.can_auto_update`
    accepts; the frame falls back to opening the release page otherwise, so this
    class never has to render a "cannot update" state as its opening move.
    """

    def __init__(self, parent: wx.Window, controller: AppController, info: UpdateInfo) -> None:
        super().__init__(parent, title=t("app.update.title"))
        init_top_level_window(self)
        self.SetBackgroundColour(DARK_BG)

        self.controller = controller
        self.info = info
        self._installer = None
        self._phase = PHASE_CONFIRM
        self._wrap_width = WRAP_WIDTH
        # -1 rather than 0 so the installer's opening ``(0, total)`` tick, which
        # is what puts the size on screen before the first byte, is not swallowed
        # as "no change".
        self._last_step = -1
        # False until Update is pressed and again once the download has reached
        # an outcome; see ``handlers._render_progress`` for what it guards.
        self._accepting_progress = False

        self._build_ui()
        self._show_phase(PHASE_CONFIRM)
        self.Centre()

        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        self._panel = panel
        sizer = wx.BoxSizer(wx.VERTICAL)

        heading = wx.StaticText(panel, label=t("app.update.heading", version=self.info.version))
        heading.SetForegroundColour(LIGHT_TEXT)
        apply_type_level(heading, "title")
        sizer.Add(heading, 0, wx.ALL, SPACE_MD)

        body = wx.StaticText(panel, label=t("app.update.body", current=APP_VERSION))
        body.SetForegroundColour(LIGHT_TEXT)
        body.Wrap(WRAP_WIDTH)
        sizer.Add(body, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_MD)

        self._gauge = wx.Gauge(panel, range=GAUGE_RANGE)
        stylize_gauge(self._gauge)
        sizer.Add(self._gauge, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_MD)

        # One label for progress and for failure copy. They never coexist, and a
        # second control would only differ in which of them was left blank.
        self._status = wx.StaticText(panel, label="")
        self._status.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(self._status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_MD)

        sizer.Add(self._build_buttons(panel), 0, wx.EXPAND | wx.ALL, SPACE_MD)

        panel.SetSizer(sizer)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(outer)

    def _build_buttons(self, panel: wx.Panel) -> wx.BoxSizer:
        """The one row every phase shares; ``_show_phase`` decides who is in it.

        Separate buttons per phase rather than one pair that is re-labelled: a
        relabelled ``wx.Button`` keeps the size it was measured at, and this row
        goes from "Later / Update now" to "Cancel" and back to "Close".
        """
        row = wx.BoxSizer(wx.HORIZONTAL)

        # The release page stays one click away in both the phases that have a
        # decision in them -- it is where the notes for this version are, and
        # after a failure it is how the user installs it by hand.
        self._notes_btn = wx.Button(panel, label=t("app.update.btn.release_notes"))
        stylize_button(self._notes_btn, kind="ghost", surface="base")
        self._notes_btn.Bind(wx.EVT_BUTTON, self._on_release_notes_clicked)
        row.Add(self._notes_btn, 0)

        row.AddStretchSpacer(1)

        self._later_btn = wx.Button(panel, label=t("app.update.btn.later"))
        stylize_button(self._later_btn, kind="secondary", surface="base")
        self._later_btn.Bind(wx.EVT_BUTTON, self._on_later_clicked)
        row.Add(self._later_btn, 0, wx.RIGHT, SPACE_SM)

        self._cancel_btn = wx.Button(panel, label=t("app.update.btn.cancel"))
        stylize_button(self._cancel_btn, kind="secondary", surface="base")
        self._cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel_clicked)
        # No trailing border on these two: each is the last *shown* button of its
        # phase, and a hidden item contributes neither size nor border, so a gap
        # here would push it off the edge the primary sits on in the confirmation.
        row.Add(self._cancel_btn, 0)

        self._close_btn = wx.Button(panel, label=t("app.update.btn.close"))
        stylize_button(self._close_btn, kind="secondary", surface="base")
        self._close_btn.Bind(wx.EVT_BUTTON, self._on_close_clicked)
        row.Add(self._close_btn, 0)

        self._update_btn = wx.Button(panel, label=t("app.update.btn.update"))
        stylize_button(self._update_btn, kind="primary", surface="base")
        self._update_btn.Bind(wx.EVT_BUTTON, self._on_update_clicked)
        self._update_btn.SetDefault()
        row.Add(self._update_btn, 0)

        return row


def show_update_dialog(
    parent: wx.Window, controller: AppController, info: UpdateInfo
) -> UpdateDialog:
    """Open the updater, or raise the one that is already open.

    The note this is opened from stays clickable for the whole session and the
    Help menu carries the same action, so "clicked twice" is ordinary -- and a
    second dialog would start a second 175 MB download of the same file.
    ``GetChildren()`` can only ever hand back live windows, which is what makes
    it safe to test a previously opened dialog for (see docs/WXMSW_BEHAVIOUR.md).
    """
    for child in parent.GetChildren():
        if isinstance(child, UpdateDialog):
            child.Raise()
            return child
    dialog = UpdateDialog(parent, controller, info)
    dialog.Show()
    return dialog
