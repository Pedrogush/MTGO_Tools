"""A fail-fast tripwire at the outbound-HTTP transport boundary.

Why this exists
---------------
``tests/README.md`` §2 names outbound network / scraping as the one dependency
category that must be faked. Enforcing that by inspecting side effects after the
fact -- "did a ``.jpg`` appear in the image cache?" -- is both late and
unreliable: it only catches the leaks that happen to leave a file behind, and it
depends on where the cache constants happened to point.

This module installs the check at the boundary instead. Every entry point the
app can reach the network through is replaced with a recorder that appends the
attempted URL to a list and then raises :class:`NetworkAccessError`.

The recording matters as much as the raising. Production code deliberately wraps
its fetches in broad ``except Exception`` handlers and falls back to cached data,
so a tripwire that only raised would be swallowed and the test would still pass.
Assert on the returned list, not on the absence of an exception.

Covered entry points
--------------------
* ``requests.sessions.Session.request`` -- the funnel for ``requests.get`` and
  friends, and for :class:`~services.image_service.scryfall_session.ScryfallSession`,
  which reaches the wire through ``super().request``.
* ``curl_cffi.requests`` module-level verbs and ``Session``/``AsyncSession`` --
  the scrapers use ``from curl_cffi import requests`` for browser impersonation,
  a separate stack that never touches ``requests``.
* ``urllib.request.urlopen`` / ``urlretrieve`` -- the ``urllib`` fallbacks that
  several fetchers drop to when ``curl_cffi`` fails.
* ``http.client.HTTP(S)Connection.connect`` -- a backstop below ``requests`` and
  ``urllib`` so a path that bypasses the wrappers above is still caught.
"""

from __future__ import annotations

from typing import Any

import pytest

__all__ = ["NetworkAccessError", "NetworkWatch", "install_network_tripwire"]


class NetworkAccessError(RuntimeError):
    """Raised when test code reaches for a real network connection."""


class NetworkWatch:
    """A window onto a session-wide attempt log, opened at construction.

    The tripwire is installed once per session (daemon threads outlive the test
    that starts them, so a per-test patch leaves gaps), but each test needs to
    assert on *its own* calls. This exposes only the entries recorded since it
    was created.
    """

    def __init__(self, attempts: list[str]) -> None:
        self._attempts = attempts
        self._start = len(attempts)

    @property
    def attempts(self) -> list[str]:
        """Distinct outbound calls attempted since this watch opened."""
        return list(dict.fromkeys(self._attempts[self._start :]))

    def __bool__(self) -> bool:
        return bool(self.attempts)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"NetworkWatch({self.attempts!r})"


_CURL_VERBS = (
    "request",
    "get",
    "head",
    "post",
    "put",
    "patch",
    "delete",
    "options",
)


def _describe(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Best-effort target description for the attempted call."""
    url = kwargs.get("url")
    if url is None:
        positional = [a for a in args if isinstance(a, str)]
        if positional:
            url = positional[-1]
    if url is None and args:
        # ``HTTPConnection.connect(self)`` carries the target on the instance.
        host = getattr(args[0], "host", None)
        if host is not None:
            url = f"{host}:{getattr(args[0], 'port', '?')}"
    return str(url) if url is not None else "<unknown>"


def install_network_tripwire(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Make every outbound HTTP entry point record and raise.

    Returns the list attempts are recorded into. It stays empty for a properly
    isolated test; every entry is a real outbound call the test would have made.
    """
    attempts: list[str] = []

    def _trip(label: str):
        def _blocked(*args: Any, **kwargs: Any):
            target = _describe(args, kwargs)
            attempts.append(f"{label} {target}")
            raise NetworkAccessError(
                f"Outbound network call blocked in tests: {label} {target}. "
                "Fake it at a seam you own (tests/README.md §2)."
            )

        return _blocked

    import http.client
    import urllib.request

    import requests.sessions

    monkeypatch.setattr(
        requests.sessions.Session, "request", _trip("requests.Session.request"), raising=False
    )

    try:
        import curl_cffi.requests as curl_requests
    except ImportError:  # pragma: no cover - curl_cffi is a hard dependency
        curl_requests = None
    if curl_requests is not None:
        for verb in _CURL_VERBS:
            if hasattr(curl_requests, verb):
                monkeypatch.setattr(
                    curl_requests, verb, _trip(f"curl_cffi.requests.{verb}"), raising=False
                )
        for session_name in ("Session", "AsyncSession"):
            session_cls = getattr(curl_requests, session_name, None)
            if session_cls is not None:
                monkeypatch.setattr(
                    session_cls,
                    "request",
                    _trip(f"curl_cffi.requests.{session_name}.request"),
                    raising=False,
                )

    monkeypatch.setattr(urllib.request, "urlopen", _trip("urllib.request.urlopen"), raising=False)
    monkeypatch.setattr(
        urllib.request, "urlretrieve", _trip("urllib.request.urlretrieve"), raising=False
    )

    for conn_name in ("HTTPConnection", "HTTPSConnection"):
        conn_cls = getattr(http.client, conn_name, None)
        if conn_cls is not None:
            monkeypatch.setattr(
                conn_cls, "connect", _trip(f"http.client.{conn_name}.connect"), raising=False
            )

    return attempts
