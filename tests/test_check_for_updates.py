"""*File ▸ Check for updates* — the throttle, the three outcomes, the one request (#1041).

The automatic check asks GitHub at most once per ``UPDATE_CHECK_INTERVAL_SECONDS``
and answers from ``cache/update_check.json`` in between, which is right for a
check nobody asked for and wrong for a menu item someone just picked: v1.2.15 was
published at 14:25 on 2026-09-17 and an install that had checked at 07:16 went on
reporting 1.2.14 for the rest of the day, with no way to re-ask short of deleting
the stamp by hand.

Three layers, three files' worth of behaviour, all here because they are one
feature:

* :class:`services.update_service.UpdateService` — ``force=True`` skips the
  stamp, a completed forced check *rewrites* it, a failed one does not, and the
  unforced path is untouched;
* :class:`controllers.app_controller.updates.UpdateCheckMixin` — the request goes
  to the background worker, and a second click while one is in flight is dropped;
* :class:`widgets.frames.app_frame.handlers.app_frame.AppFrameHandlersMixin` —
  each outcome reaches the user, and the menu entry exists to start it.

No network: every test either replaces the one ``requests``-touching seam or
replaces ``requests.get`` itself. Nothing here is marked ``network``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from controllers.app_controller.updates import UpdateCheckMixin
from services.update_service import (
    FORCE_CHECK_ENV_VAR,
    OUTCOME_UNREACHABLE,
    OUTCOME_UP_TO_DATE,
    OUTCOME_UPDATE_AVAILABLE,
    CheckResult,
    UpdateInfo,
    UpdateService,
)
from widgets.frames.app_frame.handlers import app_frame as _handlers

CURRENT = "1.2.14"
NEWER = "1.2.15"
INSTALLER_NAME = f"MTGOTools_Setup_v{NEWER}.exe"
INSTALLER_URL = f"https://github.test/download/{INSTALLER_NAME}"


def _payload(tag: str) -> dict[str, Any]:
    """The subset of GitHub's ``/releases/latest`` payload the service reads."""
    return {
        "tag_name": tag,
        "html_url": f"https://github.test/releases/tag/{tag}",
        "assets": [
            {"name": INSTALLER_NAME, "browser_download_url": INSTALLER_URL},
            {"name": f"{INSTALLER_NAME}.sha256", "browser_download_url": f"{INSTALLER_URL}.sha256"},
        ],
    }


def _service(
    tmp_path: Path,
    *,
    responses: list[Any] | None = None,
    current_version: str = CURRENT,
) -> tuple[UpdateService, list[str]]:
    """A service whose HTTP seam replays ``responses`` and records every attempt.

    ``None`` in ``responses`` (and running out of them) stands for a request that
    got no answer. The returned list grows by one per attempt, which is how the
    throttle is measured: the question is always "was GitHub asked", never "what
    did the method return".
    """
    queue = list(responses if responses is not None else [])
    calls: list[str] = []
    service = UpdateService(
        current_version=current_version,
        cache_path=tmp_path / "update_check.json",
        api_url="https://api.github.test/latest",
    )

    def _fake_fetch() -> Any:
        calls.append(service.api_url)
        return queue.pop(0) if queue else None

    service._fetch_latest_release = _fake_fetch  # type: ignore[method-assign]
    return service, calls


def _stamp(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "update_check.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_forced_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing here may be forced by the environment it runs in.

    ``MTGO_TOOLS_FORCE_UPDATE_CHECK`` is documented, so a developer testing the
    update path has it set -- and it turns every throttle assertion below into
    a failure about their own shell. ``tests/test_update_service.py`` already
    clears it this way.
    """
    monkeypatch.delenv(FORCE_CHECK_ENV_VAR, raising=False)


# ---------------------------------------------------------------------------
# The service: forcing, stamping, and the interval that must survive both
# ---------------------------------------------------------------------------


def test_a_forced_check_ignores_a_stamp_written_moments_ago(tmp_path: Path) -> None:
    """The bug itself: a stamp minutes old hid a release published after it."""
    first, first_calls = _service(tmp_path, responses=[_payload(f"v{CURRENT}")])
    assert first.check() is None
    assert len(first_calls) == 1

    second, second_calls = _service(tmp_path, responses=[_payload(f"v{NEWER}")])
    result = second.check_result(force=True)

    assert len(second_calls) == 1, "the forced check answered from the stamp"
    assert result.outcome == OUTCOME_UPDATE_AVAILABLE
    assert result.info is not None
    assert result.info.version == NEWER


def test_an_unforced_check_still_answers_from_a_fresh_stamp(tmp_path: Path) -> None:
    """The 24-hour interval is the reason ``force`` had to be a parameter."""
    first, first_calls = _service(tmp_path, responses=[_payload(f"v{CURRENT}")])
    first.check()

    second, second_calls = _service(tmp_path, responses=[_payload(f"v{NEWER}")])
    result = second.check_result()

    assert second_calls == [], "the automatic check asked GitHub inside the interval"
    assert result.outcome == OUTCOME_UP_TO_DATE
    assert len(first_calls) == 1


def test_a_completed_forced_check_replaces_the_stamp(tmp_path: Path) -> None:
    """Asking by hand resets the 24-hour clock rather than leaving it to launch."""
    first, _ = _service(tmp_path, responses=[_payload(f"v{CURRENT}")])
    first.check()
    before = _stamp(tmp_path)
    assert before["latest_version"] == CURRENT

    forced, _ = _service(tmp_path, responses=[_payload(f"v{NEWER}")])
    forced.check_result(force=True)

    after = _stamp(tmp_path)
    assert after["latest_version"] == NEWER
    assert after["checked_at"] >= before["checked_at"]

    # And the next automatic check is served from it, rather than re-asking
    # because the forced one left the old timestamp in place.
    later, later_calls = _service(tmp_path, responses=[_payload(f"v{NEWER}")])
    assert later_calls == []
    assert later.check_result().outcome == OUTCOME_UPDATE_AVAILABLE


def test_a_forced_check_that_could_not_reach_github_writes_no_stamp(tmp_path: Path) -> None:
    """A failed attempt is not a completed check, so it must not start a clock."""
    service, calls = _service(tmp_path, responses=[None])

    result = service.check_result(force=True)

    assert len(calls) == 1
    assert result.outcome == OUTCOME_UNREACHABLE
    assert result.reachable is False
    assert not (tmp_path / "update_check.json").exists()


def test_an_unreachable_check_does_not_pass_the_cached_answer_off_as_fresh(
    tmp_path: Path,
) -> None:
    """``info`` survives for the Help menu; the *outcome* still says it failed."""
    seeded, _ = _service(tmp_path, responses=[_payload(f"v{NEWER}")])
    seeded.check()

    offline, _ = _service(tmp_path, responses=[None])
    result = offline.check_result(force=True)

    assert result.outcome == OUTCOME_UNREACHABLE
    assert result.info is not None and result.info.version == NEWER


def test_a_forced_check_on_the_newest_build_reports_up_to_date(tmp_path: Path) -> None:
    service, calls = _service(tmp_path, responses=[_payload(f"v{CURRENT}")])

    result = service.check_result(force=True)

    assert len(calls) == 1
    assert result.outcome == OUTCOME_UP_TO_DATE
    assert result.info is None
    assert result.current_version == CURRENT


def test_a_forced_check_reports_a_newer_release_with_its_installer(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, responses=[_payload(f"v{NEWER}")])

    result = service.check_result(force=True)

    assert result.update_available is True
    assert result.info is not None
    assert result.info.version == NEWER
    assert result.info.installer_url == INSTALLER_URL


def test_check_still_collapses_the_outcome_to_the_update_or_none(tmp_path: Path) -> None:
    """``check()`` is what the automatic path calls, and its contract is unchanged."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    current, _ = _service(tmp_path / "a", responses=[_payload(f"v{CURRENT}")])
    assert current.check(force=True) is None

    newer, _ = _service(tmp_path / "b", responses=[_payload(f"v{NEWER}")])
    found = newer.check(force=True)
    assert found is not None and found.version == NEWER


def test_the_env_var_still_forces_a_check_without_the_parameter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The QA affordance predates the parameter and keeps working beside it."""
    first, _ = _service(tmp_path, responses=[_payload(f"v{CURRENT}")])
    first.check()

    monkeypatch.setenv(FORCE_CHECK_ENV_VAR, "1")
    second, second_calls = _service(tmp_path, responses=[_payload(f"v{NEWER}")])
    result = second.check_result()

    assert len(second_calls) == 1
    assert result.outcome == OUTCOME_UPDATE_AVAILABLE


def test_a_transport_failure_reaches_the_user_as_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Through the real ``_fetch_latest_release``, with ``requests`` stubbed out.

    The seam every other test replaces is exercised here exactly once, so
    "unreachable" is known to be what an actual failed request produces rather
    than only what the fake queue's ``None`` produces.
    """
    import services.update_service as update_service

    attempts: list[str] = []

    def _no_network(url: str, **_kwargs: Any) -> Any:
        attempts.append(url)
        raise OSError("getaddrinfo failed")

    monkeypatch.setattr(update_service.requests, "get", _no_network)
    service = UpdateService(
        current_version=CURRENT,
        cache_path=tmp_path / "update_check.json",
        api_url="https://api.github.test/latest",
    )

    result = service.check_result(force=True)

    assert attempts == ["https://api.github.test/latest"]
    assert result.outcome == OUTCOME_UNREACHABLE
    assert not (tmp_path / "update_check.json").exists()


# ---------------------------------------------------------------------------
# The controller: off the UI thread, and one request per question
# ---------------------------------------------------------------------------


class _DeferredWorker:
    """Holds submitted work until :meth:`run` — i.e. behaves like a real thread.

    Inline execution would make "the UI thread is not blocked" untestable: the
    assertion is precisely that ``check_for_update_now`` returns *before* the
    service is consulted.
    """

    def __init__(self) -> None:
        self.pending: list[tuple[Any, Any, Any]] = []

    def submit(self, func, *args, on_success=None, on_error=None, **kwargs) -> None:
        self.pending.append((lambda: func(*args, **kwargs), on_success, on_error))

    def run(self) -> None:
        while self.pending:
            func, on_success, on_error = self.pending.pop(0)
            try:
                result = func()
            except Exception as exc:  # pragma: no cover - only if a stub raises
                if on_error:
                    on_error(exc)
                continue
            if on_success:
                on_success(result)


class _Controller(UpdateCheckMixin):
    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled
        self._worker = _DeferredWorker()
        self._ui_callbacks = None
        self._available_update: UpdateInfo | None = None
        self._update_check_in_flight = False
        self._update_installer = None
        self.frame = None

    def get_update_check_enabled(self) -> bool:
        return self._enabled


def _stub_service(monkeypatch: pytest.MonkeyPatch, result: CheckResult) -> dict[str, Any]:
    """Replace the service singleton; record how it was asked."""
    import services.update_service as update_service

    seen: dict[str, Any] = {"checks": 0, "forced": []}

    class _StubService:
        def check_result(self, *, force: bool = False) -> CheckResult:
            seen["checks"] += 1
            seen["forced"].append(force)
            return result

    monkeypatch.setattr(update_service, "get_update_service", lambda: _StubService())
    return seen


def test_the_request_runs_on_the_worker_not_on_the_calling_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info = UpdateInfo(version=NEWER, release_url="https://github.test/r")
    seen = _stub_service(monkeypatch, CheckResult(OUTCOME_UPDATE_AVAILABLE, info, CURRENT))
    controller = _Controller()
    results: list[CheckResult] = []

    assert controller.check_for_update_now(results.append) is True
    assert seen["checks"] == 0, "the check ran before check_for_update_now returned"
    assert results == []

    controller._worker.run()

    assert seen["checks"] == 1
    assert seen["forced"] == [True], "the menu item did not force the check"
    assert [r.info for r in results] == [info]
    assert controller.get_available_update() == info


def test_a_second_request_while_one_is_in_flight_is_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two clicks are one question: one request, one dialog."""
    seen = _stub_service(monkeypatch, CheckResult(OUTCOME_UP_TO_DATE, None, CURRENT))
    controller = _Controller()
    results: list[CheckResult] = []

    assert controller.check_for_update_now(results.append) is True
    assert controller.is_update_check_running() is True
    assert controller.check_for_update_now(results.append) is False

    controller._worker.run()

    assert seen["checks"] == 1
    assert len(results) == 1
    assert controller.is_update_check_running() is False


def test_the_next_request_after_one_finishes_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _stub_service(monkeypatch, CheckResult(OUTCOME_UP_TO_DATE, None, CURRENT))
    controller = _Controller()

    assert controller.check_for_update_now(lambda _r: None) is True
    controller._worker.run()
    assert controller.check_for_update_now(lambda _r: None) is True
    controller._worker.run()

    assert seen["checks"] == 2


def test_an_unreachable_check_reaches_the_caller_rather_than_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_service(monkeypatch, CheckResult(OUTCOME_UNREACHABLE, None, CURRENT))
    controller = _Controller()
    results: list[CheckResult] = []

    controller.check_for_update_now(results.append)
    controller._worker.run()

    assert [r.outcome for r in results] == [OUTCOME_UNREACHABLE]
    assert controller.is_update_check_running() is False


def test_an_unforeseen_failure_is_reported_instead_of_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``check_result`` absorbs its own failures, so this is belt and braces —
    and the one thing this feature must never do is leave the click unanswered."""
    import services.update_service as update_service

    class _Exploding:
        def check_result(self, *, force: bool = False) -> CheckResult:
            raise RuntimeError("msgspec said no")

    monkeypatch.setattr(update_service, "get_update_service", lambda: _Exploding())
    controller = _Controller()
    results: list[CheckResult] = []

    controller.check_for_update_now(results.append)
    controller._worker.run()

    assert [r.outcome for r in results] == [OUTCOME_UNREACHABLE]
    assert controller.is_update_check_running() is False


def test_the_menu_item_works_with_the_automatic_check_turned_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The preference governs the *unasked-for* check, not an explicit request."""
    seen = _stub_service(monkeypatch, CheckResult(OUTCOME_UP_TO_DATE, None, CURRENT))
    controller = _Controller(enabled=False)

    assert controller.check_for_update_now(lambda _r: None) is True
    controller._worker.run()
    assert seen["checks"] == 1

    # ...while the automatic one still respects it.
    controller.check_for_update()
    controller._worker.run()
    assert seen["checks"] == 1


# ---------------------------------------------------------------------------
# The frame: the menu entry, and each outcome reaching the user
# ---------------------------------------------------------------------------


class _FrameStub:
    """Just enough of ``AppFrame`` for the three handlers under test.

    The methods under test are borrowed off the mixin rather than inherited,
    because inheriting it would pull in the whole frame protocol for no added
    coverage while still leaving the other menus' handlers to be stubbed. ``_t``
    returns the key plus its arguments so the assertions can be about *which*
    string was chosen without pinning the English copy.
    """

    _check_for_updates_now = _handlers.AppFrameHandlersMixin._check_for_updates_now
    _on_update_check_finished = _handlers.AppFrameHandlersMixin._on_update_check_finished
    _file_menu_entries = _handlers.AppFrameHandlersMixin._file_menu_entries

    def __init__(self, *, started: bool = True) -> None:
        self.started = started
        self.statuses: list[tuple[str, dict[str, Any]]] = []
        self.notices: list[tuple[str, str]] = []
        self.available: list[UpdateInfo] = []
        self.opened = 0
        self.requests = 0
        self.controller = self
        # The File menu's other entries. Only their existence matters here --
        # ``_file_menu_entries`` reads them to build the entries it returns.
        self.on_load_deck_clicked = lambda: None
        self.on_save_clicked = lambda _evt=None: None
        self._open_feedback_dialog = lambda: None
        self._open_preferences = lambda: None
        self.image_cache = None
        self.image_downloader = None

    # -- the bits the handlers touch -------------------------------------
    def _t(self, key: str, **kwargs: Any) -> str:
        return f"{key}|{sorted(kwargs.items())}" if kwargs else key

    def _set_status(self, key: str, **kwargs: Any) -> None:
        self.statuses.append((key, kwargs))

    def _on_update_available(self, info: UpdateInfo) -> None:
        self.available.append(info)

    def _open_update(self) -> None:
        self.opened += 1

    def check_for_update_now(self, on_result: Any) -> bool:
        self.requests += 1
        self.on_result = on_result
        return self.started


@pytest.fixture(name="frame")
def fixture_frame(monkeypatch: pytest.MonkeyPatch) -> _FrameStub:
    """A stub frame with the notice dialog replaced by a recorder."""
    stub = _FrameStub()
    monkeypatch.setattr(
        _handlers,
        "show_update_check_notice",
        lambda _parent, heading, body: stub.notices.append((heading, body)),
    )
    return stub


def test_picking_the_menu_item_starts_a_check_and_says_so(frame: _FrameStub) -> None:
    frame._check_for_updates_now()

    assert frame.requests == 1
    assert frame.statuses == [("app.status.checking_for_updates", {})]


def test_picking_it_twice_says_one_is_already_running(frame: _FrameStub) -> None:
    frame.started = False

    frame._check_for_updates_now()

    assert frame.statuses == [("app.status.update_check_running", {})]


def test_an_up_to_date_result_names_the_running_version(frame: _FrameStub) -> None:
    frame._on_update_check_finished(CheckResult(OUTCOME_UP_TO_DATE, None, CURRENT))

    assert frame.statuses == [("app.status.update_check_current", {"version": CURRENT})]
    assert len(frame.notices) == 1
    heading, body = frame.notices[0]
    assert heading == "app.update_check.current.heading"
    assert body == f"app.update_check.current.body|[('version', '{CURRENT}')]"
    assert frame.opened == 0


def test_an_unreachable_result_says_so_rather_than_nothing(frame: _FrameStub) -> None:
    frame._on_update_check_finished(CheckResult(OUTCOME_UNREACHABLE, None, CURRENT))

    assert frame.statuses == [("app.status.update_check_failed", {})]
    assert frame.notices == [
        ("app.update_check.failed.heading", "app.update_check.failed.body"),
    ]
    assert frame.available == []
    assert frame.opened == 0


def test_an_unreachable_result_holding_a_cached_update_still_reports_the_failure(
    frame: _FrameStub,
) -> None:
    """The stale answer is not presented as the answer to *this* question."""
    info = UpdateInfo(version=NEWER, release_url="https://github.test/r")

    frame._on_update_check_finished(CheckResult(OUTCOME_UNREACHABLE, info, CURRENT))

    assert frame.statuses == [("app.status.update_check_failed", {})]
    assert frame.opened == 0


def test_a_newer_release_gets_the_same_surface_the_automatic_check_uses(
    frame: _FrameStub,
) -> None:
    info = UpdateInfo(version=NEWER, release_url="https://github.test/r")

    frame._on_update_check_finished(CheckResult(OUTCOME_UPDATE_AVAILABLE, info, CURRENT))

    assert frame.available == [info], "the status note and Help entry were skipped"
    assert frame.opened == 1, "the update prompt did not open"
    assert frame.notices == [], "a newer release must not get the no-update notice"
    assert frame.statuses == [("app.status.update_available", {"version": NEWER})]


def test_the_file_menu_carries_the_entry_that_starts_it(frame: _FrameStub) -> None:
    """Without this the feature is unreachable however well the rest behaves."""
    from widgets.menu_bar.spec import invoke_entry

    entries = frame._file_menu_entries()
    labels = [entry.label for entry in entries]

    assert "menu.check_for_updates" in labels
    assert invoke_entry(entries, ["menu.check_for_updates"]) is True
    assert frame.requests == 1
