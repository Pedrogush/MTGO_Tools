"""Unit tests for the in-app update check (issue #142).

No network is exercised: :meth:`UpdateService._fetch_latest_release` is the one
seam that touches ``requests``, so every test stubs it (or stubs ``requests.get``
itself, where the point is that a transport failure stays contained). The
throttle and the disable setting are covered by counting how often that seam is
reached.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from services.update_service import (
    NO_RELEASE,
    RELEASES_PAGE_URL,
    UpdateInfo,
    UpdateService,
    get_update_service,
    parse_version,
    reset_update_service,
)


def _release_payload(
    tag: str, url: str = "https://github.com/o/r/releases/tag/x"
) -> dict[str, Any]:
    """The subset of GitHub's ``/releases/latest`` payload the service reads."""
    return {"tag_name": tag, "html_url": url}


def _service(
    tmp_path: Path,
    *,
    current_version: str = "1.0.2",
    responses: list[Any] | None = None,
    check_interval: float = 86400.0,
) -> tuple[UpdateService, list[str]]:
    """An UpdateService whose HTTP seam replays ``responses`` and records calls.

    ``None`` in ``responses`` stands for a failed request. Returns the service
    plus the list that grows by one entry per request actually attempted.
    """
    queue = list(responses if responses is not None else [])
    calls: list[str] = []

    service = UpdateService(
        current_version=current_version,
        cache_path=tmp_path / "update_check.json",
        check_interval=check_interval,
    )

    def _fake_fetch() -> Any:
        calls.append(service.api_url)
        return queue.pop(0) if queue else None

    service._fetch_latest_release = _fake_fetch  # type: ignore[method-assign]
    return service, calls


# ---------------------------------------------------------------------------
# parse_version
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("v1.0.2", (1, 0, 2)),
        ("1.0.2", (1, 0, 2)),
        ("V1.0.2", (1, 0, 2)),
        ("  v1.0.2\n", (1, 0, 2)),
        ("v10.20.30", (10, 20, 30)),
    ],
)
def test_parse_version_accepts_plain_release_tags(raw: str, expected: tuple[int, int, int]) -> None:
    assert parse_version(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", None, "latest", "v1.0", "1.0.2.3", "v1.0.x", "v-1.0.2", "1.0.3-rc1", "v1.0.2+build"],
)
def test_parse_version_rejects_anything_else(raw: str | None) -> None:
    assert parse_version(raw) is None


def test_parse_version_orders_numerically_not_lexically() -> None:
    # The reason this parses at all: "1.0.10" < "1.0.9" as strings.
    assert parse_version("v1.0.10") > parse_version("v1.0.9")  # type: ignore[operator]
    assert parse_version("v1.10.0") > parse_version("v1.9.9")  # type: ignore[operator]
    assert parse_version("v2.0.0") > parse_version("v1.99.99")  # type: ignore[operator]


# ---------------------------------------------------------------------------
# Version comparison
# ---------------------------------------------------------------------------


def test_check_reports_a_newer_release(tmp_path: Path) -> None:
    service, calls = _service(tmp_path, responses=[_release_payload("v1.0.3")])

    result = service.check()

    assert result == UpdateInfo(
        version="1.0.3", release_url="https://github.com/o/r/releases/tag/x"
    )
    assert len(calls) == 1


def test_check_is_quiet_when_already_current(tmp_path: Path) -> None:
    service, _calls = _service(tmp_path, responses=[_release_payload("v1.0.2")])

    assert service.check() is None


def test_check_is_quiet_when_the_release_is_older(tmp_path: Path) -> None:
    # A rolled-back release, or a build made from an unmerged branch that is
    # ahead of main — either way there is nothing to offer the user.
    service, _calls = _service(tmp_path, responses=[_release_payload("v1.0.1")])

    assert service.check() is None


def test_check_compares_numerically_across_a_ten_boundary(tmp_path: Path) -> None:
    service, _calls = _service(
        tmp_path, current_version="1.0.9", responses=[_release_payload("v1.0.10")]
    )

    result = service.check()

    assert result is not None
    assert result.version == "1.0.10"


def test_check_falls_back_to_the_releases_page_without_an_html_url(tmp_path: Path) -> None:
    service, _calls = _service(tmp_path, responses=[{"tag_name": "v1.0.3"}])

    result = service.check()

    assert result is not None
    assert result.release_url == RELEASES_PAGE_URL


# ---------------------------------------------------------------------------
# Degraded inputs: malformed tags, malformed payloads, network failure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"tag_name": "nightly"},  # not a release version
        {"tag_name": None},  # wrong type
        {},  # field gone entirely
        {"message": "Not Found"},  # GitHub's 404 body shape
    ],
)
def test_check_ignores_a_payload_it_cannot_read(tmp_path: Path, payload: dict[str, Any]) -> None:
    service, _calls = _service(tmp_path, responses=[payload])

    assert service.check() is None


def test_an_unreadable_payload_still_counts_as_a_completed_check(tmp_path: Path) -> None:
    # Otherwise a permanently changed API shape would mean one request per launch.
    service, calls = _service(
        tmp_path, responses=[{"tag_name": "nightly"}, _release_payload("v9.0.0")]
    )

    assert service.check() is None
    assert service.check() is None
    assert len(calls) == 1


def test_check_is_quiet_when_the_running_version_is_unknown(tmp_path: Path) -> None:
    # APP_VERSION degrades to "unknown" when the VERSION file is missing from a
    # build; with nothing to compare against, saying nothing beats guessing.
    service, _calls = _service(
        tmp_path, current_version="unknown", responses=[_release_payload("v9.9.9")]
    )

    assert service.check() is None


def test_check_survives_a_network_failure(tmp_path: Path) -> None:
    service, calls = _service(tmp_path, responses=[None])

    assert service.check() is None
    assert len(calls) == 1


def test_a_failed_request_does_not_burn_the_throttle_window(tmp_path: Path) -> None:
    # A failed attempt is not a completed check, so the next launch retries
    # rather than sitting on no information for a whole day.
    service, calls = _service(tmp_path, responses=[None, _release_payload("v1.0.3")])

    assert service.check() is None
    result = service.check()

    assert len(calls) == 2
    assert result is not None
    assert result.version == "1.0.3"


def test_a_failed_request_keeps_serving_the_last_known_answer(tmp_path: Path) -> None:
    service, _calls = _service(
        tmp_path, check_interval=0.0, responses=[_release_payload("v1.0.3"), None]
    )

    assert service.check() == UpdateInfo(
        version="1.0.3", release_url="https://github.com/o/r/releases/tag/x"
    )
    # Second call: throttle expired, request fails — the cached answer stands.
    result = service.check()

    assert result is not None
    assert result.version == "1.0.3"


def test_a_deleted_release_stops_being_advertised(tmp_path: Path) -> None:
    """The bug this guards: a pulled release recommended forever from a stale cache.

    A 404 means "nothing is published", which is an answer. Treating it like a
    transport failure made every later launch re-ask, 404, and fall back to the
    very answer it should have thrown away.
    """
    service, calls = _service(
        tmp_path,
        check_interval=0.0,
        responses=[_release_payload("v1.0.3"), NO_RELEASE],
    )

    assert service.check() is not None  # v1.0.3 is published and newer
    # The release is then deleted, so GitHub starts answering 404.
    assert service.check() is None
    assert len(calls) == 2


def test_a_deleted_release_stays_gone_across_restarts(tmp_path: Path) -> None:
    """The cleared answer must be persisted, not just returned once."""
    service, _calls = _service(
        tmp_path, check_interval=0.0, responses=[_release_payload("v1.0.3"), NO_RELEASE]
    )
    service.check()
    service.check()

    # A fresh service reading the same stamp, with the throttle still holding.
    restarted, calls = _service(tmp_path, check_interval=86400.0)

    assert restarted.check() is None
    assert not calls, "a stamped 'nothing published' must satisfy the throttle"


def test_no_release_counts_as_a_completed_check(tmp_path: Path) -> None:
    service, calls = _service(tmp_path, responses=[NO_RELEASE, _release_payload("v1.0.3")])

    assert service.check() is None
    # Throttled: the 404 was a real answer, so it holds the window like any other.
    assert service.check() is None
    assert len(calls) == 1


def test_a_404_is_read_as_no_release_not_as_a_failure(tmp_path: Path, monkeypatch) -> None:
    """The real ``requests`` seam: 404 must reach the NO_RELEASE path."""
    import services.update_service as update_service

    class _NotFound:
        status_code = 404

        def raise_for_status(self) -> None:  # pragma: no cover - never reached
            raise AssertionError("404 must be handled before raise_for_status")

        def json(self) -> Any:  # pragma: no cover - never reached
            raise AssertionError("404 carries no payload worth reading")

    monkeypatch.setattr(update_service.requests, "get", lambda *a, **k: _NotFound())
    service = UpdateService(current_version="1.0.2", cache_path=tmp_path / "update_check.json")

    assert service._fetch_latest_release() is update_service.NO_RELEASE
    assert service.check() is None
    # Stamped, unlike a transport failure — that is the whole distinction.
    assert (tmp_path / "update_check.json").exists()


def test_requests_failures_never_escape_the_service(tmp_path: Path, monkeypatch) -> None:
    """The real ``requests`` seam: a transport error must not raise into the caller."""
    import services.update_service as update_service

    def _boom(*_args: Any, **_kwargs: Any) -> Any:
        raise update_service.requests.ConnectionError("offline")

    monkeypatch.setattr(update_service.requests, "get", _boom)
    service = UpdateService(current_version="1.0.2", cache_path=tmp_path / "update_check.json")

    assert service.check() is None
    assert not (tmp_path / "update_check.json").exists()


# ---------------------------------------------------------------------------
# Throttling
# ---------------------------------------------------------------------------


def test_the_throttle_suppresses_a_second_check(tmp_path: Path) -> None:
    service, calls = _service(
        tmp_path, responses=[_release_payload("v1.0.3"), _release_payload("v1.0.4")]
    )

    first = service.check()
    second = service.check()

    assert len(calls) == 1
    assert first == second


def test_the_throttle_survives_a_restart(tmp_path: Path) -> None:
    first_run, first_calls = _service(tmp_path, responses=[_release_payload("v1.0.3")])
    first_run.check()

    # A fresh service over the same cache file stands in for the next launch.
    second_run, second_calls = _service(tmp_path, responses=[_release_payload("v1.0.4")])
    result = second_run.check()

    assert len(first_calls) == 1
    assert not second_calls
    assert result is not None
    assert result.version == "1.0.3"


def test_an_expired_throttle_re_checks(tmp_path: Path) -> None:
    service, calls = _service(
        tmp_path,
        check_interval=0.0,
        responses=[_release_payload("v1.0.3"), _release_payload("v1.0.4")],
    )

    service.check()
    result = service.check()

    assert len(calls) == 2
    assert result is not None
    assert result.version == "1.0.4"


def test_a_stamp_from_the_future_is_treated_as_stale(tmp_path: Path) -> None:
    # A clock that ran fast and was then corrected would otherwise pin the
    # cached answer forever.
    (tmp_path / "update_check.json").write_text(
        '{"checked_at": 99999999999.0, "latest_version": "1.0.3", "release_url": "https://x.test"}',
        encoding="utf-8",
    )
    service, calls = _service(tmp_path, responses=[_release_payload("v1.0.4")])

    result = service.check()

    assert len(calls) == 1
    assert result is not None
    assert result.version == "1.0.4"


def test_a_corrupt_cache_file_is_treated_as_no_cache(tmp_path: Path) -> None:
    cache = tmp_path / "update_check.json"
    cache.write_text("{not json at all", encoding="utf-8")
    service, calls = _service(tmp_path, responses=[_release_payload("v1.0.3")])

    result = service.check()

    assert len(calls) == 1
    assert result is not None
    assert result.version == "1.0.3"


def test_an_unwritable_cache_directory_does_not_break_the_check(tmp_path: Path) -> None:
    # The cache path sits under a *file*, so mkdir/replace can't succeed.
    blocker = tmp_path / "blocker"
    blocker.write_text("", encoding="utf-8")
    service = UpdateService(
        current_version="1.0.2", cache_path=blocker / "nested" / "update_check.json"
    )
    service._fetch_latest_release = lambda: _release_payload("v1.0.3")  # type: ignore[method-assign]

    result = service.check()

    assert result is not None
    assert result.version == "1.0.3"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


def test_get_update_service_returns_a_singleton_until_reset() -> None:
    first = get_update_service()
    assert get_update_service() is first
    reset_update_service()
    assert get_update_service() is not first
