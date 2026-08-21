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

*This module decides* whether *there is an update, never* whether *to apply
one.* It reads the release payload and hands back what an updater would need —
the installer asset's URL and its ``.sha256`` sidecar — but downloading,
verifying and running that installer lives in :mod:`services.update_installer`,
and the fallback of simply opening the release page in a browser stays valid at
all times.
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

# How the two assets `.github/workflows/release.yml` attaches are recognized in
# the payload's ``assets`` array. Matched by prefix + suffix rather than by
# rebuilding ``MTGOTools_Setup_v{version}.exe`` from the tag, so a release whose
# asset and tag disagree about the version string (a re-upload, a hand-made
# release) is still usable. The sidecar, by contrast, is required to be exactly
# ``<installer name>.sha256``: a checksum file that names *some other* build is
# worse than no checksum at all, because it would be trusted.
INSTALLER_ASSET_PREFIX = "MTGOTools_Setup_"
INSTALLER_ASSET_SUFFIX = ".exe"
CHECKSUM_ASSET_SUFFIX = ".sha256"


@dataclass(frozen=True)
class UpdateInfo:
    """A published release newer than the running build.

    The three asset fields are all present or all absent, and absent is an
    ordinary outcome rather than a failure: a release may carry no installer, or
    an installer with no ``.sha256`` sidecar to verify it against. When that
    happens the user is *still* told a newer version exists — the notice is
    about the release, not about the app's ability to apply it — and the UI
    falls back to opening :attr:`release_url` in a browser. Treating a missing
    asset as "no update" would hide a real update behind a packaging detail.

    They move together because a downloader needs both halves: an installer with
    no checksum is a 174 MB executable the app would have to run unverified,
    which it will not do. So "can this be applied in-app?" is exactly
    "is :attr:`installer_url` set?".
    """

    version: str  # bare semver, no leading "v" (e.g. "1.0.3")
    release_url: str
    installer_url: str | None = None
    checksum_url: str | None = None
    installer_name: str | None = None  # e.g. "MTGOTools_Setup_v1.0.3.exe"


class _CheckStamp(msgspec.Struct):
    """Outcome of the last *completed* check, persisted across restarts.

    ``latest_version`` is ``None`` when the request succeeded but produced no
    usable version (an unrecognized tag). That is still a completed check, so it
    carries a timestamp and suppresses re-checking — otherwise a payload the app
    can't read would mean an API call on every single launch, forever.

    Every field after ``checked_at`` is optional *and* defaulted, which is what
    keeps a stamp written by an older build readable: msgspec fills fields the
    JSON omits from their defaults and ignores members it does not know, so
    neither adding a field here nor removing one later turns a cached stamp into
    a decode error (which would silently cost one API request per launch until
    the stamp was rewritten). Anything added here must keep a default for that
    reason.
    """

    checked_at: float
    latest_version: str | None = None
    release_url: str | None = None
    installer_url: str | None = None
    checksum_url: str | None = None
    installer_name: str | None = None


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


def _asset_download_url(asset: dict[str, Any]) -> str | None:
    """The URL that serves an asset's *bytes*, or ``None``.

    Deliberately only ``browser_download_url``. Every asset also carries a
    ``url`` pointing at the API endpoint for it, but that endpoint answers with
    the asset's JSON metadata unless the request sets
    ``Accept: application/octet-stream`` — so falling back to it would hand the
    downloader a URL that yields a few hundred bytes of JSON, which would then
    fail SHA256 verification and be reported to the user as a corrupt download.
    A missing ``browser_download_url`` means "not downloadable" instead.
    """
    url = asset.get("browser_download_url")
    return url if isinstance(url, str) and url else None


def _find_installer_assets(
    payload: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    """Locate the installer and its checksum sidecar in a release payload.

    Returns ``(installer_url, checksum_url, installer_name)``, all three
    ``None`` unless *both* assets were found — see :class:`UpdateInfo` for why
    half a pair is worth nothing. Every degenerate payload shape (no ``assets``
    key, a non-list, entries that aren't dicts or have no name) resolves to the
    same "no assets" answer, because none of them is a reason to withhold the
    update notice itself.
    """
    assets = payload.get("assets")
    if not isinstance(assets, list):
        return None, None, None
    by_name: dict[str, dict[str, Any]] = {}
    for asset in assets:
        if isinstance(asset, dict):
            name = asset.get("name")
            if isinstance(name, str) and name:
                by_name[name] = asset
    # Sorted so a release that somehow carries two matching installers resolves
    # the same way on every launch, rather than depending on upload order.
    installer_name = next(
        (
            name
            for name in sorted(by_name)
            if name.startswith(INSTALLER_ASSET_PREFIX) and name.endswith(INSTALLER_ASSET_SUFFIX)
        ),
        None,
    )
    if installer_name is None:
        logger.debug("Update check: release carries no installer asset")
        return None, None, None
    checksum_asset = by_name.get(f"{installer_name}{CHECKSUM_ASSET_SUFFIX}")
    installer_url = _asset_download_url(by_name[installer_name])
    checksum_url = _asset_download_url(checksum_asset) if checksum_asset is not None else None
    if installer_url is None or checksum_url is None:
        logger.info(f"Update check: {installer_name} has no usable checksum sidecar")
        return None, None, None
    return installer_url, checksum_url, installer_name


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

        stamp = self._stamp_from_payload(payload)
        self._write_stamp(stamp)
        return self._to_update_info(stamp)

    # ------------------------------------------------------------------ network ------------------------------------------------------------------
    def _fetch_latest_release(self) -> dict[str, Any] | None:
        """GET the latest release payload, or ``None`` on any failure at all."""
        try:
            response = requests.get(
                self.api_url, headers=_API_HEADERS, timeout=self.request_timeout
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            # Having no connection is the ordinary case here, not a fault worth
            # an ERROR + traceback for a check the user never asked for.
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
        installer_url, checksum_url, installer_name = _find_installer_assets(payload)
        return _CheckStamp(
            checked_at=now,
            latest_version=".".join(str(number) for number in parsed),
            release_url=url if isinstance(url, str) and url else RELEASES_PAGE_URL,
            installer_url=installer_url,
            checksum_url=checksum_url,
            installer_name=installer_name,
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
            installer_url=stamp.installer_url,
            checksum_url=stamp.checksum_url,
            installer_name=stamp.installer_name,
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
    "CHECKSUM_ASSET_SUFFIX",
    "INSTALLER_ASSET_PREFIX",
    "INSTALLER_ASSET_SUFFIX",
    "LATEST_RELEASE_API_URL",
    "RELEASES_PAGE_URL",
    "UpdateInfo",
    "UpdateService",
    "get_update_service",
    "parse_version",
    "reset_update_service",
]
