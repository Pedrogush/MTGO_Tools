"""Factory for creating zone card tables."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from wx.lib.agw import flatnotebook as fnb

if TYPE_CHECKING:
    from utils.mana_icon_factory import ManaIconFactory
    from widgets.panels.card_table_panel import CardTablePanel


class ZoneTableFactory:
    """Factory for creating card table panels for deck zones."""

    def __init__(
        self,
        parent_notebook: fnb.FlatNotebook,
        mana_icons: "ManaIconFactory",
        get_card_metadata: Callable[[str], dict[str, Any] | None],
        get_owned_status: Callable[[str], dict[str, Any]],
        on_delta: Callable[[str, str, int], None],
        on_remove: Callable[[str, str], None],
        on_add: Callable[[str], None],
        on_focus: Callable[[str, dict[str, Any] | None], None],
        on_hover: Callable[[str, dict[str, Any]], None],
    ):
        self.parent_notebook = parent_notebook
        self.mana_icons = mana_icons
        self.get_card_metadata = get_card_metadata
        self.get_owned_status = get_owned_status
        self.on_delta = on_delta
        self.on_remove = on_remove
        self.on_add = on_add
        self.on_focus = on_focus
        self.on_hover = on_hover

    def create_zone_table(self, zone: str, tab_name: str) -> "CardTablePanel":
        """Create a card table panel for a specific zone."""
        from widgets.panels.card_table_panel import CardTablePanel

        table = CardTablePanel(
            self.parent_notebook,
            zone,
            self.mana_icons,
            self.get_card_metadata,
            self.get_owned_status,
            self.on_delta,
            self.on_remove,
            self.on_add,
            self.on_focus,
            self.on_hover,
        )
        self.parent_notebook.AddPage(table, tab_name)
        return table
