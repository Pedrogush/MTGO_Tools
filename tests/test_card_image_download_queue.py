"""Tests for background card image download queue behavior."""

from __future__ import annotations

import threading

from services import image_service
from utils import card_images


def test_card_image_queue_invokes_callback_after_download(tmp_path) -> None:
    cache_dir = tmp_path / "cache"
    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=cache_dir / "images.db")

    done = threading.Event()
    received: list[card_images.CardImageRequest] = []

    def on_downloaded(request: card_images.CardImageRequest) -> None:
        received.append(request)
        done.set()

    queue = image_service.CardImageDownloadQueue(cache, on_downloaded=on_downloaded)

    def fake_download(card_id: str, size: str = "normal") -> tuple[bool, str]:
        file_path = cache.cache_dir / size / f"{card_id}.jpg"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"image")
        cache.add_image(
            uuid=card_id,
            name="Test Card",
            set_code="TST",
            collector_number="001",
            image_size=size,
            file_path=file_path,
            scryfall_uri=None,
            artist=None,
            face_index=0,
        )
        return True, "Downloaded"

    try:
        queue._downloader.download_card_image_by_id = fake_download  # type: ignore[assignment]
        request = card_images.CardImageRequest(
            card_name="Test Card",
            uuid="test-uuid",
            set_code="TST",
            collector_number="001",
            size="normal",
        )
        assert queue.enqueue(request, prioritize=True)
        assert done.wait(2.0)
        assert received == [request]
    finally:
        queue.stop()
