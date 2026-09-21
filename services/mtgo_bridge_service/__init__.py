"""MTGO bridge service: Python-facing facade over the CLI bridge.

Every call here is routed through one long-lived ``MTGOBridge.exe serve``
process (see :mod:`.session`), which pays MTGOSDK's ~3.1s attach once instead of
once per command and keeps a single request queue so concurrent callers cannot
degrade each other's latency. If a session cannot be established — most often an
older bridge build that has no ``serve`` mode — each call falls back to the
one-shot subprocess transport in :mod:`.client`, so behaviour is unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import partial
from typing import Any

from loguru import logger

from utils.constants import BRIDGE_SESSION_WATCH_INTERVAL_MS

from . import client as mtgo_bridge_client
from . import session as mtgo_bridge_session
from .session import (
    BridgeSessionError,
    BridgeSessionUnavailable,
    SessionRequestFuture,
    SessionWatcher,
    shutdown_session,
)

__all__ = [
    "BridgeSessionError",
    "BridgeSessionUnavailable",
    "SessionRequestFuture",
    "SessionWatcher",
    "accept_pending_trades",
    "ensure_runtime_ready",
    "fetch_collection_async",
    "fetch_history_async",
    "get_collection_snapshot",
    "get_full_collection",
    "get_match_history",
    "get_trade_snapshot",
    "list_decks",
    "runtime_status",
    "shutdown_session",
    "start_watch",
]


def _request(
    command: str,
    *,
    args: Sequence[str] = (),
    bridge_path: str | None = None,
    timeout: float | None = None,
) -> Any:
    """Run ``command`` on the shared session, falling back to a one-shot call.

    ``FileNotFoundError`` (no bridge executable) is deliberately left to
    propagate: callers already handle it and a fallback could not help.
    """
    try:
        return mtgo_bridge_session.get_session(bridge_path).request(
            command, args=args, timeout=timeout
        )
    except BridgeSessionUnavailable as exc:
        logger.debug("Bridge session unavailable ({}); using a one-shot command.", exc)

    return mtgo_bridge_client.run_bridge_command(
        command,
        bridge_path=bridge_path,
        extra_args=tuple(args) or None,
        timeout=timeout,
    )


def _bridge_available(bridge_path: str | None = None) -> tuple[bool, str | None]:
    try:
        path = mtgo_bridge_client._require_bridge_path(bridge_path)  # type: ignore[attr-defined]
    except FileNotFoundError as exc:
        return False, str(exc)
    return True, str(path)


def ensure_runtime_ready(bridge_path: str | None = None) -> tuple[bool, str | None]:
    """Return True if the CLI bridge executable exists."""
    return runtime_status(bridge_path)


def runtime_status(bridge_path: str | None = None) -> tuple[bool, str | None]:
    ready, message = _bridge_available(bridge_path)
    return ready, None if ready else message


def get_collection_snapshot(
    bridge_path: str | None = None,
    timeout: float | None = None,
) -> Mapping[str, Any]:
    """Return the collection snapshot payload from the bridge."""
    payload = _request("collection", bridge_path=bridge_path, timeout=timeout)
    collection = payload.get("collection") if isinstance(payload, dict) else None
    if not isinstance(collection, dict):
        logger.debug("Collection payload missing or malformed; returning empty dict")
        return {}
    return collection


def get_match_history(
    bridge_path: str | None = None,
    timeout: float | None = None,
) -> Mapping[str, Any]:
    """Return the match history payload from the bridge."""
    payload = _request("history", bridge_path=bridge_path, timeout=timeout)
    history = payload.get("history") if isinstance(payload, dict) else None
    if not isinstance(history, dict):
        logger.debug("History payload missing or malformed; returning empty dict")
        return {}
    return history


def get_trade_snapshot(
    bridge_path: str | None = None,
    timeout: float | None = None,
) -> Mapping[str, Any]:
    """Return the active trade snapshot emitted by the bridge."""
    payload = _request("trade", args=("status",), bridge_path=bridge_path, timeout=timeout)
    trade = payload.get("trade") if isinstance(payload, Mapping) else None
    if not isinstance(trade, Mapping):
        logger.debug("Trade payload missing or malformed; returning empty dict")
        return {}
    return trade


def fetch_collection_async(
    *,
    bridge_path: str | None = None,
    context=None,  # noqa: ARG001 - kept for signature compatibility; see below
):
    """Return a future for the collection snapshot.

    ``context`` (a multiprocessing context) is accepted and ignored: the work no
    longer needs a worker process now that it rides the shared session.
    """
    return SessionRequestFuture(partial(_request, "collection", bridge_path=bridge_path))


def fetch_history_async(
    *,
    bridge_path: str | None = None,
    context=None,  # noqa: ARG001 - kept for signature compatibility
):
    return SessionRequestFuture(partial(_request, "history", bridge_path=bridge_path))


def start_watch(
    *,
    bridge_path: str | None = None,
    interval_ms: int = BRIDGE_SESSION_WATCH_INTERVAL_MS,
    context=None,
):
    """Start streaming challenge-timer snapshots.

    Prefers the shared session — which is what stops the watcher and a
    collection refresh from being two processes contending for MTGO's UI thread
    — and falls back to a dedicated ``watch`` subprocess when there is no
    session to ride on.
    """
    try:
        watcher = SessionWatcher(mtgo_bridge_session.get_session(bridge_path), interval_ms)
        watcher.start()
        return watcher
    except BridgeSessionUnavailable as exc:
        logger.debug("Bridge session unavailable ({}); using a standalone watcher.", exc)

    return mtgo_bridge_client.start_watch(
        bridge_path=bridge_path, interval_ms=interval_ms, context=context
    )


def accept_pending_trades(*_args, **_kwargs) -> dict[str, Any]:
    """Attempt to accept the currently active trade via the CLI bridge."""
    bridge_path = _kwargs.get("bridge_path")
    timeout = _kwargs.get("timeout")
    try:
        payload = _request("trade", args=("accept",), bridge_path=bridge_path, timeout=timeout)
    except (mtgo_bridge_client.BridgeCommandError, BridgeSessionError) as exc:
        return {
            "accepted": False,
            "requested": False,
            "error": str(exc),
        }

    if not isinstance(payload, Mapping):
        return {
            "accepted": False,
            "requested": False,
            "error": "bridge_response_malformed",
        }

    requested = bool(payload.get("requestedAcceptance"))
    accepted = bool(payload.get("accepted"))
    error = payload.get("error")
    return {
        "accepted": accepted,
        "requested": requested,
        "error": error,
        "timestamp": payload.get("timestamp"),
    }


def list_decks(*_args, **_kwargs) -> list[dict[str, Any]]:
    """Legacy API placeholder—deck grouping is not exposed by the CLI bridge."""
    return []


def get_full_collection(*_args, **_kwargs) -> Mapping[str, Any]:
    """Backward compatible alias for ``get_collection_snapshot``."""
    return get_collection_snapshot(*_args, **_kwargs)
