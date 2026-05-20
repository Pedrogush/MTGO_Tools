"""MTGO bridge service: Python-facing facade over the CLI bridge.

Wraps the subprocess/multiprocessing transport in :mod:`.client` and
exposes collection/history/trade snapshots and the challenge watcher.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from loguru import logger

from . import client as mtgo_bridge_client


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
    payload = mtgo_bridge_client.run_bridge_command(
        "collection", bridge_path=bridge_path, timeout=timeout
    )
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
    payload = mtgo_bridge_client.run_bridge_command(
        "history", bridge_path=bridge_path, timeout=timeout
    )
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
    payload = mtgo_bridge_client.fetch_trade_snapshot(
        bridge_path=bridge_path,
        timeout=timeout,
    )
    trade = payload.get("trade") if isinstance(payload, Mapping) else None
    if not isinstance(trade, Mapping):
        logger.debug("Trade payload missing or malformed; returning empty dict")
        return {}
    return trade


def fetch_collection_async(
    *,
    bridge_path: str | None = None,
    context=None,
):
    return mtgo_bridge_client.fetch_collection_snapshot_async(
        bridge_path=bridge_path, context=context
    )


def fetch_history_async(
    *,
    bridge_path: str | None = None,
    context=None,
):
    return mtgo_bridge_client.fetch_match_history_async(bridge_path=bridge_path, context=context)


def start_watch(
    *,
    bridge_path: str | None = None,
    interval_ms: int = 500,
    context=None,
):
    return mtgo_bridge_client.start_watch(
        bridge_path=bridge_path, interval_ms=interval_ms, context=context
    )


def accept_pending_trades(*_args, **_kwargs) -> dict[str, Any]:
    """Attempt to accept the currently active trade via the CLI bridge."""
    bridge_path = _kwargs.get("bridge_path")
    timeout = _kwargs.get("timeout")
    try:
        payload = mtgo_bridge_client.accept_trade(
            bridge_path=bridge_path,
            timeout=timeout,
        )
    except mtgo_bridge_client.BridgeCommandError as exc:  # type: ignore[attr-defined]
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
