"""Modal dialog for manually selecting a format + archetype name."""

from __future__ import annotations

from typing import Any

import wx
from loguru import logger

from repositories.metagame_repository import MetagameRepository
from utils.constants import DARK_BG, FORMAT_OPTIONS, LIGHT_TEXT


class _LoadArchetypeDialog(wx.Dialog):
    """Small dialog for manually selecting a format + archetype name."""

    def __init__(
        self,
        parent: wx.Window,
        title: str,
        format_label: str,
        archetype_label: str,
        metagame_repository: MetagameRepository,
        locale: str | None = None,
    ) -> None:
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE)
        self.SetBackgroundColour(DARK_BG)
        self._metagame_repo = metagame_repository
        self._archetypes_by_format: dict[str, list[dict[str, Any]]] = {}

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        grid = wx.FlexGridSizer(2, 2, 6, 8)
        grid.AddGrowableCol(1, 1)
        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 12)

        lbl_fmt = wx.StaticText(self, label=format_label)
        lbl_fmt.SetForegroundColour(LIGHT_TEXT)
        self._format_choice = wx.Choice(self, choices=FORMAT_OPTIONS)
        self._format_choice.SetSelection(0)
        self._format_choice.Bind(wx.EVT_CHOICE, self._on_format_changed)

        lbl_arch = wx.StaticText(self, label=archetype_label)
        lbl_arch.SetForegroundColour(LIGHT_TEXT)
        self._archetype_choice = wx.Choice(self, choices=[], size=(260, -1))

        grid.Add(lbl_fmt, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._format_choice, 1, wx.EXPAND)
        grid.Add(lbl_arch, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._archetype_choice, 1, wx.EXPAND)

        btn_sizer = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self._populate_archetype_choices()
        self.Fit()
        self.CentreOnParent()

    def get_values(self) -> tuple[str, str]:
        fmt = self._format_choice.GetString(self._format_choice.GetSelection())
        archetype = self._archetype_choice.GetStringSelection().strip()
        return fmt, archetype

    def _on_format_changed(self, _event: wx.CommandEvent) -> None:
        self._populate_archetype_choices()

    def _populate_archetype_choices(self) -> None:
        fmt = self._format_choice.GetStringSelection()
        archetypes = self._archetypes_by_format.get(fmt)
        if archetypes is None:
            try:
                archetypes = self._metagame_repo.get_archetypes_for_format(fmt)
            except Exception as exc:
                logger.warning(f"Failed to load archetype choices for {fmt}: {exc}")
                archetypes = []
            self._archetypes_by_format[fmt] = archetypes

        names = sorted(
            {
                str(archetype.get("name", "")).strip()
                for archetype in archetypes
                if str(archetype.get("name", "")).strip()
            },
            key=str.casefold,
        )
        self._archetype_choice.Set(names)
        if names:
            self._archetype_choice.SetSelection(0)
