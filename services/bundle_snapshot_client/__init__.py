"""Bundle Snapshot Client package — download and hydrate the remote client bundle.

The remote repository publishes a single compressed archive (``client-bundle.tar.gz``)
that contains archetype lists and deck lists for all supported formats.  This
package downloads that archive in-memory, extracts it, and writes the data into
the local caches used by ``MetagameRepository`` so that archetype fetching, deck
loading, radar analysis, and metagame analysis all start with warm caches.

Split by responsibility into internal modules:

- ``stamp``: stamp file freshness tracking
- ``http``: bundle download + HTTP fallbacks (exposes :class:`BundleSnapshotError`)
- ``parser``: tar.gz archive parsing into grouped entries
- ``archetype_cache``: archetype list / deck list / MTGO decklist / deck-text hydration
- ``snapshot_cache``: format card pool and precomputed radar hydration
- ``service``: :class:`BundleSnapshotClient` composed from the above mixins
"""

from __future__ import annotations

from services.bundle_snapshot_client.http import BundleSnapshotError
from services.bundle_snapshot_client.service import BundleSnapshotClient

_default_client: BundleSnapshotClient | None = None


def get_bundle_snapshot_client() -> BundleSnapshotClient:
    global _default_client
    if _default_client is None:
        _default_client = BundleSnapshotClient()
    return _default_client


def reset_bundle_snapshot_client() -> None:
    """Reset the singleton — primarily for test isolation."""
    global _default_client
    _default_client = None


__all__ = [
    "BundleSnapshotClient",
    "BundleSnapshotError",
    "get_bundle_snapshot_client",
    "reset_bundle_snapshot_client",
]
