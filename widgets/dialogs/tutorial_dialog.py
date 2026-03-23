"""First-run tutorial wizard for MTGO Tools."""

from __future__ import annotations

import wx

from utils.constants import DARK_BG, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT

_STEPS: list[tuple[str, str]] = [
    (
        "Welcome to MTGO Tools",
        (
            "MTGO Tools helps you research the competitive metagame, build and edit decks, "
            "track opponents, and manage your MTGO collection — all in one desktop app.\n\n"
            "This short tour covers the main features. You can revisit it any time from "
            "Settings \u2192 Show Tutorial."
        ),
    ),
    (
        "Metagame Research",
        (
            "The left panel is your metagame research hub.\n\n"
            "\u2022  Choose a format (Modern, Legacy, \u2026) from the dropdown.\n"
            "\u2022  Type in the search box to filter archetypes by name.\n"
            "\u2022  Click an archetype to load its decklists in the Deck Results panel.\n"
            "\u2022  Use \u201cReload Archetypes\u201d to refresh data from MTGGoldfish."
        ),
    ),
    (
        "Deck Workspace",
        (
            "The centre area shows the currently loaded deck.\n\n"
            "\u2022  Mainboard \u2014 your 60-card main deck.\n"
            "\u2022  Sideboard \u2014 your 15-card sideboard.\n"
            "\u2022  Hover over or click a card row to inspect it in the Card Inspector "
            "on the right.\n"
            "\u2022  Use the + / \u2212 controls to edit counts when building your own deck."
        ),
    ),
    (
        "Toolbar Tools",
        (
            "The toolbar at the top of the right panel provides quick access to:\n\n"
            "\u2022  Opponent Tracker \u2014 detects the opponent from your MTGO window title "
            "and looks up their most-played archetypes.\n"
            "\u2022  Timer Alert \u2014 configurable countdown to warn you before time runs out "
            "in a round.\n"
            "\u2022  Match History \u2014 parses your MTGO GameLog files and shows recent results.\n"
            "\u2022  Metagame Analysis \u2014 a top-level breakdown of the current format."
        ),
    ),
    (
        "Deck Builder",
        (
            "Switch the left panel to Builder mode to search for cards and craft your own deck.\n\n"
            "\u2022  Type a card name or keyword in the search box.\n"
            "\u2022  Click a result to preview it in the Card Inspector.\n"
            "\u2022  Use \u201cAdd to Main\u201d or \u201cAdd to Side\u201d to add it to your deck.\n"
            "\u2022  Open the Mana Keyboard for quick mana-cost symbol input.\n"
            "\u2022  Use \u201cCopy\u201d to copy the deck list to your clipboard."
        ),
    ),
    (
        "Sideboard Guide",
        (
            "The Sideboard Guide tab lets you record matchup-by-matchup notes.\n\n"
            "\u2022  Add an entry for each archetype you face.\n"
            "\u2022  Record cards to bring IN and take OUT for each matchup.\n"
            "\u2022  Mark flex slots \u2014 cards whose count varies by matchup.\n"
            "\u2022  Pin the guide to keep it visible while reviewing other tabs.\n"
            "\u2022  Export or import as CSV to share guides with teammates."
        ),
    ),
    (
        "You\u2019re All Set!",
        (
            "That\u2019s the quick tour of MTGO Tools.\n\n"
            "A few more tips:\n"
            "\u2022  Use the \u2699 Settings menu to load your MTGO collection, download card "
            "images, update the card database, or change the language.\n"
            "\u2022  Deck Notes let you keep free-form notes attached to any deck.\n"
            "\u2022  Session state (current deck, format, window size) is saved automatically.\n\n"
            "Good luck in your matches!"
        ),
    ),
]


class TutorialDialog(wx.Dialog):
    """Multi-page wizard that introduces the main features of MTGO Tools."""

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(
            parent,
            title="MTGO Tools \u2014 Quick Tour",
            size=(540, 420),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.SetBackgroundColour(DARK_BG)
        self._step = 0
        self._total = len(_STEPS)
        self._build_ui()
        self._refresh()
        self.Centre()

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

        self._skip_btn = wx.Button(btn_bar, label="Skip Tour")
        self._skip_btn.SetForegroundColour(SUBDUED_TEXT)
        self._skip_btn.Bind(wx.EVT_BUTTON, self._on_skip)
        btn_sizer.Add(self._skip_btn, 0, wx.ALL, 8)

        btn_sizer.AddStretchSpacer(1)

        self._back_btn = wx.Button(btn_bar, wx.ID_BACKWARD, label="< Back")
        self._back_btn.Bind(wx.EVT_BUTTON, self._on_back)
        btn_sizer.Add(self._back_btn, 0, wx.TOP | wx.BOTTOM | wx.RIGHT, 8)

        self._next_btn = wx.Button(btn_bar, wx.ID_FORWARD, label="Next >")
        self._next_btn.SetDefault()
        self._next_btn.Bind(wx.EVT_BUTTON, self._on_next)
        btn_sizer.Add(self._next_btn, 0, wx.TOP | wx.BOTTOM | wx.RIGHT, 8)

        outer.Add(btn_bar, 0, wx.EXPAND)

        self.SetSizer(outer)

    # ------------------------------------------------------------------ nav --
    def _refresh(self) -> None:
        title, body = _STEPS[self._step]
        self._title_label.SetLabel(title)
        self._progress_label.SetLabel(f"{self._step + 1} / {self._total}")
        self._body_label.SetLabel(body)
        self._body_label.Wrap(self.GetClientSize().GetWidth() - 40)
        self._back_btn.Enable(self._step > 0)
        is_last = self._step == self._total - 1
        self._next_btn.SetLabel("Finish" if is_last else "Next >")
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


def show_tutorial(parent: wx.Window) -> None:
    """Show the tutorial dialog modally and destroy it afterwards."""
    dlg = TutorialDialog(parent)
    dlg.Bind(wx.EVT_SIZE, dlg.OnSize)
    dlg.ShowModal()
    dlg.Destroy()
