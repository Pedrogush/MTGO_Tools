"""HTTP fetch for the MTGJSON AtomicCards dataset.

Owns the single external integration (HEAD for metadata, GET for the zip
payload) so the rest of the service can stay offline-testable.

``requests`` is re-exported at module scope so tests can monkeypatch
``repositories.card_repository.remote.requests.head`` / ``.get``.
"""

from __future__ import annotations

from typing import Any

from curl_cffi import requests
from loguru import logger

from utils.constants import (
    ATOMIC_DATA_DOWNLOAD_TIMEOUT_SECONDS,
    ATOMIC_DATA_HEAD_TIMEOUT_SECONDS,
    ATOMIC_DATA_URL,
)


def fetch_dataset_headers() -> dict[str, Any] | None:
    """HEAD the MTGJSON endpoint and return the cache-relevant headers."""
    try:
        resp = requests.head(
            ATOMIC_DATA_URL,
            impersonate="chrome",
            timeout=ATOMIC_DATA_HEAD_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning(f"Failed to fetch MTGJSON dataset headers: {exc}")
        return None
    meta: dict[str, Any] = {}
    headers = {k.lower(): v for k, v in resp.headers.items()}  # type: ignore[arg-type]
    if "etag" in headers:
        meta["etag"] = headers["etag"].strip('"')
    if "last-modified" in headers:
        meta["last_modified"] = headers["last-modified"]
    if "content-length" in headers:
        meta["content_length"] = headers["content-length"]
    return meta or None


def download_atomic_cards_zip() -> tuple[bytes, dict[str, str]]:
    """GET the dataset and return ``(content_bytes, normalized_headers)``."""
    resp = requests.get(
        ATOMIC_DATA_URL,
        impersonate="chrome",
        timeout=ATOMIC_DATA_DOWNLOAD_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    headers = {k.lower(): v for k, v in resp.headers.items()}  # type: ignore[arg-type]
    return resp.content, headers


__all__ = ["download_atomic_cards_zip", "fetch_dataset_headers", "requests"]
