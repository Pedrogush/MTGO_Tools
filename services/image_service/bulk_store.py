"""Gzip-on-disk storage for the Scryfall bulk-data file.

The bulk metadata file is large uncompressed (~620 MB) but compresses ~5x, so
we store it gzip-compressed on disk and decompress it in memory when an index is
(re)built. The whole file is already loaded into memory to feed msgspec either
way, so the only added cost is a one-off ~1-2 s decompress on the rare rebuild —
in exchange for cutting the on-disk footprint to ~130 MB.

The on-disk **filename is unchanged** (``bulk_data.json``); the content is
identified by its gzip magic bytes on read (:func:`decode_bulk_bytes`). That
keeps two things free:

* a legacy *uncompressed* ``bulk_data.json`` written by an older build still
  loads, and the next download rewrites it compressed — no migration, no forced
  re-download; and
* the installer-bundled seed (already gzip) is copied in verbatim rather than
  decompressed, so a fresh install lands the compact form directly.

Every reader of the bulk file must go through :func:`decode_bulk_bytes`, and the
downloader writes through :func:`gzip_chunks`.
"""

from __future__ import annotations

import zlib
from collections.abc import Iterable, Iterator

# gzip file magic (RFC 1952). Present iff the on-disk content is compressed.
_GZIP_MAGIC = b"\x1f\x8b"
# zlib window size selecting the gzip container (16) + max window (15). Using
# zlib directly (rather than the gzip module) lets us stream-compress the
# download and stream-decompress a whole-file read with no temp files.
_GZIP_WBITS = 31
# Default balance of speed vs. ratio; 9 is markedly slower on a 600 MB file for
# only a few percent smaller output.
_GZIP_LEVEL = 6


def is_gzip(raw: bytes) -> bool:
    return raw[:2] == _GZIP_MAGIC


def decode_bulk_bytes(raw: bytes) -> bytes:
    """Return the JSON bytes, decompressing first if the content is gzip."""
    if is_gzip(raw):
        return zlib.decompress(raw, _GZIP_WBITS)
    return raw


def gzip_chunks(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Gzip-compress a stream of byte chunks (feeds ``atomic_write_stream``)."""
    compressor = zlib.compressobj(_GZIP_LEVEL, zlib.DEFLATED, _GZIP_WBITS)
    for chunk in chunks:
        if not chunk:
            continue
        out = compressor.compress(chunk)
        if out:
            yield out
    tail = compressor.flush()
    if tail:
        yield tail


__all__ = ["decode_bulk_bytes", "gzip_chunks", "is_gzip"]
