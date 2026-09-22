"""One process per command: the MTGO bridge's fallback transport.

**This is the fallback, not the default.** Every call now goes through the one
long-lived ``MTGOBridge.exe serve`` process in :mod:`.session`, which pays
MTGOSDK's ~3.1s attach once instead of once per call; the facade in
:mod:`services.mtgo_bridge_service` drops back to this module only when a
session cannot be established -- most often an older bridge build with no
``serve`` mode -- or when ``MTGO_BRIDGE_NO_SESSION=1`` is set. It is kept
complete rather than trimmed to a stub precisely so that fallback is a change
of transport and nothing else.

This module runs the compiled ``MTGOBridge.exe`` and exposes:

* ``submit_bridge_command`` / ``BridgeCommandFuture`` for one-shot commands
  (collection, currency, all, username, logfiles, trade, ping) without blocking
  the caller thread.
* ``BridgeWatcher`` for streaming challenge timer / opponent snapshots using
  the bridge ``watch`` mode in a background process.

The implementation is split across three function-based submodules:

* :mod:`.discovery` — bridge discovery / process resolution
* :mod:`.commands` — one-shot command transport
* :mod:`.watch` — streaming / challenge-watch transport

This module is kept as a thin re-export facade so existing import paths
(``services.mtgo_bridge_service.client.*``) continue to resolve.
"""

from __future__ import annotations

from .commands import (
    BridgeCommandError,
    BridgeCommandFuture,
    _command_worker,
    _sanitize_json_payload,
    accept_trade,
    fetch_collection_snapshot,
    fetch_collection_snapshot_async,
    fetch_trade_snapshot,
    run_bridge_command,
    submit_bridge_command,
)
from .discovery import (
    BRIDGE_MANUAL_DOWNLOAD_URL,
    _default_bridge_candidates,
    _installed_app_dir,
    _require_bridge_path,
    _resolve_bridge_path,
)
from .watch import (
    BridgeWatcher,
    _queue_replace,
    _watch_worker,
    start_watch,
)

__all__ = [
    "BRIDGE_MANUAL_DOWNLOAD_URL",
    "BridgeCommandError",
    "BridgeCommandFuture",
    "BridgeWatcher",
    "accept_trade",
    "fetch_collection_snapshot",
    "fetch_collection_snapshot_async",
    "fetch_trade_snapshot",
    "run_bridge_command",
    "start_watch",
    "submit_bridge_command",
    # Internal helpers preserved for existing callers/tests that resolve
    # them through this facade.
    "_command_worker",
    "_default_bridge_candidates",
    "_installed_app_dir",
    "_queue_replace",
    "_require_bridge_path",
    "_resolve_bridge_path",
    "_sanitize_json_payload",
    "_watch_worker",
]
