"""Pure-data helpers for the card inspector panel."""

from __future__ import annotations

from typing import Any

from utils.card_images import CardImageRequest


class CardInspectorPanelPropertiesMixin:
    """Pure helpers (no ``self`` UI mutation) for :class:`CardInspectorPanel`.

    Kept as a mixin (no ``__init__``) so :class:`CardInspectorPanel` remains
    the single source of truth for instance-state initialization.
    """

    inspector_current_card_name: str | None
    inspector_printings: list[dict[str, Any]]
    inspector_current_printing: int

    def _resolve_image_request_name(
        self, card: dict[str, Any], meta: dict[str, Any] | None
    ) -> str | None:
        base_name = (card.get("name") or "").strip()
        if not meta:
            return base_name or None
        aliases = meta.get("aliases") if meta is not None else None
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str) and "//" in alias:
                    return alias
        return base_name or None

    def _request_matches_current(self, request: CardImageRequest) -> bool:
        if self.inspector_current_card_name is None:
            return False
        if request.card_name == self.inspector_current_card_name:
            return True
        if not self.inspector_printings:
            return False
        printing = self.inspector_printings[self.inspector_current_printing]
        uuid = printing.get("id")
        return bool(uuid and request.uuid and uuid == request.uuid)

    @staticmethod
    def _failure_key(request: CardImageRequest) -> tuple[str, str]:
        return (
            (request.card_name or "").lower(),
            (request.set_code or "").lower(),
        )
