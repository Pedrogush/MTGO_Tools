"""Pure-data helpers and read-only getters for the mana rich-text control."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import wx
    import wx.richtext


class ManaRichTextInnerPropertiesMixin:
    """Pure helpers (no ``self`` UI mutation) for the inner RichTextCtrl.

    Kept as a mixin (no ``__init__``) so the inner control remains the
    single source of truth for instance-state initialization.
    """

    # Attributes supplied by the inner RichTextCtrl's __init__.
    _plain_text: str
    _hint_label: wx.StaticText

    def GetValue(self) -> str:  # type: ignore[override]
        return self._plain_text

    def _has_content(self) -> bool:
        return bool(self._plain_text) or self.GetLastPosition() > 0

    def _symbol_height(self) -> int:
        return max(16, self.GetCharHeight() - 2)


class ManaSymbolRichCtrlPropertiesMixin:
    """Pure helpers (no ``self`` UI mutation) for :class:`ManaSymbolRichCtrl`.

    Kept as a mixin (no ``__init__``) so :class:`ManaSymbolRichCtrl` remains
    the single source of truth for instance-state initialization.
    """

    # Attribute supplied by :class:`ManaSymbolRichCtrl` / the handlers mixin.
    _inner: wx.richtext.RichTextCtrl

    def GetValue(self) -> str:
        return self._inner.GetValue()
