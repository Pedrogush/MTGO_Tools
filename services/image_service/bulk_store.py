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

Upstream, Scryfall retired the JSON-array bulk files in favour of **JSONL** — one
card object per line — and the old ``.json.gz`` URLs now 404. The stored format
here is deliberately unchanged: :func:`jsonl_to_json_array` rewrites the stream
back into an array as it is downloaded, so every reader, the on-disk cache, and
the installer-bundled seed all keep working untouched. The download pipeline is

    gunzip_chunks -> jsonl_to_json_array -> gzip_chunks -> disk

because the upstream file is served as ``Content-Type: application/gzip`` with no
``Content-Encoding``, i.e. the gzip is *file content* that HTTP clients will not
transparently decode (it used to arrive gzip *transfer*-encoded, which they did).
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


def gunzip_chunks(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Gzip-*de*compress a stream of byte chunks — the inverse of :func:`gzip_chunks`.

    Needed because the upstream bulk file is gzip as *file content* rather than
    as a transfer encoding, so an HTTP client hands back the compressed bytes.

    Handles a *multi-member* stream (several gzip files concatenated, which the
    format permits): a single ``decompressobj`` stops at the first member's end
    and parks the remainder in ``unused_data``, so continuing there is what keeps
    a concatenated file from being silently truncated mid-way.
    """
    decompressor = zlib.decompressobj(_GZIP_WBITS)
    for chunk in chunks:
        if not chunk:
            continue
        out = decompressor.decompress(chunk)
        if out:
            yield out
        # Roll onto the next member, and keep rolling: one chunk can span the
        # tail of one member, a whole short member, and the head of the next.
        while decompressor.eof and decompressor.unused_data:
            leftover = decompressor.unused_data
            decompressor = zlib.decompressobj(_GZIP_WBITS)
            out = decompressor.decompress(leftover)
            if out:
                yield out
    tail = decompressor.flush()
    if tail:
        yield tail


def jsonl_to_json_array(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Rewrite a JSONL byte stream into a JSON-array byte stream.

    Scryfall now publishes one card object per line; the readers here all decode
    a single JSON array (``msgspec.json.Decoder(list[BulkCard])``). Bridging at
    download time keeps the stored format — and therefore every reader, every
    existing cache, and the bundled seed — unchanged.

    Splitting on newlines is safe: JSON escapes a literal newline inside a string
    as ``\\n``, so a raw ``0x0A`` only ever appears as a record separator.

    Operates chunk-wise (not line-wise) because the input arrives as arbitrary
    HTTP chunks that split records; a partial trailing line is carried over into
    the next chunk. Blank lines are skipped, and empty input yields ``[]``.
    """
    yield b"["
    first = True
    pending = b""
    for chunk in chunks:
        if not chunk:
            continue
        pending += chunk
        start = 0
        while (newline := pending.find(b"\n", start)) != -1:
            line = pending[start:newline].strip()
            start = newline + 1
            if not line:
                continue
            yield line if first else b"," + line
            first = False
        pending = pending[start:]

    # Whatever is left after the last newline (upstream omits the trailing one).
    line = pending.strip()
    if line:
        yield line if first else b"," + line
    yield b"]"


__all__ = [
    "decode_bulk_bytes",
    "gunzip_chunks",
    "gzip_chunks",
    "is_gzip",
    "jsonl_to_json_array",
]
