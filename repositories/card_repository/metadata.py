"""Card metadata lookup and search for :class:`CardRepository`."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from repositories.card_repository.protocol import CardRepositoryProto

    _Base = CardRepositoryProto
else:
    _Base = object


class MetadataMixin(_Base):
    """Card metadata lookup and search backed by ``CardDataManager``."""

    def get_card_metadata(self, card_name: str) -> dict[str, Any] | None:
        try:
            card_info = self.card_data_manager.get_card(card_name)
            return card_info
        except RuntimeError as exc:
            logger.debug(f"Card data not loaded: {exc}")
            return None
        except Exception as exc:
            logger.warning(f"Failed to get metadata for {card_name}: {exc}")
            return None

    def search_cards(
        self,
        query: str | None = None,
        colors: list[str] | None = None,
        types: list[str] | None = None,
        mana_value: int | None = None,
    ) -> list[dict[str, Any]]:
        try:
            results = self.card_data_manager.search_cards(
                query=query or "", color_identity=colors, type_filter=types
            )
            return results
        except RuntimeError as exc:
            logger.warning(f"Card data not loaded: {exc}")
            return []
        except Exception as exc:
            logger.error(f"Failed to search cards: {exc}")
            return []

    def is_card_data_loaded(self) -> bool:
        return self._card_data_manager is not None and self._card_data_manager.is_loaded
