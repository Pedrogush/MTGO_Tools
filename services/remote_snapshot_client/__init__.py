"""Remote Snapshot Client package — consumes published metagame artifacts.

This package downloads and stages snapshots from the MTGO_Scrapes_Repository so
the app can resolve archetype lists, deck metadata, and metagame stats without
hitting MTGGoldfish directly in the common path.

Split by responsibility into internal modules:

- ``http``: HTTP JSON fetch with urllib fallback (exposes :class:`RemoteSnapshotError`)
- ``manifest``: top-level manifest download and caching
- ``artifact``: per-format artifact download and disk staging
- ``service``: :class:`RemoteSnapshotClient` composed from the above mixins
"""

from __future__ import annotations

from services.remote_snapshot_client.http import RemoteSnapshotError
from services.remote_snapshot_client.service import RemoteSnapshotClient

_default_client: RemoteSnapshotClient | None = None


def get_remote_snapshot_client() -> RemoteSnapshotClient:
    """Return the shared ``RemoteSnapshotClient`` instance."""
    global _default_client
    if _default_client is None:
        _default_client = RemoteSnapshotClient()
    return _default_client


def reset_remote_snapshot_client() -> None:
    """Reset the singleton — primarily for test isolation."""
    global _default_client
    _default_client = None


__all__ = [
    "RemoteSnapshotClient",
    "RemoteSnapshotError",
    "get_remote_snapshot_client",
    "reset_remote_snapshot_client",
]
