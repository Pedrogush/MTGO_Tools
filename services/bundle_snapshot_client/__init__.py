"""Bundle Snapshot Client package — download and hydrate the remote client bundle.

The remote repository publishes a single compressed archive (``client-bundle.tar.gz``)
that contains archetype lists and deck lists for all supported formats.  This
package downloads that archive in-memory, extracts it, and writes the data into
the local caches used by ``MetagameRepository`` so that archetype fetching, deck
loading, radar analysis, and metagame analysis all start with warm caches.

Why this service intentionally fans out to three repositories
-------------------------------------------------------------

The bundle is a single artifact (one URL, one download, one freshness stamp) that
packs multiple cache shapes together.  Hydrating ``deck_text_cache``,
``format_card_pool_repository`` and ``radar_repository`` from one parse pass is
the entire purpose of the service — splitting it would either require multiple
downloads (defeating the bundle) or a coordinator that still talks to all three.
The MTGO-decklist merge also needs archetype href lookups to write into
``deck_text_cache``, so even "just the deck-text slice" is not independent of the
archetype slice.  See issue #450 for the investigation that confirmed this.

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
