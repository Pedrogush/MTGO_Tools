"""In-app check for a newer published release (issue #142).

``.github/workflows/release.yml`` publishes exactly one GitHub Release per
version — tagged ``v<VERSION>``, carrying ``MTGOTools_Setup_v<VERSION>.exe`` —
and that is the entire contract consumed here: ask the API for the latest
release, read ``tag_name``, and compare it against the running ``VERSION``.

Public API:

- :func:`get_update_service` — module-level singleton accessor.
- :class:`UpdateService.check` — throttled network check; returns the newer
  release or ``None``.
- :func:`parse_version` — ``"v1.2.3"`` → ``(1, 2, 3)``, or ``None``.

Three properties matter more than the feature itself:

*Nothing here is load-bearing.* The app is completely usable without update
information, so every failure mode — offline, DNS failure, rate limit, a
payload whose shape changed — resolves to "no update info" and a debug/info log
line. :meth:`UpdateService.check` does not raise.

*The check is throttled across restarts.* The outcome is stamped to disk with a
timestamp and re-checked at most once per
:data:`UPDATE_CHECK_INTERVAL_SECONDS`, so launching the app repeatedly does not
mean repeatedly hitting an API whose unauthenticated budget is 60 requests per
hour per IP.

*A pulled release stops being advertised.* A 404 from ``/releases/latest`` is an
answer ("nothing is published"), not a failure, and is stamped as one — so a
release that was deleted or unpublished clears on the next check instead of
being recommended forever from a cache that never gets overwritten.

*Downloading and applying the update is out of scope.* The UI points at the
release page and the existing installer takes over from there.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import msgspec
import requests
from loguru import logger

from utils.atomic_io import atomic_write_json, locked_path
from utils.constants import APP_VERSION, UPDATE_CHECK_CACHE_FILE
from utils.constants.timing import (
    UPDATE_CHECK_INTERVAL_SECONDS,
    UPDATE_CHECK_REQUEST_TIMEOUT_SECONDS,
)

LATEST_RELEASE_API_URL = "https://api.github.com/repos/Pedrogush/MTGO_Tools/releases/latest"
# Fallback target for the "open the release page" affordance when the payload
# didn't carry an ``html_url``. ``/releases/latest`` always redirects to the
# newest published release, so it lands the user in the right place regardless.
RELEASES_PAGE_URL = "https://github.com/Pedrogush/MTGO_Tools/releases/latest"

# GitHub asks API clients to pin the API version explicitly, so a future change
# to the default can't reshape the payload underneath us.
_API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


class _NoRelease:
    """Type of :data:`NO_RELEASE`; see there."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return "NO_RELEASE"


#: GitHub answered authoritatively that this repository has no published release
#: (every release is a draft or a pre-release, or there are none at all). This is
#: a completed check with a known answer, which is why it is not ``None``: a
#: transport failure means "ask again", while this means "forget what you knew".
NO_RELEASE = _NoRelease()


@dataclass(frozen=True)
class UpdateInfo:
    """A published release newer than the running build."""

    version: str  # bare semver, no leading "v" (e.g. "1.0.3")
    release_url: str


class _CheckStamp(msgspec.Struct):
    """Outcome of the last *completed* check, persisted across restarts.

    ``latest_version`` is ``None`` when the request succeeded but produced no
    usable version (an unrecognized tag). That is still a completed check, so it
    carries a timestamp and suppresses re-checking — otherwise a payload the app
    can't read would mean an API call on every single launch, forever.
    """

    checked_at: float
    latest_version: str | None = None
    release_url: str | None = None


def parse_version(raw: str | None) -> tuple[int, int, int] | None:
    """Parse ``"v1.2.3"`` / ``"1.2.3"`` into a comparable ``(major, minor, patch)``.

    Tuple comparison is the point: string comparison ranks ``"1.0.9"`` above
    ``"1.0.10"``, which would hide exactly the update a user needs.

    Returns ``None`` for anything that isn't a plain numeric release version.
    Malformed tags, pre-release suffixes and an unknown running version all
    funnel through that one path into "no update info" rather than into a
    comparison that can't be trusted. The project only ever publishes plain
    ``vX.Y.Z`` tags (docs/VERSIONING.md), so rejecting the rest costs nothing.
    """
    if not raw:
        return None
    text = raw.strip()
    if text[:1] in ("v", "V"):
        text = text[1:]
    parts = text.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    major, minor, patch = (int(part) for part in parts)
    return major, minor, patch


class UpdateService:
    """Throttled "has a newer release shipped?" check against the GitHub API.

    :meth:`check` performs network and disk I/O, so it belongs on a background
    thread. It never raises: callers get ``None`` (or the previously cached
    answer) for every failure.
    """

    def __init__(
        self,
        current_version: str = APP_VERSION,
        cache_path: Path = UPDATE_CHECK_CACHE_FILE,
        api_url: str = LATEST_RELEASE_API_URL,
        check_interval: float = UPDATE_CHECK_INTERVAL_SECONDS,
        request_timeout: float = UPDATE_CHECK_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.current_version = current_version
        self.cache_path = Path(cache_path)
        self.api_url = api_url
        self.check_interval = check_interval
        self.request_timeout = request_timeout

    def check(self) -> UpdateInfo | None:
        """Return the newest published release when it is newer than this build.

        Answers from the on-disk stamp while it is still fresh, so the API is
        contacted at most once per :attr:`check_interval` no matter how often
        the app is launched. A stamp dated in the *future* counts as stale: a
        clock that ran fast and was then corrected would otherwise pin the
        cached answer permanently.
        """
        stamp = self._read_stamp()
        if stamp is not None and 0 <= (time.time() - stamp.checked_at) < self.check_interval:
            logger.debug("Update check: cached result is still fresh")
            return self._to_update_info(stamp)

        payload = self._fetch_latest_release()
        if payload is None:
            # Offline, DNS failure, rate limit, 5xx… Deliberately *not* stamped:
            # a failed attempt is not a completed check, so the next launch
            # retries rather than sitting on missing information for a full
            # interval. The retry rate is bounded by launches, not by a timer.
            return self._to_update_info(stamp)

        if payload is NO_RELEASE:
            # GitHub answered, and the answer is "nothing is published". That is
            # a *completed* check, not a failed one, so it gets stamped and the
            # previous answer is dropped. Without this the two are indistinguishable
            # and a release that was deleted or pulled goes on being advertised
            # forever — every launch re-asks, 404s, and falls back to the stale
            # answer it should have discarded.
            stamp = _CheckStamp(checked_at=time.time())
            self._write_stamp(stamp)
            return self._to_update_info(stamp)

        stamp = self._stamp_from_payload(payload)
        self._write_stamp(stamp)
        return self._to_update_info(stamp)

    # ------------------------------------------------------------------ network ------------------------------------------------------------------
    def _fetch_latest_release(self) -> dict[str, Any] | _NoRelease | None:
        """The latest release payload, :data:`NO_RELEASE`, or ``None``.

        Three outcomes, because "I could not reach GitHub" and "GitHub says there
        is nothing published" call for opposite handling and only one of them is
        a failure. A 404 from this endpoint is an *answer*: the repository has no
        published non-prerelease, non-draft release. Collapsing it into ``None``
        alongside the transport failures is what let a deleted release keep being
        advertised.
        """
        try:
            response = requests.get(
                self.api_url, headers=_API_HEADERS, timeout=self.request_timeout
            )
        except Exception as exc:
            # Having no connection is the ordinary case here, not a fault worth
            # an ERROR + traceback for a check the user never asked for.
            logger.debug(f"Update check request failed: {exc}")
            return None

        if response.status_code == 404:
            logger.info("Update check: no published release for this repository")
            return NO_RELEASE

        try:
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.debug(f"Update check request failed: {exc}")
            return None
        if not isinstance(payload, dict):
            logger.info(f"Update check: unexpected payload type {type(payload).__name__}")
            return None
        return payload

    def _stamp_from_payload(self, payload: dict[str, Any]) -> _CheckStamp:
        now = time.time()
        tag = payload.get("tag_name")
        parsed = parse_version(tag if isinstance(tag, str) else None)
        if parsed is None:
            logger.info(f"Update check: unrecognized release tag {tag!r}")
            return _CheckStamp(checked_at=now)
        url = payload.get("html_url")
        return _CheckStamp(
            checked_at=now,
            latest_version=".".join(str(number) for number in parsed),
            release_url=url if isinstance(url, str) and url else RELEASES_PAGE_URL,
        )

    # ------------------------------------------------------------------ comparison ------------------------------------------------------------------
    def _to_update_info(self, stamp: _CheckStamp | None) -> UpdateInfo | None:
        if stamp is None or stamp.latest_version is None:
            return None
        current = parse_version(self.current_version)
        if current is None:
            # No trustworthy running version to compare against (VERSION missing
            # from the bundle, say). Staying quiet beats nagging on the strength
            # of a comparison we can't actually make.
            logger.info(f"Update check: unrecognized running version {self.current_version!r}")
            return None
        latest = parse_version(stamp.latest_version)
        if latest is None or latest <= current:
            return None
        return UpdateInfo(
            version=stamp.latest_version,
            release_url=stamp.release_url or RELEASES_PAGE_URL,
        )

    # ------------------------------------------------------------------ stamp I/O ------------------------------------------------------------------
    def _read_stamp(self) -> _CheckStamp | None:
        if not self.cache_path.is_file():
            return None
        try:
            with locked_path(self.cache_path):
                raw = self.cache_path.read_bytes()
            return msgspec.json.decode(raw, type=_CheckStamp)
        except (OSError, msgspec.DecodeError) as exc:
            logger.debug(f"Update check: unreadable cache at {self.cache_path}: {exc}")
            return None

    def _write_stamp(self, stamp: _CheckStamp) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(self.cache_path, msgspec.structs.asdict(stamp), indent=2)
        except OSError as exc:
            logger.debug(f"Update check: unable to persist cache: {exc}")


_default_service: UpdateService | None = None


def get_update_service() -> UpdateService:
    """Return the module-level :class:`UpdateService` singleton."""
    global _default_service
    if _default_service is None:
        _default_service = UpdateService()
    return _default_service


def reset_update_service() -> None:
    """Reset the singleton — primarily for test isolation."""
    global _default_service
    _default_service = None


__all__ = [
    "LATEST_RELEASE_API_URL",
    "NO_RELEASE",
    "RELEASES_PAGE_URL",
    "UpdateInfo",
    "UpdateService",
    "get_update_service",
    "parse_version",
    "reset_update_service",
]
