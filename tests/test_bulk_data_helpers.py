from __future__ import annotations

from collections.abc import Callable
from typing import Any

from controllers.app_controller_helpers import UICallbacks
from controllers.bulk_data_helpers import BulkDataHelpers


def _noop(*_args: Any, **_kwargs: Any) -> None:
    return None


class ImmediateWorker:
    def submit(
        self,
        func: Callable[..., Any],
        *args: Any,
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        **kwargs: Any,
    ) -> None:
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            if on_error:
                on_error(exc)
            return

        if on_success:
            on_success(result)


class FakeImageService:
    def __init__(self, *, check_result: tuple[bool, str] = (True, "current")) -> None:
        self.check_result = check_result
        self.check_error: Exception | None = None
        self.bulk_data: dict[str, list[dict[str, Any]]] | None = None
        self.load_started = True
        self.load_data = {"lightning bolt": [{"set": "lea"}]}
        self.load_stats = {"total_printings": 1}
        self.load_error: str | None = None
        self.download_error: str | None = None
        self.download_msg = "downloaded"
        self.load_calls: list[bool] = []
        self.download_calls: list[bool] = []

    def check_bulk_data_exists(self) -> tuple[bool, str]:
        if self.check_error:
            raise self.check_error
        return self.check_result

    def download_bulk_metadata_async(
        self,
        *,
        on_success: Callable[[str], None],
        on_error: Callable[[str], None],
        force: bool = False,
    ) -> None:
        self.download_calls.append(force)
        if self.download_error is not None:
            on_error(self.download_error)
            return
        on_success(self.download_msg)

    def load_printing_index_async(
        self,
        *,
        force: bool,
        on_success: Callable[[dict[str, list[dict[str, Any]]], dict[str, Any]], None],
        on_error: Callable[[str], None],
    ) -> bool:
        self.load_calls.append(force)
        if not self.load_started:
            return False
        if self.load_error is not None:
            on_error(self.load_error)
            return True
        on_success(self.load_data, self.load_stats)
        return True

    def set_bulk_data(self, bulk_data: dict[str, list[dict[str, Any]]]) -> None:
        self.bulk_data = bulk_data

    def get_bulk_data(self) -> dict[str, list[dict[str, Any]]] | None:
        return self.bulk_data


def _make_callbacks(
    *,
    statuses: list[str],
    needed: list[str] | None = None,
    completed: list[str] | None = None,
    failed: list[str] | None = None,
) -> UICallbacks:
    needed = needed if needed is not None else []
    completed = completed if completed is not None else []
    failed = failed if failed is not None else []
    return UICallbacks(
        on_status=lambda msg, *_args, **_kwargs: statuses.append(msg),
        on_archetypes_success=_noop,
        on_archetypes_error=_noop,
        on_collection_loaded=_noop,
        on_collection_not_found=_noop,
        on_collection_refresh_success=_noop,
        on_collection_failed=_noop,
        on_bulk_download_needed=needed.append,
        on_bulk_download_complete=completed.append,
        on_bulk_download_failed=failed.append,
    )


def _make_helper(image_service: FakeImageService) -> BulkDataHelpers:
    return BulkDataHelpers(
        image_service=image_service,
        worker=ImmediateWorker(),
        frame_provider=lambda: None,
        call_after=lambda callback, *args: callback(*args),
    )


def test_check_and_download_bulk_data_loads_existing_index() -> None:
    image_service = FakeImageService(check_result=(True, "current"))
    helper = _make_helper(image_service)
    statuses: list[str] = []

    helper.check_and_download_bulk_data(_make_callbacks(statuses=statuses))

    assert statuses == [
        "bulk.status.checking",
        "bulk.status.preparing_cache",
        "bulk.status.ready",
    ]
    assert image_service.load_calls == [False]
    assert image_service.download_calls == []
    assert image_service.bulk_data == image_service.load_data


def test_check_and_download_bulk_data_downloads_missing_index() -> None:
    image_service = FakeImageService(check_result=(False, "missing cache"))
    helper = _make_helper(image_service)
    statuses: list[str] = []
    needed: list[str] = []
    completed: list[str] = []

    helper.check_and_download_bulk_data(
        _make_callbacks(statuses=statuses, needed=needed, completed=completed)
    )

    assert statuses == [
        "bulk.status.checking",
        "bulk.status.downloading",
        "bulk.status.preparing_cache",
    ]
    assert needed == ["missing cache"]
    assert completed == ["downloaded"]
    assert image_service.download_calls == [False]
    assert image_service.load_calls == [True]
    assert image_service.bulk_data == image_service.load_data


def test_load_bulk_data_into_memory_reports_ready_when_index_worker_not_started() -> None:
    image_service = FakeImageService()
    image_service.load_started = False
    helper = _make_helper(image_service)
    statuses: list[str] = []

    helper.load_bulk_data_into_memory(statuses.append, force=True)

    assert statuses == ["bulk.status.preparing_cache", "app.status.ready"]
    assert image_service.load_calls == [True]
    assert image_service.bulk_data is None


def test_force_bulk_data_update_reports_ready_after_download_failure() -> None:
    image_service = FakeImageService()
    image_service.download_error = "network failed"
    helper = _make_helper(image_service)
    statuses: list[str] = []
    failed: list[str] = []

    helper.force_bulk_data_update(_make_callbacks(statuses=statuses, failed=failed))

    assert statuses == ["bulk.status.downloading", "app.status.ready"]
    assert failed == ["network failed"]
    assert image_service.download_calls == [True]
    assert image_service.load_calls == []
