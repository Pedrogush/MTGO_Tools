"""First-run tutorial wizard for MTGO Tools."""

from __future__ import annotations

import wx

from utils.constants import DARK_BG, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
from utils.i18n import DEFAULT_LOCALE, translate

_STEP_KEYS: list[tuple[str, str]] = [
    ("tutorial.step0.title", "tutorial.step0.body"),
    ("tutorial.step1.title", "tutorial.step1.body"),
    ("tutorial.step2.title", "tutorial.step2.body"),
    ("tutorial.step3.title", "tutorial.step3.body"),
    ("tutorial.step4.title", "tutorial.step4.body"),
    ("tutorial.step5.title", "tutorial.step5.body"),
    ("tutorial.step6.title", "tutorial.step6.body"),
]


class TutorialDialog(wx.Dialog):
    """Multi-page wizard that introduces the main features of MTGO Tools."""

    def __init__(self, parent: wx.Window, locale: str = DEFAULT_LOCALE) -> None:
        self._locale = locale
        super().__init__(
            parent,
            title=self._t("tutorial.dialog_title"),
            size=(540, 420),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.SetBackgroundColour(DARK_BG)
        self._step = 0
        self._total = len(_STEP_KEYS)
        self._build_ui()
        self._refresh()
        self.Centre()

    def _t(self, key: str) -> str:
        return translate(self._locale, key)

    # ------------------------------------------------------------------ build --
    def _build_ui(self) -> None:
        outer = wx.BoxSizer(wx.VERTICAL)

        # ---- header bar ----
        header = wx.Panel(self)
        header.SetBackgroundColour(DARK_PANEL)
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        header.SetSizer(header_sizer)

        self._title_label = wx.StaticText(header, label="")
        self._title_label.SetForegroundColour(LIGHT_TEXT)
        font = self._title_label.GetFont()
        font.SetPointSize(font.GetPointSize() + 3)
        font.MakeBold()
        self._title_label.SetFont(font)
        header_sizer.Add(self._title_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 16)

        self._progress_label = wx.StaticText(header, label="")
        self._progress_label.SetForegroundColour(SUBDUED_TEXT)
        header_sizer.Add(self._progress_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 16)

        outer.Add(header, 0, wx.EXPAND)

        # ---- divider ----
        line = wx.StaticLine(self)
        outer.Add(line, 0, wx.EXPAND)

        # ---- body ----
        self._body_label = wx.StaticText(
            self,
            label="",
            style=wx.ST_NO_AUTORESIZE,
        )
        self._body_label.SetForegroundColour(LIGHT_TEXT)
        outer.Add(self._body_label, 1, wx.EXPAND | wx.ALL, 20)

        # ---- bottom bar ----
        bottom_line = wx.StaticLine(self)
        outer.Add(bottom_line, 0, wx.EXPAND)

        btn_bar = wx.Panel(self)
        btn_bar.SetBackgroundColour(DARK_PANEL)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_bar.SetSizer(btn_sizer)

        self._skip_btn = wx.Button(btn_bar, label=self._t("tutorial.btn.skip"))
        self._skip_btn.SetForegroundColour(SUBDUED_TEXT)
        self._skip_btn.Bind(wx.EVT_BUTTON, self._on_skip)
        btn_sizer.Add(self._skip_btn, 0, wx.ALL, 8)

        btn_sizer.AddStretchSpacer(1)

        self._back_btn = wx.Button(btn_bar, wx.ID_BACKWARD, label=self._t("tutorial.btn.back"))
        self._back_btn.Bind(wx.EVT_BUTTON, self._on_back)
        btn_sizer.Add(self._back_btn, 0, wx.TOP | wx.BOTTOM | wx.RIGHT, 8)

        self._next_btn = wx.Button(btn_bar, wx.ID_FORWARD, label=self._t("tutorial.btn.next"))
        self._next_btn.SetDefault()
        self._next_btn.Bind(wx.EVT_BUTTON, self._on_next)
        btn_sizer.Add(self._next_btn, 0, wx.TOP | wx.BOTTOM | wx.RIGHT, 8)

        outer.Add(btn_bar, 0, wx.EXPAND)

        self.SetSizer(outer)

    # ------------------------------------------------------------------ nav --
    def _refresh(self) -> None:
        title_key, body_key = _STEP_KEYS[self._step]
        self._title_label.SetLabel(self._t(title_key))
        self._progress_label.SetLabel(f"{self._step + 1} / {self._total}")
        self._body_label.SetLabel(self._t(body_key))
        self._body_label.Wrap(self.GetClientSize().GetWidth() - 40)
        self._back_btn.Enable(self._step > 0)
        is_last = self._step == self._total - 1
        self._next_btn.SetLabel(
            self._t("tutorial.btn.finish") if is_last else self._t("tutorial.btn.next")
        )
        self._skip_btn.Show(not is_last)
        self.Layout()

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

    # ------------------------------------------------------------------ resize --
    def OnSize(self, event: wx.SizeEvent) -> None:  # noqa: N802 - wx override
        event.Skip()
        wx.CallAfter(self._rewrap)

    def _rewrap(self) -> None:
        if self._body_label:
            self._body_label.Wrap(self.GetClientSize().GetWidth() - 40)
            self.Layout()


def show_tutorial(parent: wx.Window, locale: str = DEFAULT_LOCALE) -> None:
    """Show the tutorial dialog modally and destroy it afterwards."""
    dlg = TutorialDialog(parent, locale=locale)
    dlg.Bind(wx.EVT_SIZE, dlg.OnSize)
    dlg.ShowModal()
    dlg.Destroy()
