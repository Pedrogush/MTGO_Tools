"""Download, verify and run the installer for a newer release (issue #142).

:mod:`services.update_service` answers "is there a newer release?"; this module
answers "apply it". The sequence is deliberately three separate steps the caller
drives — :meth:`UpdateInstaller.download`, then :meth:`UpdateInstaller.launch`,
then the caller exits the app — because the last one is not this module's to
take: only the UI knows whether unsaved work is on screen.

Public API:

- :func:`can_auto_update` — does this :class:`~services.update_service.UpdateInfo`
  carry the assets needed to apply it in-app?
- :class:`UpdateInstaller` — ``download()`` / ``launch()`` / ``cancel()`` /
  ``cleanup()`` over one update.
- :func:`parse_sha256_sidecar` — the ``sha256sum``-format parser, exposed
  because it is the part worth testing on its own.
- :class:`UpdateError` and its subclasses — one per outcome the UI needs to
  describe differently.

Three properties this module exists to guarantee:

*A downloaded installer is executed only after its SHA256 matches the sidecar
published alongside it.* The app is about to run a 175 MB unsigned binary it
fetched over the network with the user's privileges. A mismatch is not a
recoverable hiccup to retry past: the file is deleted, :class:`ChecksumMismatch`
is raised, and nothing is executed. Nothing in here may grow a path that runs an
unverified file — not a fallback, not a "the sidecar 404'd so skip it".

*Every failure is typed.* "The update failed" is not a message anyone can act
on. Network trouble suggests trying later, a checksum mismatch suggests
downloading from the release page by hand, a cancellation needs no message at
all — so they are distinct exception classes rather than one exception with
prose in it.

*No wx, no app singletons, no global state.* This runs on a worker thread, and
its whole surface is testable headlessly on Linux, where the only Windows-specific
part (detached process creation) degrades to the POSIX equivalent.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess  # nosec B404 - running the downloaded installer is the point
import sys
import tempfile
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import requests
from loguru import logger

from services.update_service import UpdateInfo
from utils.constants import UPDATE_DOWNLOAD_CHUNK_SIZE, UPDATE_DOWNLOAD_TIMEOUT_SECONDS

# Switches passed to the downloaded Setup. ``/SILENT`` because the user already
# confirmed in the app's own dialog and a second wizard would be noise;
# ``/NORESTART`` because an installer deciding on its own to reboot a machine
# mid-session is never acceptable; ``/RELAUNCH`` because the app has to exit for
# its files to be replaced, so the installer is what puts it back on screen
# (packaging/installer.iss).
INSTALLER_SWITCHES: tuple[str, ...] = ("/SILENT", "/NORESTART", "/RELAUNCH")

# Bootloader variables that must not reach the installer (issue: "_MEI" DLL error
# after an in-app update).
#
# A PyInstaller onefile app runs from a directory it unpacked into %TEMP%
# (``_MEIxxxxxx``) and advertises that directory to its own child processes
# through these environment variables — that is how a re-executed child, such as
# a ``multiprocessing`` "spawn" worker, reuses the unpacked bundle instead of
# unpacking a second copy. They live in ``os.environ``, so *every* child this app
# starts inherits them, including one that is not a child of the bundle at all.
#
# That is what breaks an update. Setup inherits them, Setup's ``/RELAUNCH`` entry
# starts the freshly installed ``mtgo_tools.exe`` and it inherits them in turn —
# and the bootloader's test for "am I a re-executed child?" is whether
# ``_PYI_ARCHIVE_FILE`` names the executable now running. After an update it does:
# the new build sits at the same path as the old one. So the new process trusts
# ``_PYI_APPLICATION_HOME_DIR``, which points into the *old* app's unpack
# directory — deleted seconds earlier when that app exited — and dies before
# Python starts with ``Failed to load Python DLL '...\_MEIxxxxxx\python3xx.dll'``.
#
# Stripping them for this one child is the whole fix: with no inherited state to
# trust, the new process unpacks its own bundle the way a fresh start does.
# ``_MEIPASS2`` is the pre-6.0 spelling, kept so a rollback of the pinned
# PyInstaller cannot quietly reopen this.
#
# Only the installer's environment is filtered. The variables are load-bearing
# for the app's own ``multiprocessing`` children, which must keep them.
_BOOTLOADER_ENV_VARS: tuple[str, ...] = (
    "_PYI_APPLICATION_HOME_DIR",
    "_PYI_ARCHIVE_FILE",
    "_PYI_PARENT_PROCESS_LEVEL",
    "_PYI_SPLASH_IPC",
    "_MEIPASS2",
)

# Where the download lands. Not the install directory (%LOCALAPPDATA%\Programs
# is exactly what the installer is about to overwrite, and writing into it can
# need rights the app does not have) and not the app's cache directory (the app
# prunes that, and a 175 MB binary is not cache). The user's temp directory is
# swept by Windows on its own schedule, which matters because the file cannot be
# deleted after launch — Setup is running from it.
_TEMP_DIR_PREFIX = "mtgo_tools_update_"

# A sha256sum line: the digest, then whitespace, then optionally a filename that
# may carry the ``*`` binary marker. Anchored and exactly 64 hex characters, so
# a truncated digest, a hex-looking prefix of an error page, or an HTML 404 body
# cannot be mistaken for a checksum.
_SIDECAR_LINE = re.compile(r"^(?P<digest>[0-9a-fA-F]{64})(?:[ \t]+\*?(?P<name>.*))?$")

ProgressCallback = Callable[[int, int | None], None]
"""``(bytes_done, bytes_total)``. ``bytes_total`` is ``None`` when the server
sent no usable ``Content-Length`` — the UI must handle an indeterminate total
rather than assume one."""


class UpdateError(Exception):
    """Base class for every reason an in-app update stopped."""


class DownloadFailed(UpdateError):
    """The bytes could not be fetched or stored: transport, HTTP status, disk.

    Distinct from :class:`ChecksumMismatch` on purpose: this one means "try
    again later", that one means "do not trust this file".
    """


class ChecksumUnavailable(UpdateError):
    """The ``.sha256`` sidecar could not be fetched or could not be parsed.

    Aborts the update. There is no verification-optional mode: an installer that
    cannot be checked is one this app will not run.
    """


class ChecksumMismatch(UpdateError):
    """The downloaded installer's SHA256 is not the published one.

    Corruption in transit is the benign explanation and interference is the
    other one; from here they are indistinguishable, so both end the same way —
    the file is deleted and nothing is executed.
    """


class UpdateCancelled(UpdateError):
    """The user cancelled. Not a fault; the UI should say nothing."""


class LaunchFailed(UpdateError):
    """The verified installer could not be started."""


class UpdateNotDownloadable(UpdateError):
    """This release carries no installer/checksum pair to apply.

    A caller that checked :func:`can_auto_update` first never sees this; it
    exists so that skipping the check fails loudly instead of downloading
    ``None``.
    """


def can_auto_update(info: UpdateInfo | None) -> bool:
    """Can this update be applied in-app, or only by visiting the release page?

    False is an ordinary answer — a release with no installer asset, or a stamp
    written by a build that predates these fields — and callers are expected to
    keep offering the release-page fallback for it rather than hiding the
    update.
    """
    return bool(info is not None and info.installer_url and info.checksum_url)


def parse_sha256_sidecar(text: str, *, expected_filename: str | None = None) -> str | None:
    """Extract the digest from a ``sha256sum``-format sidecar, or ``None``.

    The published sidecar is one line — ``<64 lowercase hex><two spaces><name>``
    — but this tolerates any run of spaces or tabs, a trailing CRLF, leading
    blank lines, the ``*`` binary marker GNU ``sha256sum`` writes for binary
    mode, and an uppercase digest, because none of those change what the file
    means and all of them are one CI edit away.

    What it does *not* tolerate is anything it cannot read with certainty. The
    first non-blank line either parses completely or the whole file is rejected:
    no scanning ahead for a line that happens to look like a digest, since the
    thing being parsed decides whether an executable runs. ``expected_filename``
    is likewise checked when the sidecar names a file at all — a checksum for
    *some other* build would otherwise be applied to this one and reported as a
    mismatch, or worse, match a substituted file.
    """
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _SIDECAR_LINE.match(line)
        if match is None:
            return None
        named = (match.group("name") or "").strip()
        if expected_filename and named and named.lower() != expected_filename.lower():
            logger.error(f"Checksum sidecar names {named!r}, expected {expected_filename!r}")
            return None
        return match.group("digest").lower()
    return None


class UpdateInstaller:
    """Downloads, verifies and runs the installer for one :class:`UpdateInfo`.

    Instances are single-use and are driven from a worker thread:
    :meth:`download` blocks for as long as the transfer takes, reporting
    progress through the callback, and :meth:`cancel` is the one method safe to
    call from another thread (the UI thread) while it runs.

    The temp directory holding the download belongs to the instance.
    :meth:`cleanup` removes it; :meth:`launch` deliberately does not, because
    the process it just started is running out of that directory.
    """

    def __init__(
        self,
        info: UpdateInfo,
        *,
        timeout: float = UPDATE_DOWNLOAD_TIMEOUT_SECONDS,
        chunk_size: int = UPDATE_DOWNLOAD_CHUNK_SIZE,
        temp_root: Path | None = None,
    ) -> None:
        self.info = info
        self.timeout = timeout
        self.chunk_size = chunk_size
        self.temp_root = Path(temp_root) if temp_root is not None else None
        self.installer_path: Path | None = None
        self._download_dir: Path | None = None
        self._cancelled = threading.Event()

    # ------------------------------------------------------------------ cancellation ------------------------------------------------------------------
    def cancel(self) -> None:
        """Ask an in-flight :meth:`download` to stop. Safe from any thread.

        Cancellation is cooperative and takes effect between chunks, so it is
        bounded by one socket read rather than being instant. It cannot unrun a
        launched installer — once :meth:`launch` returns, the update is applied.
        """
        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def _raise_if_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise UpdateCancelled("Update cancelled")

    # ------------------------------------------------------------------ download ------------------------------------------------------------------
    def download(self, progress: ProgressCallback | None = None) -> Path:
        """Fetch the installer to a temp directory and verify it. Returns its path.

        Raises :class:`UpdateNotDownloadable`, :class:`DownloadFailed`,
        :class:`ChecksumUnavailable`, :class:`ChecksumMismatch` or
        :class:`UpdateCancelled` — and leaves no partial file behind for any of
        them.
        """
        if not can_auto_update(self.info) or not self.info.installer_url:
            raise UpdateNotDownloadable(f"Release v{self.info.version} has no installer asset")

        # The sidecar first, and not only because it is ~100 bytes: if the thing
        # that authorizes running the installer is missing or unreadable, there
        # is no point spending a 175 MB download to find that out.
        expected_digest = self._fetch_expected_digest()
        self._raise_if_cancelled()

        target = self._prepare_target()
        actual_digest = self._stream_to_file(self.info.installer_url, target, progress)

        if actual_digest != expected_digest:
            # The one failure that must never fall through to launch(). Deleted
            # rather than kept for inspection: a file this size that the app has
            # already decided not to trust has no business surviving in temp,
            # where a later run (or a user browsing %TEMP%) could still run it.
            logger.error(
                f"Update installer checksum mismatch: expected {expected_digest}, "
                f"got {actual_digest}"
            )
            self.cleanup()
            raise ChecksumMismatch(
                "The downloaded installer failed its integrity check and was discarded."
            )

        logger.info(f"Update installer verified: {target} ({expected_digest})")
        self.installer_path = target
        return target

    def _fetch_expected_digest(self) -> str:
        url = self.info.checksum_url or ""
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            text = response.text
        except Exception as exc:
            logger.info(f"Update: checksum sidecar unavailable ({exc})")
            raise ChecksumUnavailable(
                f"Could not fetch the checksum for v{self.info.version}: {exc}"
            ) from exc
        digest = parse_sha256_sidecar(text, expected_filename=self.info.installer_name)
        if digest is None:
            logger.error(f"Update: unreadable checksum sidecar at {url}: {text[:120]!r}")
            raise ChecksumUnavailable("The published checksum could not be read.")
        return digest

    def _prepare_target(self) -> Path:
        """Create this instance's temp directory and return the file path in it."""
        try:
            self._download_dir = Path(tempfile.mkdtemp(prefix=_TEMP_DIR_PREFIX, dir=self.temp_root))
        except OSError as exc:
            raise DownloadFailed(f"Could not create a temporary directory: {exc}") from exc
        # Kept under the published name so the sidecar's filename check means
        # something, and so a user who finds the file in %TEMP% can tell what it
        # is. Only the basename is taken from the payload: a name carrying path
        # separators would otherwise escape the temp directory.
        name = Path(self.info.installer_name or "MTGOTools_Setup.exe").name
        return self._download_dir / name

    def _stream_to_file(self, url: str, target: Path, progress: ProgressCallback | None) -> str:
        """Stream ``url`` into ``target``, hashing as it goes. Returns the hex digest.

        The hash is computed from the same chunks that are written, so the
        installer is read once rather than downloaded and then re-read to verify
        — which matters at 175 MB, and rules out the class of bug where the
        bytes verified are not the bytes stored.
        """
        digest = hashlib.sha256()
        done = 0
        try:
            with requests.get(url, stream=True, timeout=self.timeout) as response:
                response.raise_for_status()
                total = _content_length(response)
                if progress is not None:
                    # Fired before the first byte so the UI can show the total
                    # (and a 0% bar) instead of an empty dialog during the wait
                    # for the first chunk.
                    progress(0, total)
                with target.open("wb") as handle:
                    for chunk in _iter_chunks(response, self.chunk_size):
                        self._raise_if_cancelled()
                        handle.write(chunk)
                        digest.update(chunk)
                        done += len(chunk)
                        if progress is not None:
                            progress(done, total)
        except UpdateCancelled:
            logger.info(f"Update download cancelled after {done} bytes")
            self.cleanup()
            raise
        except OSError as exc:
            # Both the disk (no space, permissions) and requests' transport
            # errors, which subclass OSError, land here: from the user's side
            # they are the same "it didn't arrive, try later".
            logger.info(f"Update download failed after {done} bytes: {exc}")
            self.cleanup()
            raise DownloadFailed(f"The download failed: {exc}") from exc
        except Exception as exc:
            logger.exception("Update download failed")
            self.cleanup()
            raise DownloadFailed(f"The download failed: {exc}") from exc
        return digest.hexdigest()

    # ------------------------------------------------------------------ launch ------------------------------------------------------------------
    def launch(self) -> None:
        """Start the verified installer detached, then return immediately.

        The caller is expected to exit the app right after this: the installer
        cannot replace files the running app has open, and ``/RELAUNCH`` is what
        starts the new build once it is done.

        Only ever reachable for a file :meth:`download` verified — the path is
        stored by that method and by nothing else.
        """
        target = self.installer_path
        if target is None or not target.is_file():
            raise LaunchFailed("No verified installer to run")
        command = [str(target), *INSTALLER_SWITCHES]
        logger.info(f"Launching update installer: {command}")
        try:
            subprocess.Popen(  # nosec B603 - argv list, no shell, verified local path
                command,
                cwd=str(target.parent),
                env=_installer_env(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                **_detached_popen_kwargs(),
            )
        except OSError as exc:
            logger.exception("Failed to launch the update installer")
            raise LaunchFailed(f"Could not start the installer: {exc}") from exc

    # ------------------------------------------------------------------ cleanup ------------------------------------------------------------------
    def cleanup(self) -> None:
        """Remove the download directory, if it still exists.

        Best-effort and idempotent: it runs on failure paths, so it must not be
        able to replace the error the caller is about to see with an error of
        its own. Never call it after :meth:`launch` — Setup is executing from
        that directory.
        """
        directory = self._download_dir
        self._download_dir = None
        self.installer_path = None
        if directory is None:
            return
        shutil.rmtree(directory, ignore_errors=True)


def _content_length(response: requests.Response) -> int | None:
    """``Content-Length`` as a positive int, or ``None`` if it is unusable.

    A chunked or compressed response has no length, and a malformed header is
    worse than none: a progress bar sized from a bad total either sticks at 100%
    or never reaches it.
    """
    raw = response.headers.get("Content-Length")
    try:
        total = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return total if total > 0 else None


def _iter_chunks(response: requests.Response, chunk_size: int) -> Iterator[bytes]:
    """``iter_content`` minus the keep-alive blanks it can yield."""
    for chunk in response.iter_content(chunk_size=chunk_size):
        if chunk:
            yield chunk


def _installer_env() -> dict[str, str]:
    """This process's environment minus PyInstaller's bootloader variables.

    See :data:`_BOOTLOADER_ENV_VARS` for why they cannot be allowed to reach
    Setup: they describe an unpack directory that stops existing moments after
    Setup starts, and the app Setup relaunches would follow them into it.

    A copy is returned rather than ``os.environ`` being mutated — the app is
    still running and still spawning ``multiprocessing`` workers that need those
    variables, and it keeps this safe to call from the worker thread ``launch()``
    runs on. Everything else is passed through unchanged: Setup is a normal
    Windows program and wants the user's real environment.
    """
    return {key: value for key, value in os.environ.items() if key not in _BOOTLOADER_ENV_VARS}


def _detached_popen_kwargs() -> dict[str, Any]:
    """Popen arguments that let the child outlive this process.

    The installer must survive the app exiting seconds later — that exit is what
    frees the files it needs to replace — so it cannot be an ordinary child that
    dies with (or blocks) its parent.

    On Windows that is ``DETACHED_PROCESS`` (no inherited console, so the child
    is not killed by a console event aimed at the app) plus
    ``CREATE_NEW_PROCESS_GROUP`` (no inherited Ctrl+C/Ctrl+Break group). The
    values are read through ``getattr`` with the documented literals as
    fallbacks because these attributes only exist in ``subprocess`` on Windows;
    on any other platform the module still has to import for tests to run at all.

    ``CREATE_BREAKAWAY_FROM_JOB`` is *not* included, deliberately. It would help
    in the one case where the app is inside a job object configured to kill its
    children, but CreateProcess fails outright with ERROR_ACCESS_DENIED when the
    job does not permit breakaway — trading a rare failure for a common one.

    The POSIX branch (``start_new_session``) exists only so this code path is
    exercisable in tests; the installer itself is a Windows executable.
    """
    if sys.platform != "win32":
        return {"start_new_session": True}
    flags = int(getattr(subprocess, "DETACHED_PROCESS", 0x00000008)) | int(
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    )
    return {"creationflags": flags}


__all__ = [
    "ChecksumMismatch",
    "ChecksumUnavailable",
    "DownloadFailed",
    "INSTALLER_SWITCHES",
    "LaunchFailed",
    "ProgressCallback",
    "UpdateCancelled",
    "UpdateError",
    "UpdateInstaller",
    "UpdateNotDownloadable",
    "can_auto_update",
    "parse_sha256_sidecar",
]
