"""HTTP download helpers for the bundle snapshot client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from services.bundle_snapshot_client.protocol import BundleSnapshotClientProto

    _Base = BundleSnapshotClientProto
else:
    _Base = object


class BundleSnapshotError(Exception):
    """Raised when the bundle cannot be downloaded or applied."""


@dataclass(frozen=True)
class BundleResponse:
    """Outcome of a (conditional) bundle download.

    ``not_modified`` is ``True`` when the server answered ``304 Not Modified``
    to a conditional request, in which case ``content`` is ``None`` and the
    expensive gunzip + tar-parse + SQLite merge can be skipped entirely.
    """

    content: bytes | None
    not_modified: bool = False
    etag: str | None = None
    last_modified: str | None = None


class DownloadMixin(_Base):
    """Download the compressed bundle archive over HTTP."""

    def _download_bundle(
        self, etag: str | None = None, last_modified: str | None = None
    ) -> BundleResponse:
        url = f"{self.base_url}/{self.bundle_path}"
        response = self._http_get_bytes(url, etag=etag, last_modified=last_modified)
        if response is None or (response.content is None and not response.not_modified):
            raise BundleSnapshotError(f"Failed to download bundle from {url!r}")
        return response

    def _http_get_bytes(
        self, url: str, etag: str | None = None, last_modified: str | None = None
    ) -> BundleResponse | None:
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        try:
            import curl_cffi.requests as requests  # type: ignore[import-untyped]

            response = requests.get(
                url,
                impersonate="chrome",
                timeout=self.request_timeout,
                headers=headers or None,
            )
            if response.status_code == 304:
                logger.debug(f"Bundle unchanged (304) for {url!r}")
                return BundleResponse(content=None, not_modified=True)
            response.raise_for_status()
            return BundleResponse(
                content=response.content,
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
            )
        except ImportError:
            pass
        except Exception as exc:
            logger.debug(f"Bundle download (curl_cffi) failed for {url!r}: {exc}")
            return None

        try:
            from urllib.error import HTTPError
            from urllib.parse import urlparse
            from urllib.request import Request, urlopen

            parsed = urlparse(url)
            if parsed.scheme not in ("https", "http"):
                raise ValueError(f"Disallowed URL scheme: {parsed.scheme!r}")
            request = Request(url, headers=headers)  # nosec B310
            try:
                with urlopen(request, timeout=self.request_timeout) as resp:  # nosec B310
                    return BundleResponse(
                        content=resp.read(),
                        etag=resp.headers.get("ETag"),
                        last_modified=resp.headers.get("Last-Modified"),
                    )
            except HTTPError as http_exc:
                if http_exc.code == 304:
                    logger.debug(f"Bundle unchanged (304) for {url!r}")
                    return BundleResponse(content=None, not_modified=True)
                raise
        except Exception as exc:
            logger.debug(f"Bundle download (urllib) failed for {url!r}: {exc}")
            return None
