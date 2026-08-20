"""Rate-limited ``requests`` session for Scryfall traffic.

Scryfall asks clients to keep API traffic to roughly 10 requests/second (a
50-100 ms gap between calls) and to back off when it answers ``429 Too Many
Requests``. The image pipeline runs up to 10 concurrent download workers
(:data:`CardImageDownloadQueue._MAX_CONCURRENT_DOWNLOADS`), and on a *cold*
start — before the local bulk-data index has finished downloading — every card
falls back to a per-card ``/cards/named`` API lookup. Ten unthrottled workers
hammering the API that way trips Scryfall's rate limiter within seconds: the
symptom seen in the field was a 429 storm during the first ~50 s of a fresh
install, which dropped a nondeterministic subset of a deck's images (issue:
prefetch-image-queue cold-start inconsistency).

:class:`ScryfallSession` centralizes the fix so every code path that talks to
Scryfall behaves the same:

* a single process-wide :class:`_RateLimiter` paces requests to the Scryfall
  **API host** at :data:`SCRYFALL_API_MIN_INTERVAL_SECONDS`, shared across every
  session instance and every worker thread, and
* ``429`` responses are retried honoring the ``Retry-After`` header.

Image **bytes** are served from Scryfall's CDN (``cards.scryfall.io``), which is
not the rate-limited host, so CDN requests are left unthrottled — throttling
them would needlessly serialize the bulk image warm-up.
"""

from __future__ import annotations

import threading
import time
from urllib.parse import urlsplit

import requests
from loguru import logger

from utils.constants.timing import (
    SCRYFALL_API_MAX_429_RETRIES,
    SCRYFALL_API_MIN_INTERVAL_SECONDS,
    SCRYFALL_API_RETRY_AFTER_FALLBACK_SECONDS,
    SCRYFALL_API_RETRY_AFTER_MAX_SECONDS,
)

# Hosts that serve the rate-limited Scryfall *API* (as opposed to the image
# CDN). Any request whose host ends with one of these is paced by the shared
# limiter; everything else (CDN image bytes, bulk-data file) passes through.
_SCRYFALL_API_HOSTS = ("api.scryfall.com",)

_USER_AGENT = "MTGOMetagameCrawler/1.0"


class _RateLimiter:
    """Process-wide minimum-interval gate shared by every Scryfall session.

    Reserves the next time slot under a short lock, then sleeps *outside* the
    lock so concurrent callers queue for distinct slots instead of serializing
    on the sleep itself.
    """

    def __init__(self, min_interval: float) -> None:
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_allowed)
            self._next_allowed = slot + self._min_interval
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)


# One limiter for the whole process: all BulkImageDownloader instances and all
# download-queue workers must share a single API budget, or N sessions each get
# their own 10 req/s allowance and the aggregate trips the limiter anyway.
_API_LIMITER = _RateLimiter(SCRYFALL_API_MIN_INTERVAL_SECONDS)


def _is_api_host(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(
        host == api_host or host.endswith("." + api_host) for api_host in _SCRYFALL_API_HOSTS
    )


def _retry_after_seconds(response: requests.Response) -> float:
    """Seconds to wait per the ``Retry-After`` header, clamped to a sane bound."""
    raw = response.headers.get("Retry-After")
    delay = SCRYFALL_API_RETRY_AFTER_FALLBACK_SECONDS
    if raw:
        try:
            delay = float(raw)
        except ValueError:
            # HTTP-date form is possible but Scryfall sends seconds; fall back.
            delay = SCRYFALL_API_RETRY_AFTER_FALLBACK_SECONDS
    return max(0.0, min(delay, SCRYFALL_API_RETRY_AFTER_MAX_SECONDS))


class ScryfallSession(requests.Session):
    """``requests.Session`` that paces API calls and backs off on 429."""

    def __init__(self) -> None:
        super().__init__()
        self.headers.update({"User-Agent": _USER_AGENT})

    def request(self, method, url, *args, **kwargs):  # type: ignore[override]
        throttle = _is_api_host(str(url))
        attempts = 0
        while True:
            if throttle:
                _API_LIMITER.acquire()
            response = super().request(method, url, *args, **kwargs)
            if throttle and response.status_code == 429 and attempts < SCRYFALL_API_MAX_429_RETRIES:
                wait = _retry_after_seconds(response)
                attempts += 1
                logger.warning(
                    "Scryfall rate limited (429) for {}; backing off {:.2f}s (retry {}/{}).",
                    url,
                    wait,
                    attempts,
                    SCRYFALL_API_MAX_429_RETRIES,
                )
                time.sleep(wait)
                continue
            return response


__all__ = ["ScryfallSession"]
