"""Navigation and resize handlers for the tutorial dialog."""

from __future__ import annotations

import wx


class TutorialDialogHandlersMixin:
    """Nav and resize handlers for :class:`TutorialDialog`."""

    _step: int
    _total: int
    _body_label: wx.StaticText

    def _on_back(self, _evt: wx.CommandEvent) -> None:
        if self._step > 0:
            self._step -= 1
            self._refresh()

    def _on_next(self, _evt: wx.CommandEvent) -> None:
        if self._step < self._total - 1:
            self._step += 1
            self._refresh()
        else:
            self.EndModal(wx.ID_OK)

    def _on_skip(self, _evt: wx.CommandEvent) -> None:
        self.EndModal(wx.ID_CANCEL)

    def OnSize(self, event: wx.SizeEvent) -> None:  # noqa: N802 - wx override
        event.Skip()
        wx.CallAfter(self._rewrap)

    def _rewrap(self) -> None:
        if self._body_label:
            self._body_label.Wrap(self.GetClientSize().GetWidth() - 40)
            self.Layout()
