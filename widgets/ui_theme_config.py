"""UI theme configuration for consistent styling."""

import wx
from wx.lib.agw import flatnotebook as fnb

from utils.constants import DARK_ACCENT, DARK_BG, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT


class UIThemeConfig:
    """Configuration for consistent UI theming."""

    def __init__(self):
        self.background_color = DARK_BG
        self.panel_color = DARK_PANEL
        self.accent_color = DARK_ACCENT
        self.text_color = LIGHT_TEXT
        self.subdued_text_color = SUBDUED_TEXT

    def apply_to_panel(self, panel: wx.Panel) -> None:
        """Apply theme to a panel."""
        panel.SetBackgroundColour(self.background_color)

    def apply_to_static_box(self, box: wx.StaticBox) -> None:
        """Apply theme to a static box."""
        box.SetForegroundColour(self.text_color)
        box.SetBackgroundColour(self.panel_color)

    def apply_to_notebook(self, notebook: fnb.FlatNotebook) -> None:
        """Apply theme to a flat notebook."""
        notebook.SetTabAreaColour(self.panel_color)
        notebook.SetActiveTabColour(self.accent_color)
        notebook.SetNonActiveTabTextColour(self.subdued_text_color)
        notebook.SetActiveTabTextColour(wx.Colour(12, 14, 18))
        notebook.SetBackgroundColour(self.background_color)
        notebook.SetForegroundColour(self.text_color)

    def get_notebook_style(self) -> int:
        """Get the default notebook style flags."""
        return (
            fnb.FNB_FANCY_TABS | fnb.FNB_SMART_TABS | fnb.FNB_NO_X_BUTTON | fnb.FNB_NO_NAV_BUTTONS
        )
