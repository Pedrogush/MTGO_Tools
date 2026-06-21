"""Per-face image writing for :class:`BulkImageDownloader`.

Talks only to ``self.cache`` and ``self.session``: layout dispatch, per-face
fetch + :func:`atomic_write_bytes` + ``cache.add_image``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from utils.atomic_io import atomic_write_bytes
from utils.constants import SCRYFALL_REQUEST_TIMEOUT_SECONDS

if TYPE_CHECKING:
    from services.image_service.downloader_protocol import BulkImageDownloaderProto

    _Base = BulkImageDownloaderProto
else:
    _Base = object


class ImageWriterMixin(_Base):
    """Layout dispatch and per-face image fetch + atomic write + cache record."""

    def _download_single_image(
        self, card: dict[str, Any], size: str = "normal"
    ) -> tuple[bool, str]:
        uuid = card.get("id")
        name = card.get("name", "Unknown")

        if not uuid:
            return False, f"No UUID for {name}"

        card_faces = card.get("card_faces") or []
        if card_faces:
            return self._download_multi_face_card(card, card_faces, size)

        success, message, _ = self._download_face_asset(
            uuid=uuid,
            face_index=0,
            name=name,
            image_uris=card.get("image_uris") or {},
            size=size,
            card=card,
        )
        return success, message

    def _download_multi_face_card(
        self, card: dict[str, Any], faces: list[dict[str, Any]], size: str
    ) -> tuple[bool, str]:
        uuid = card.get("id")
        if not uuid:
            return False, "Missing UUID for multi-face card"

        # Single-image layouts (split, flip, adventure, prepare) carry one
        # physical image at the top level; per-face image_uris are empty.
        # Two-image layouts (transform, modal_dfc, reversible_card) put the
        # image_uris on each face. Dispatch by presence rather than by layout
        # name so future Scryfall layouts with the same shape work without code
        # changes.
        if not any((face.get("image_uris") or {}) for face in faces):
            return self._download_single_image_multi_face(card, size)

        downloaded = 0
        front_path: Path | None = None
        for idx, face in enumerate(faces):
            face_name = face.get("name") or card.get("name", "Unknown")
            image_uris = face.get("image_uris") or {}
            success, _, file_path = self._download_face_asset(
                uuid=uuid,
                face_index=idx,
                name=face_name,
                image_uris=image_uris,
                size=size,
                card=card,
            )
            if success:
                downloaded += 1
                if idx == 0:
                    front_path = file_path

        # Store combined display name pointing to the front face
        combined_name = card.get("name")
        if combined_name and front_path:
            self.cache.add_image(
                uuid=uuid,
                name=combined_name,
                set_code=card.get("set", ""),
                collector_number=card.get("collector_number", ""),
                image_size=size,
                file_path=front_path,
                scryfall_uri=card.get("scryfall_uri"),
                artist=card.get("artist"),
                face_index=-1,
            )

        if downloaded == 0:
            return False, f"No downloadable faces for {card.get('name', 'Unknown')}"
        return True, f"Downloaded {downloaded} faces for {card.get('name', 'Unknown')}"

    def _download_single_image_multi_face(
        self, card: dict[str, Any], size: str
    ) -> tuple[bool, str]:
        uuid = card.get("id") or ""
        combined_name = card.get("name", "Unknown")
        image_uris = card.get("image_uris") or {}

        success, message, _ = self._download_face_asset(
            uuid=uuid,
            face_index=0,
            name=combined_name,
            image_uris=image_uris,
            size=size,
            card=card,
        )
        return success, message

    def _download_face_asset(
        self,
        uuid: str,
        face_index: int,
        name: str,
        image_uris: dict[str, Any],
        size: str,
        card: dict[str, Any],
    ) -> tuple[bool, str, Path | None]:
        if self.cache.is_cached(uuid, size, face_index=face_index):
            path = self.cache.get_image_by_uuid(uuid, size, face_index=face_index)
            return True, f"Already cached: {name}", path

        image_url = image_uris.get(size) or image_uris.get("normal")
        if not image_url:
            return False, f"No {size} image for {name}", None

        try:
            resp = self.session.get(image_url, timeout=SCRYFALL_REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
        except Exception as exc:
            logger.debug(f"Failed to download {name}: {exc}")
            return False, f"Error: {name} - {exc}", None

        ext = "png" if size == "png" else "jpg"
        filename = self._build_face_filename(uuid, face_index, ext)
        file_path = self.cache.cache_dir / size / filename

        try:
            atomic_write_bytes(file_path, resp.content)
        except Exception as exc:
            logger.debug(f"Failed to write image {name}: {exc}")
            return False, f"Error saving image for {name}: {exc}", None

        self.cache.add_image(
            uuid=uuid,
            name=name,
            set_code=card.get("set", ""),
            collector_number=card.get("collector_number", ""),
            image_size=size,
            file_path=file_path,
            scryfall_uri=card.get("scryfall_uri"),
            artist=card.get("artist"),
            face_index=face_index,
        )
        return True, f"Downloaded: {name}", file_path

    @staticmethod
    def _build_face_filename(uuid: str, face_index: int, ext: str) -> str:
        if face_index <= 0:
            return f"{uuid}.{ext}"
        return f"{uuid}-f{face_index}.{ext}"
