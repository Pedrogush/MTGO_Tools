"""HTTP download helpers for the bundle snapshot client."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from services.bundle_snapshot_client.protocol import BundleSnapshotClientProto

    _Base = BundleSnapshotClientProto
else:
    _Base = object


class BundleSnapshotError(Exception):
    """Raised when the bundle cannot be downloaded or applied."""


class DownloadMixin(_Base):
    """Download the compressed bundle archive over HTTP."""

    def _download_bundle(self) -> bytes:
        url = f"{self.base_url}/{self.bundle_path}"
        data = self._http_get_bytes(url)
        if data is None:
            raise BundleSnapshotError(f"Failed to download bundle from {url!r}")
        return data

    def _http_get_bytes(self, url: str) -> bytes | None:
        try:
            import curl_cffi.requests as requests  # type: ignore[import-untyped]

            response = requests.get(url, impersonate="chrome", timeout=self.request_timeout)
            response.raise_for_status()
            return response.content
        except ImportError:
            pass
        except Exception as exc:
            logger.debug(f"Bundle download (curl_cffi) failed for {url!r}: {exc}")
            return None

        try:
            from urllib.parse import urlparse
            from urllib.request import urlopen

            parsed = urlparse(url)
            if parsed.scheme not in ("https", "http"):
                raise ValueError(f"Disallowed URL scheme: {parsed.scheme!r}")
            with urlopen(url, timeout=self.request_timeout) as resp:  # nosec B310
                return resp.read()
        except Exception as exc:
            logger.debug(f"Bundle download (urllib) failed for {url!r}: {exc}")
            return None
