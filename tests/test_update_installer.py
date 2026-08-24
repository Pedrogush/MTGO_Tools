"""Unit tests for applying an in-app update (issue #142).

No network is exercised: ``requests.get`` is the single seam the installer uses
and every test replaces it with a scripted responder, so a test that would
otherwise reach GitHub fails loudly with "unexpected URL" instead. Likewise
``subprocess.Popen`` is stubbed in the launch tests — the whole point of that
method is that it starts a process and returns, so what is asserted is the
argument vector and the detach flags, not a running installer.

The bias throughout is toward the failure paths. The success path deletes
nothing and executes a binary; the failure paths are where "leaves no partial
file" and "never launches an unverified file" actually have to hold.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import requests

import services.update_installer as update_installer
from services.update_installer import (
    INSTALLER_SWITCHES,
    ChecksumMismatch,
    ChecksumUnavailable,
    DownloadFailed,
    LaunchFailed,
    ReleaseUnavailable,
    UpdateCancelled,
    UpdateError,
    UpdateInstaller,
    UpdateNotDownloadable,
    can_auto_update,
    parse_sha256_sidecar,
)
from services.update_service import UpdateInfo

INSTALLER_NAME = "MTGOTools_Setup_v1.0.3.exe"
INSTALLER_URL = "https://example.test/download/MTGOTools_Setup_v1.0.3.exe"
CHECKSUM_URL = f"{INSTALLER_URL}.sha256"
INSTALLER_BYTES = b"MZ fake installer payload" * 64
INSTALLER_SHA256 = hashlib.sha256(INSTALLER_BYTES).hexdigest()


def _info(**overrides: Any) -> UpdateInfo:
    fields: dict[str, Any] = {
        "version": "1.0.3",
        "release_url": "https://example.test/releases/v1.0.3",
        "installer_url": INSTALLER_URL,
        "checksum_url": CHECKSUM_URL,
        "installer_name": INSTALLER_NAME,
    }
    fields.update(overrides)
    return UpdateInfo(**fields)


class _FakeResponse:
    """Just enough of ``requests.Response`` for the two calls under test."""

    def __init__(
        self,
        *,
        text: str = "",
        chunks: list[bytes] | None = None,
        status_error: Exception | None = None,
        chunk_error: Exception | None = None,
        content_length: str | None = None,
        status_code: int = 200,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self._chunks = chunks or []
        self._status_error = status_error
        self._chunk_error = chunk_error
        self.headers: dict[str, str] = {}
        if content_length is not None:
            self.headers["Content-Length"] = content_length
        self.closed = False

    def raise_for_status(self) -> None:
        if self._status_error is not None:
            raise self._status_error

    def iter_content(self, chunk_size: int = 1) -> Any:
        yield from self._chunks
        if self._chunk_error is not None:
            raise self._chunk_error

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.closed = True


def _installer_response(**overrides: Any) -> _FakeResponse:
    fields: dict[str, Any] = {
        "chunks": [INSTALLER_BYTES[:100], INSTALLER_BYTES[100:]],
        "content_length": str(len(INSTALLER_BYTES)),
    }
    fields.update(overrides)
    return _FakeResponse(**fields)


def _sidecar_response(digest: str = INSTALLER_SHA256, name: str = INSTALLER_NAME) -> _FakeResponse:
    return _FakeResponse(text=f"{digest}  {name}\n")


def _recorder() -> tuple[list[tuple[int, int | None]], Any]:
    """A progress callback plus the list of ``(done, total)`` pairs it records."""
    seen: list[tuple[int, int | None]] = []

    def _record(done: int, total: int | None) -> None:
        seen.append((done, total))

    return seen, _record


def _http(monkeypatch: pytest.MonkeyPatch, routes: dict[str, Any]) -> list[str]:
    """Route ``requests.get`` by URL; return the list of URLs actually requested.

    A route value that is an exception instance is raised instead of returned,
    which is how transport failures are simulated. Any URL not in ``routes`` is
    an assertion failure, so a test can prove a request was *never* made.
    """
    requested: list[str] = []

    def _fake_get(url: str, **_kwargs: Any) -> Any:
        requested.append(url)
        assert url in routes, f"unexpected URL requested: {url}"
        result = routes[url]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(update_installer.requests, "get", _fake_get)
    return requested


# ---------------------------------------------------------------------------
# parse_sha256_sidecar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        f"{INSTALLER_SHA256}  {INSTALLER_NAME}\n",  # exactly what CI publishes
        f"{INSTALLER_SHA256}  {INSTALLER_NAME}\r\n",  # a CRLF checkout of it
        f"{INSTALLER_SHA256} {INSTALLER_NAME}",  # one space, no newline
        f"{INSTALLER_SHA256}\t{INSTALLER_NAME}\n",  # tab-separated
        f"{INSTALLER_SHA256}  *{INSTALLER_NAME}\n",  # sha256sum's binary marker
        f"\n\n{INSTALLER_SHA256}  {INSTALLER_NAME}\n",  # leading blank lines
        f"  {INSTALLER_SHA256}  {INSTALLER_NAME}  \n",  # surrounding whitespace
        f"{INSTALLER_SHA256}\n",  # digest alone, no filename
        f"{INSTALLER_SHA256.upper()}  {INSTALLER_NAME}\n",  # uppercase hex
    ],
)
def test_the_sidecar_parser_tolerates_whitespace_and_case_variations(text: str) -> None:
    assert parse_sha256_sidecar(text, expected_filename=INSTALLER_NAME) == INSTALLER_SHA256


@pytest.mark.parametrize(
    "text",
    [
        "",  # empty file
        "\n \n",  # blank lines only
        f"{INSTALLER_SHA256[:32]}  {INSTALLER_NAME}\n",  # truncated digest
        f"{INSTALLER_SHA256}ab  {INSTALLER_NAME}\n",  # too long
        f"{'z' * 64}  {INSTALLER_NAME}\n",  # not hex
        "<html><body>404 Not Found</body></html>\n",  # an error page
        f"SHA256: {INSTALLER_SHA256}\n",  # prose, not sha256sum format
    ],
)
def test_the_sidecar_parser_rejects_anything_it_cannot_read_with_certainty(text: str) -> None:
    assert parse_sha256_sidecar(text, expected_filename=INSTALLER_NAME) is None


def test_a_sidecar_naming_a_different_build_is_rejected() -> None:
    # Otherwise the checksum of some other release would be applied to this one.
    text = f"{INSTALLER_SHA256}  MTGOTools_Setup_v9.9.9.exe\n"

    assert parse_sha256_sidecar(text, expected_filename=INSTALLER_NAME) is None


def test_the_sidecar_parser_does_not_scan_past_a_line_it_cannot_read() -> None:
    # A file whose first line is unreadable is not one to go hunting through for
    # something digest-shaped; it is a file that failed to be a checksum.
    text = f"garbage first line\n{INSTALLER_SHA256}  {INSTALLER_NAME}\n"

    assert parse_sha256_sidecar(text) is None


# ---------------------------------------------------------------------------
# can_auto_update
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("info", "expected"),
    [
        (_info(), True),
        (_info(installer_url=None), False),
        (_info(checksum_url=None), False),
        (UpdateInfo(version="1.0.3", release_url="https://x.test"), False),
        (None, False),
    ],
)
def test_can_auto_update_requires_both_halves_of_the_asset_pair(
    info: UpdateInfo | None, expected: bool
) -> None:
    assert can_auto_update(info) is expected


def test_downloading_a_release_with_no_installer_asset_raises_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested = _http(monkeypatch, {})
    installer = UpdateInstaller(
        UpdateInfo(version="1.0.3", release_url="https://x.test"), temp_root=tmp_path
    )

    with pytest.raises(UpdateNotDownloadable):
        installer.download()

    assert not requested


# ---------------------------------------------------------------------------
# download: the happy path
# ---------------------------------------------------------------------------


def test_download_stores_a_verified_installer_and_returns_its_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _http(
        monkeypatch,
        {CHECKSUM_URL: _sidecar_response(), INSTALLER_URL: _installer_response()},
    )
    installer = UpdateInstaller(_info(), temp_root=tmp_path)

    path = installer.download()

    assert path.read_bytes() == INSTALLER_BYTES
    assert path.name == INSTALLER_NAME
    assert path.parent.parent == tmp_path  # its own directory under the temp root
    assert installer.installer_path == path


def test_download_fetches_the_checksum_before_the_installer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Ordering is the point: a missing checksum must cost nothing to discover.
    requested = _http(
        monkeypatch,
        {CHECKSUM_URL: _sidecar_response(), INSTALLER_URL: _installer_response()},
    )

    UpdateInstaller(_info(), temp_root=tmp_path).download()

    assert requested == [CHECKSUM_URL, INSTALLER_URL]


def test_download_reports_progress_starting_with_the_total(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _http(
        monkeypatch,
        {CHECKSUM_URL: _sidecar_response(), INSTALLER_URL: _installer_response()},
    )
    seen, record = _recorder()

    UpdateInstaller(_info(), temp_root=tmp_path).download(progress=record)

    assert seen[0] == (0, len(INSTALLER_BYTES))
    assert seen[-1] == (len(INSTALLER_BYTES), len(INSTALLER_BYTES))
    assert [done for done, _total in seen] == sorted(done for done, _total in seen)


@pytest.mark.parametrize("content_length", [None, "", "unknown", "0", "-5"])
def test_progress_reports_no_total_when_the_server_gives_no_usable_length(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content_length: str | None
) -> None:
    # A progress bar sized from a bad total is worse than an indeterminate one.
    _http(
        monkeypatch,
        {
            CHECKSUM_URL: _sidecar_response(),
            INSTALLER_URL: _installer_response(content_length=content_length),
        },
    )
    seen, record = _recorder()

    UpdateInstaller(_info(), temp_root=tmp_path).download(progress=record)

    assert all(total is None for _done, total in seen)


def test_an_installer_name_carrying_path_separators_cannot_escape_the_temp_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hostile = "../../evil.exe"
    _http(
        monkeypatch,
        {
            CHECKSUM_URL: _sidecar_response(name=hostile),
            INSTALLER_URL: _installer_response(),
        },
    )
    installer = UpdateInstaller(_info(installer_name=hostile), temp_root=tmp_path)

    path = installer.download()

    assert path.name == "evil.exe"
    assert path.parent.parent == tmp_path


# ---------------------------------------------------------------------------
# download: verification failures
# ---------------------------------------------------------------------------


def test_a_checksum_mismatch_deletes_the_download_and_raises_its_own_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _http(
        monkeypatch,
        {
            CHECKSUM_URL: _sidecar_response(digest="a" * 64),
            INSTALLER_URL: _installer_response(),
        },
    )
    installer = UpdateInstaller(_info(), temp_root=tmp_path)

    with pytest.raises(ChecksumMismatch):
        installer.download()

    assert list(tmp_path.iterdir()) == []
    assert installer.installer_path is None


def test_a_checksum_mismatch_leaves_nothing_launchable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The guarantee that matters most: a UI that swallows the error and calls
    # launch() anyway still cannot execute the rejected file.
    _http(
        monkeypatch,
        {
            CHECKSUM_URL: _sidecar_response(digest="a" * 64),
            INSTALLER_URL: _installer_response(),
        },
    )
    installer = UpdateInstaller(_info(), temp_root=tmp_path)
    with pytest.raises(ChecksumMismatch):
        installer.download()

    def _never(*_args: Any, **_kwargs: Any) -> Any:  # pragma: no cover - must not run
        raise AssertionError("launched an unverified installer")

    monkeypatch.setattr(update_installer.subprocess, "Popen", _never)

    with pytest.raises(LaunchFailed):
        installer.launch()


@pytest.mark.parametrize(
    "sidecar",
    [
        _FakeResponse(text="not a checksum at all\n"),
        _FakeResponse(text=""),
        _FakeResponse(text=f"{INSTALLER_SHA256[:16]}  {INSTALLER_NAME}\n"),
    ],
)
def test_an_unreadable_sidecar_aborts_before_downloading_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sidecar: _FakeResponse
) -> None:
    requested = _http(monkeypatch, {CHECKSUM_URL: sidecar})

    with pytest.raises(ChecksumUnavailable):
        UpdateInstaller(_info(), temp_root=tmp_path).download()

    assert requested == [CHECKSUM_URL]
    assert list(tmp_path.iterdir()) == []


def test_a_missing_sidecar_aborts_rather_than_skipping_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # There is no verification-optional mode: no checksum, no execution.
    _http(monkeypatch, {CHECKSUM_URL: requests.ConnectionError("offline")})

    with pytest.raises(ChecksumUnavailable):
        UpdateInstaller(_info(), temp_root=tmp_path).download()


# ---------------------------------------------------------------------------
# download: network failures and cancellation
# ---------------------------------------------------------------------------


def test_a_network_failure_mid_download_is_reported_as_a_download_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _http(
        monkeypatch,
        {
            CHECKSUM_URL: _sidecar_response(),
            INSTALLER_URL: _installer_response(
                chunks=[INSTALLER_BYTES[:100]],
                chunk_error=requests.ConnectionError("connection reset"),
            ),
        },
    )
    installer = UpdateInstaller(_info(), temp_root=tmp_path)

    with pytest.raises(DownloadFailed) as caught:
        installer.download()

    # Distinct from a checksum failure: this one means "try again later", and a
    # UI that treated the two alike would tell users their download was tampered
    # with every time their wifi dropped.
    assert not isinstance(caught.value, ChecksumMismatch)
    assert list(tmp_path.iterdir()) == []


def test_an_http_error_on_the_installer_is_a_download_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _http(
        monkeypatch,
        {
            CHECKSUM_URL: _sidecar_response(),
            INSTALLER_URL: _installer_response(status_error=requests.HTTPError("404 Client Error")),
        },
    )

    with pytest.raises(DownloadFailed):
        UpdateInstaller(_info(), temp_root=tmp_path).download()

    assert list(tmp_path.iterdir()) == []


def test_cancelling_mid_download_raises_and_removes_the_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _http(
        monkeypatch,
        {
            CHECKSUM_URL: _sidecar_response(),
            INSTALLER_URL: _installer_response(
                chunks=[INSTALLER_BYTES[:100], INSTALLER_BYTES[100:]]
            ),
        },
    )
    installer = UpdateInstaller(_info(), temp_root=tmp_path)

    def _cancel_after_first_chunk(done: int, _total: int | None) -> None:
        if done:
            installer.cancel()

    with pytest.raises(UpdateCancelled):
        installer.download(progress=_cancel_after_first_chunk)

    assert installer.cancelled
    assert list(tmp_path.iterdir()) == []
    assert installer.installer_path is None


def test_cancelling_before_the_download_starts_skips_the_transfer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested = _http(monkeypatch, {CHECKSUM_URL: _sidecar_response()})
    installer = UpdateInstaller(_info(), temp_root=tmp_path)
    installer.cancel()

    with pytest.raises(UpdateCancelled):
        installer.download()

    assert requested == [CHECKSUM_URL]


def test_every_failure_is_an_update_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # The UI needs one except clause it can rely on to leave the app running,
    # underneath the specific ones it uses to word the message.
    _http(monkeypatch, {CHECKSUM_URL: _FakeResponse(text="nonsense")})

    with pytest.raises(UpdateError):
        UpdateInstaller(_info(), temp_root=tmp_path).download()


# ---------------------------------------------------------------------------
# a release that is gone
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [404, 410])
def test_a_pulled_release_is_reported_as_gone_not_as_a_broken_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    # The sidecar is fetched first, so a release deleted between the update check
    # and the click is discovered on *that* request. Flattened into
    # ChecksumUnavailable it would tell the user the release is fine and its
    # checksum is broken, and invite them to install it by hand from a release
    # page that no longer exists.
    requested = _http(monkeypatch, {CHECKSUM_URL: _FakeResponse(status_code=status)})
    installer = UpdateInstaller(_info(), temp_root=tmp_path)

    with pytest.raises(ReleaseUnavailable):
        installer.download()

    # And the 175 MB was never started: the answer was known from ~100 bytes.
    assert requested == [CHECKSUM_URL]


def test_a_pulled_release_carries_no_replacement_of_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # This module does not know about the throttled check in update_service, so
    # it never fills this in; the controller does, after re-checking. None here
    # means "nobody looked", not "nothing newer exists".
    _http(monkeypatch, {CHECKSUM_URL: _FakeResponse(status_code=404)})

    with pytest.raises(ReleaseUnavailable) as caught:
        UpdateInstaller(_info(), temp_root=tmp_path).download()

    assert caught.value.replacement is None


def test_an_installer_asset_that_is_gone_is_also_reported_as_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Reachable when the installer outlives its sidecar, or when a prune lands
    # between the two requests. The generic ``except Exception`` in the download
    # loop catches UpdateError subclasses too, so this asserts the specific
    # clause that lets this one back out.
    _http(
        monkeypatch,
        {CHECKSUM_URL: _sidecar_response(), INSTALLER_URL: _FakeResponse(status_code=404)},
    )
    installer = UpdateInstaller(_info(), temp_root=tmp_path)

    with pytest.raises(ReleaseUnavailable):
        installer.download()

    assert installer.installer_path is None
    assert not list(tmp_path.iterdir())  # no half-written file left behind


def test_an_ordinary_bad_status_is_still_an_ordinary_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 500 means "try again later" and must not be mistaken for "this release is
    # gone" — the difference decides whether the app re-checks or retries.
    _http(
        monkeypatch,
        {CHECKSUM_URL: _FakeResponse(status_code=500, status_error=requests.HTTPError("boom"))},
    )

    with pytest.raises(ChecksumUnavailable):
        UpdateInstaller(_info(), temp_root=tmp_path).download()


# ---------------------------------------------------------------------------
# launch
# ---------------------------------------------------------------------------


def _capture_popen(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def _fake_popen(command: list[str], **kwargs: Any) -> Any:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(update_installer.subprocess, "Popen", _fake_popen)
    return captured


def test_launch_runs_the_verified_installer_silently_with_relaunch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _http(
        monkeypatch,
        {CHECKSUM_URL: _sidecar_response(), INSTALLER_URL: _installer_response()},
    )
    captured = _capture_popen(monkeypatch)
    installer = UpdateInstaller(_info(), temp_root=tmp_path)
    path = installer.download()

    installer.launch()

    assert captured["command"] == [str(path), *INSTALLER_SWITCHES]
    assert INSTALLER_SWITCHES == ("/SILENT", "/NORESTART", "/RELAUNCH")


def test_launch_detaches_the_installer_from_this_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Setup has to outlive the app: the app exiting is what frees the files it
    # replaces. An ordinary child would also inherit the console and the app's
    # working directory, which is the directory being overwritten.
    _http(
        monkeypatch,
        {CHECKSUM_URL: _sidecar_response(), INSTALLER_URL: _installer_response()},
    )
    captured = _capture_popen(monkeypatch)
    installer = UpdateInstaller(_info(), temp_root=tmp_path)
    path = installer.download()

    installer.launch()

    kwargs = captured["kwargs"]
    assert kwargs["close_fds"] is True
    assert kwargs["cwd"] == str(path.parent)
    assert kwargs["stdin"] == subprocess.DEVNULL
    if sys.platform == "win32":
        flags = kwargs["creationflags"]
        assert flags & subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
        assert flags & subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        assert kwargs["start_new_session"] is True


def test_launch_does_not_hand_the_installer_the_bootloader_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The regression this guards: a onefile build advertises its %TEMP% unpack
    # directory through these variables, Setup inherits them, and the app Setup
    # relaunches inherits them from Setup — then loads Python from a directory
    # the exiting app already deleted and dies with "Failed to load Python DLL
    # ...\_MEIxxxxxx\python3xx.dll" before any of this project's code runs.
    _http(
        monkeypatch,
        {CHECKSUM_URL: _sidecar_response(), INSTALLER_URL: _installer_response()},
    )
    captured = _capture_popen(monkeypatch)
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", r"C:\Temp\_MEI123456")
    monkeypatch.setenv("_PYI_ARCHIVE_FILE", r"C:\Programs\MTGO Tools\mtgo_tools.exe")
    monkeypatch.setenv("_PYI_PARENT_PROCESS_LEVEL", "1")
    monkeypatch.setenv("_MEIPASS2", r"C:\Temp\_MEI123456")
    monkeypatch.setenv("MTGO_TOOLS_MARKER", "kept")
    installer = UpdateInstaller(_info(), temp_root=tmp_path)
    installer.download()

    installer.launch()

    env = captured["kwargs"]["env"]
    assert not [key for key in env if key.startswith(("_PYI", "_MEIPASS"))]
    # Only those are dropped: Setup is an ordinary Windows program and needs the
    # rest of the user's environment (TEMP, PATH, the profile directories).
    assert env["MTGO_TOOLS_MARKER"] == "kept"


def test_launch_leaves_this_process_environment_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The app is still running and still spawning multiprocessing workers, which
    # need those variables to reuse the unpacked bundle instead of unpacking a
    # second copy. Filtering has to be per-child, not a mutation of os.environ.
    _http(
        monkeypatch,
        {CHECKSUM_URL: _sidecar_response(), INSTALLER_URL: _installer_response()},
    )
    _capture_popen(monkeypatch)
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", r"C:\Temp\_MEI123456")
    installer = UpdateInstaller(_info(), temp_root=tmp_path)
    installer.download()

    installer.launch()

    assert os.environ["_PYI_APPLICATION_HOME_DIR"] == r"C:\Temp\_MEI123456"


def test_launch_without_a_download_fails_instead_of_running_something_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _capture_popen(monkeypatch)

    with pytest.raises(LaunchFailed):
        UpdateInstaller(_info(), temp_root=tmp_path).launch()


def test_a_spawn_failure_is_reported_as_its_own_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _http(
        monkeypatch,
        {CHECKSUM_URL: _sidecar_response(), INSTALLER_URL: _installer_response()},
    )
    installer = UpdateInstaller(_info(), temp_root=tmp_path)
    installer.download()

    def _boom(*_args: Any, **_kwargs: Any) -> Any:
        raise OSError("access denied")

    monkeypatch.setattr(update_installer.subprocess, "Popen", _boom)

    with pytest.raises(LaunchFailed):
        installer.launch()


def test_launch_leaves_the_downloaded_file_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Setup is running from it; deleting it here would kill the update.
    _http(
        monkeypatch,
        {CHECKSUM_URL: _sidecar_response(), INSTALLER_URL: _installer_response()},
    )
    _capture_popen(monkeypatch)
    installer = UpdateInstaller(_info(), temp_root=tmp_path)
    path = installer.download()

    installer.launch()

    assert path.is_file()


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------


def test_cleanup_removes_the_download_and_can_be_called_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # It runs on failure paths, so a second call must not raise over the error
    # the caller is already handling.
    _http(
        monkeypatch,
        {CHECKSUM_URL: _sidecar_response(), INSTALLER_URL: _installer_response()},
    )
    installer = UpdateInstaller(_info(), temp_root=tmp_path)
    installer.download()

    installer.cleanup()
    installer.cleanup()

    assert list(tmp_path.iterdir()) == []


def test_cleanup_on_an_untouched_installer_does_nothing(tmp_path: Path) -> None:
    UpdateInstaller(_info(), temp_root=tmp_path).cleanup()

    assert list(tmp_path.iterdir()) == []
