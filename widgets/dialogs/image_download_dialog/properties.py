"""Selection accessors for the offline images mode dialog."""

from __future__ import annotations


class ImageDownloadDialogPropertiesMixin:
    """Option accessors for :class:`ImageDownloadDialog`."""

    def get_selected_options(self) -> tuple[str, int | None]:
        # Offline images mode is deliberately choice-free: always the medium
        # ("normal") Scryfall size — good enough on low- and high-res monitors —
        # and always the full card set (issue #951).
        return "normal", None
