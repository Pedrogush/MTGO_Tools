"""Tests for ImageService business logic."""

import services.image_service as image_service
from services.image_service import CardImageDownloadQueue, ImageService
from utils.card_images import CardImageRequest


def test_image_service_initialization():
    """Test ImageService initializes with correct default state."""
    service = ImageService()

    assert service.bulk_data_by_name is None
    assert service.printing_index_loading is False
    assert service.image_downloader is None


def test_set_bulk_data():
    """Test setting bulk data."""
    service = ImageService()
    test_data = {
        "Lightning Bolt": [{"name": "Lightning Bolt", "set": "LEA"}],
        "Island": [{"name": "Island", "set": "LEA"}],
    }

    service.set_bulk_data(test_data)

    assert service.get_bulk_data() == test_data


def test_get_bulk_data_initially_none():
    """Test that bulk data is initially None."""
    service = ImageService()

    assert service.get_bulk_data() is None


def test_clear_printing_index_loading():
    """Test clearing the printing index loading flag."""
    service = ImageService()
    service.printing_index_loading = True

    service.clear_printing_index_loading()

    assert service.printing_index_loading is False


def test_is_loading_initially_false():
    """Test that loading flag is initially false."""
    service = ImageService()

    assert service.is_loading() is False


def test_is_loading_when_loading():
    """Test that is_loading returns True when loading."""
    service = ImageService()
    service.printing_index_loading = True

    assert service.is_loading() is True


class _FakeCache:
    def get_image_path_for_printing(self, card_name, set_code, size):
        return None

    def get_image_path(self, card_name, size):
        return None


class _FakeDownloader:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def download_card_image_by_name(self, name, size, set_code=None):
        self.calls += 1
        response = self._responses[self.calls - 1]
        if isinstance(response, Exception):
            raise response
        return response


def _build_queue(downloader):
    queue = CardImageDownloadQueue(_FakeCache())
    queue._downloader = downloader
    return queue


def test_download_request_retries_with_backoff(monkeypatch):
    sleeps = []
    monkeypatch.setattr(image_service.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(image_service.time, "monotonic", lambda: 0.0)
    downloader = _FakeDownloader([(False, "429 Too Many Requests"), (True, "ok")])
    queue = _build_queue(downloader)
    try:
        request = CardImageRequest(
            card_name="Mirrorpool",
            uuid=None,
            set_code="aeoe",
            collector_number=None,
            size="normal",
        )
        assert queue._download_request(request) is True
    finally:
        queue.stop()

    assert downloader.calls == 2
    assert sleeps == [0.5]


def test_download_request_404_no_retry(monkeypatch):
    sleeps = []
    monkeypatch.setattr(image_service.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(image_service.time, "monotonic", lambda: 0.0)
    downloader = _FakeDownloader(
        [Exception("404 Client Error: Not Found for url: https://api.scryfall.com/cards")]
    )
    queue = _build_queue(downloader)
    try:
        request = CardImageRequest(
            card_name="Mirrorpool",
            uuid=None,
            set_code="aeoe",
            collector_number=None,
            size="normal",
        )
        assert queue._download_request(request) is False
        assert queue.enqueue(request) is False
        other_size = CardImageRequest(
            card_name="Mirrorpool",
            uuid=None,
            set_code="aeoe",
            collector_number=None,
            size="large",
        )
        assert queue.enqueue(other_size) is False
        other_collector = CardImageRequest(
            card_name="Mirrorpool",
            uuid=None,
            set_code="aeoe",
            collector_number="42",
            size="normal",
        )
        assert queue.enqueue(other_collector) is False
    finally:
        queue.stop()

    assert downloader.calls == 1
    assert sleeps == []
