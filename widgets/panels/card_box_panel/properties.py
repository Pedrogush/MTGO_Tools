"""Pure-data helpers for the card box panel."""

from __future__ import annotations

from typing import Any

import wx

from utils.mana_icon_factory import ManaIconFactory


class CardBoxPanelPropertiesMixin:
    """Pure helpers (no ``self`` UI mutation) for :class:`CardBoxPanel`.

    Kept as a mixin (no ``__init__``) so :class:`CardBoxPanel` remains the
    single source of truth for instance-state initialization.
    """

    def _resolve_card_color(self, meta: dict[str, Any]) -> tuple[int, int, int]:
        identity = meta.get("color_identity") or meta.get("colors") or []
        normalized = [str(c).lower() for c in identity if c]
        if not normalized:
            return ManaIconFactory.FALLBACK_COLORS["c"]
        if len(normalized) == 1:
            return ManaIconFactory.FALLBACK_COLORS.get(
                normalized[0], ManaIconFactory.FALLBACK_COLORS["c"]
            )
        return ManaIconFactory.FALLBACK_COLORS["multicolor"]

    def _build_image_name_candidates(self, card: dict[str, Any], meta: dict[str, Any]) -> list[str]:
        candidates: list[str] = []
        base_name = card.get("name")
        if base_name:
            candidates.append(base_name)
        aliases = meta.get("aliases") if meta is not None else None
        if isinstance(aliases, list):
            for alias in aliases:
                if alias and alias not in candidates:
                    candidates.append(alias)
        # Promote the combined DFC name (from meta.name) to position 0 when
        # base_name is a single face name (no "//").  The image DB stores
        # face-0 entries under the combined name reliably; individual face names
        # can collide with same-named back faces of other printings (e.g.
        # "Witch Enchanter" also appears as face_index=1 of a different card).
        # When base_name already contains "//" it is already the canonical key.
        if base_name and "//" not in base_name and meta is not None:
            meta_name = meta.get("name")
            if meta_name and "//" in meta_name and meta_name in candidates:
                candidates.remove(meta_name)
                candidates.insert(0, meta_name)
        return candidates

    def _wrap_text(self, dc: wx.DC, text: str, max_width: int) -> list[str]:
        words = text.split()
        if not words:
            return [text]
        lines: list[str] = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            if dc.GetTextExtent(test)[0] <= max_width or not current:
                current = test
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines
