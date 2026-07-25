"""Tests for the rate-limited Scryfall session (cold-start 429 protection)."""

from __future__ import annotations

import time

import services.image_service.scryfall_session as scryfall_session
from services.image_service.scryfall_session import (
    ScryfallSession,
    _is_api_host,
    _RateLimiter,
    _retry_after_seconds,
)
from utils.constants.timing import SCRYFALL_API_RETRY_AFTER_MAX_SECONDS


class _FakeResponse:
    def __init__(self, status_code: int, headers: dict | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}


def test_is_api_host_matches_api_but_not_cdn():
    assert _is_api_host("https://api.scryfall.com/cards/named?exact=Bolt")
    assert _is_api_host("https://api.scryfall.com/cards/collection")
    # Image bytes come from the CDN, which is NOT rate limited — must not throttle.
    assert not _is_api_host("https://cards.scryfall.io/normal/front/a/b/abcd.jpg")
    assert not _is_api_host("https://example.com/whatever")


def test_retry_after_parses_and_clamps():
    assert _retry_after_seconds(_FakeResponse(429, {"Retry-After": "2"})) == 2.0
    # Missing header falls back to the configured default (a positive wait).
    assert _retry_after_seconds(_FakeResponse(429, {})) > 0
    # A hostile/huge Retry-After is clamped so a worker can't be stalled forever.
    huge = _retry_after_seconds(_FakeResponse(429, {"Retry-After": "99999"}))
    assert huge == SCRYFALL_API_RETRY_AFTER_MAX_SECONDS
    # Non-numeric header does not raise.
    assert _retry_after_seconds(_FakeResponse(429, {"Retry-After": "bogus"})) > 0


def test_rate_limiter_spaces_calls():
    limiter = _RateLimiter(min_interval=0.05)
    start = time.monotonic()
    for _ in range(4):
        limiter.acquire()
    elapsed = time.monotonic() - start
    # 4 slots at 0.05s each: the first is free, the next three are paced.
    assert elapsed >= 0.05 * 3 * 0.9


def test_session_retries_429_then_succeeds(monkeypatch):
    """A 429 on the API host is retried honoring Retry-After, then returns 200."""
    calls: list[str] = []
    sleeps: list[float] = []
    responses = iter([_FakeResponse(429, {"Retry-After": "0"}), _FakeResponse(200)])

    def fake_super_request(self, method, url, *args, **kwargs):
        calls.append(url)
        return next(responses)

    monkeypatch.setattr(scryfall_session.requests.Session, "request", fake_super_request)
    monkeypatch.setattr(scryfall_session.time, "sleep", lambda s: sleeps.append(s))
    # Neutralize the shared limiter's real pacing sleep for the test.
    monkeypatch.setattr(scryfall_session._API_LIMITER, "acquire", lambda: None)

    session = ScryfallSession()
    resp = session.request("GET", "https://api.scryfall.com/cards/named?exact=Bolt")

    assert resp.status_code == 200
    assert len(calls) == 2  # one 429, one success
    assert sleeps  # honored Retry-After at least once


def test_session_gives_up_after_max_retries(monkeypatch):
    """Persistent 429s stop after the retry budget instead of looping forever."""

    def always_429(self, method, url, *args, **kwargs):
        return _FakeResponse(429, {"Retry-After": "0"})

    monkeypatch.setattr(scryfall_session.requests.Session, "request", always_429)
    monkeypatch.setattr(scryfall_session.time, "sleep", lambda s: None)
    monkeypatch.setattr(scryfall_session._API_LIMITER, "acquire", lambda: None)

    session = ScryfallSession()
    resp = session.request("GET", "https://api.scryfall.com/cards/named?exact=Bolt")

    assert resp.status_code == 429  # surfaced to the caller for normal error handling


def test_session_does_not_throttle_or_retry_cdn(monkeypatch):
    """CDN image requests bypass the limiter and the 429 retry loop."""
    acquired: list[bool] = []
    monkeypatch.setattr(scryfall_session._API_LIMITER, "acquire", lambda: acquired.append(True))
    monkeypatch.setattr(
        scryfall_session.requests.Session,
        "request",
        lambda self, method, url, *a, **k: _FakeResponse(429, {"Retry-After": "5"}),
    )
    session = ScryfallSession()
    resp = session.request("GET", "https://cards.scryfall.io/normal/front/a/b/x.jpg")

    # Not throttled and not retried: a CDN 429 is returned as-is, immediately.
    assert resp.status_code == 429
    assert acquired == []
