"""The app's one empty state (C5 / C6).

Before phase 4 the app had five unrelated ways of saying "there is nothing
here", and the two most visible ones were broken in different directions:

* **Deck Notes** centred its message in the middle of a ~1500x650 void while the
  only button that could fix the emptiness -- ``+ Add Note`` -- stayed pinned to
  the panel's top-left corner, most of a screen away from the sentence telling
  you to press it. The sentence also said ``click "Add"``, naming a control that
  does not exist under that name anywhere in the app.
* **Sideboard Guide** had the right shape (centred message, primary CTA, and it
  hid its normal button row so the CTA was the only affordance) but the same
  wrong copy, naming ``"Add"`` while its own CTA read *Add your first matchup*.
* **Card Inspector** rendered "Select a card to inspect." flush top-left in one
  box and centred in the box immediately beside it.
* The **deck workspace** zones had their own hand-rolled panel with hard-coded
  English, its own font sizes off the ladder, and a 2:3 stretch-spacer split
  instead of a true centre.
* The **builder results table** had no empty state at all -- zero matches left a
  bare ``wx.ListCtrl`` with headers and a 9pt "Showing 0 cards." underneath it.

This module is the single component all of those now go through. The rules it
encodes, so that no caller has to re-decide them:

* the block is **max-width constrained** and centred in both axes. A message
  that wraps at the full width of a 1500px pane is not a paragraph, it is a
  horizon; :data:`EMPTY_STATE_MAX_WIDTH` is where it wraps instead.
* there is **at most one primary CTA**, and it lives *inside* the block, under
  the message it belongs to -- never in a toolbar somewhere else. Callers that
  have a toolbar with the same action are expected to hide it while the empty
  state is up (see ``Show``/``Hide`` pairs at the call sites).
* an optional **secondary** action is allowed but is never the primary. The
  Sideboard Guide needs one: its "Record" flow is reachable *only* from the
  empty state, because the panel hides its button row when there are no
  entries, so dropping it to satisfy "one CTA" would have deleted a feature
  rather than tidied a layout.
* copy **names the real button**. There is no way to enforce that in code, so
  the CTA's label and the message come from the same call site and the message
  is written not to name a button at all -- the button is right there.
"""

from __future__ import annotations

from collections.abc import Callable

import wx

from utils.constants import EMPTY_STATE_MAX_WIDTH, SPACE_MD, SPACE_SM
from widgets.stylize import stylize_button, stylize_label, surface_colour


class EmptyState(wx.Panel):
    """A centred, width-constrained "nothing here yet" block.

    Exposes :attr:`message_label`, :attr:`hint_label`, :attr:`cta_button` and
    :attr:`secondary_button` so callers can re-label or re-bind after
    construction (the deck workspace re-labels per zone, the builder re-labels
    between "no matches" and "no search yet").
    """

    def __init__(
        self,
        parent: wx.Window,
        *,
        message: str,
        hint: str | None = None,
        cta_label: str | None = None,
        on_cta: Callable[[wx.CommandEvent], None] | None = None,
        secondary_label: str | None = None,
        on_secondary: Callable[[wx.CommandEvent], None] | None = None,
        surface: str = "panel",
        max_width: int = EMPTY_STATE_MAX_WIDTH,
    ) -> None:
        super().__init__(parent)
        self._surface = surface
        self._max_width = max_width
        self.SetBackgroundColour(surface_colour(surface))

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)
        sizer.AddStretchSpacer(1)

        self.message_label = wx.StaticText(self, label=message, style=wx.ALIGN_CENTRE_HORIZONTAL)
        stylize_label(self.message_label, subtle=True, level="body", surface=surface)
        self.message_label.Wrap(max_width)
        sizer.Add(self.message_label, 0, wx.ALIGN_CENTER_HORIZONTAL)

        self.hint_label: wx.StaticText | None = None
        if hint:
            self.hint_label = wx.StaticText(self, label=hint, style=wx.ALIGN_CENTRE_HORIZONTAL)
            stylize_label(
                self.hint_label, subtle=True, level="caption", surface=surface, tone="placeholder"
            )
            self.hint_label.Wrap(max_width)
            sizer.Add(self.hint_label, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, SPACE_SM)

        self.cta_button: wx.Button | None = None
        if cta_label:
            self.cta_button = wx.Button(self, label=cta_label)
            stylize_button(self.cta_button, kind="primary")
            if on_cta is not None:
                self.cta_button.Bind(wx.EVT_BUTTON, on_cta)
            sizer.Add(self.cta_button, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, SPACE_MD)

        self.secondary_button: wx.Button | None = None
        if secondary_label:
            self.secondary_button = wx.Button(self, label=secondary_label)
            stylize_button(self.secondary_button, kind="secondary")
            if on_secondary is not None:
                self.secondary_button.Bind(wx.EVT_BUTTON, on_secondary)
            sizer.Add(self.secondary_button, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, SPACE_SM)

        sizer.AddStretchSpacer(1)

    def set_message(self, message: str, hint: str | None = None) -> None:
        """Re-label the block, re-wrapping to the same max width.

        ``Wrap`` is destructive -- it rewrites the label with hard line breaks --
        so the new text has to be set before wrapping, every time.
        """
        self.message_label.SetLabel(message)
        self.message_label.Wrap(self._max_width)
        if self.hint_label is not None:
            self.hint_label.SetLabel(hint or "")
            self.hint_label.Wrap(self._max_width)
        self.Layout()
