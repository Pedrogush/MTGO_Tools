"""HTTP JSON fetch helpers for the remote snapshot client."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger


class RemoteSnapshotError(Exception):
    """Raised when a remote snapshot operation fails unrecoverably."""


class HttpMixin:
    """Fetch JSON artifacts over HTTP with a stdlib fallback."""

    def _http_get_json(self, url: str) -> dict[str, Any] | None:
        """Fetch *url* and decode the response body as JSON.

        Returns ``None`` (and logs the error) instead of raising on any
        network or decode failure, so callers can transparently fall back.
        """
        try:
            import curl_cffi.requests as requests  # type: ignore[import-untyped]

            response = requests.get(url, impersonate="chrome", timeout=self.request_timeout)
            response.raise_for_status()
            return response.json()
        except ImportError:
            pass
        except Exception as exc:
            logger.debug(f"Remote snapshot fetch failed for {url!r}: {exc}")
            return None

        # Fallback to stdlib urllib when curl_cffi is unavailable (e.g. Linux CI)
        try:
            from urllib.parse import urlparse
            from urllib.request import urlopen

            parsed = urlparse(url)
            if parsed.scheme not in ("https", "http"):
                raise ValueError(f"Disallowed URL scheme: {parsed.scheme!r}")
            with urlopen(
                url, timeout=self.request_timeout
            ) as resp:  # nosec B310 - scheme validated above
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.debug(f"Remote snapshot fetch (urllib) failed for {url!r}: {exc}")
            return None
