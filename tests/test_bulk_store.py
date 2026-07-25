"""Tests for gzip-on-disk bulk storage helpers."""

from __future__ import annotations

import gzip

from services.image_service.bulk_store import decode_bulk_bytes, gzip_chunks, is_gzip


def test_gzip_chunks_round_trips_through_decode():
    payload = b'[{"name": "Lightning Bolt"}, {"name": "Island"}]' * 1000
    # Feed it as several arbitrary chunks, like a streamed download.
    chunks = [payload[i : i + 7] for i in range(0, len(payload), 7)]
    compressed = b"".join(gzip_chunks(chunks))

    assert is_gzip(compressed)
    assert len(compressed) < len(payload)  # actually smaller
    assert decode_bulk_bytes(compressed) == payload
    # And it's a standard gzip stream any tool can read.
    assert gzip.decompress(compressed) == payload


def test_decode_passes_through_uncompressed():
    # A legacy uncompressed bulk file (no gzip magic) is returned as-is.
    plain = b'[{"name": "Forest"}]'
    assert not is_gzip(plain)
    assert decode_bulk_bytes(plain) == plain


def test_gzip_chunks_skips_empty_chunks():
    payload = b'{"x": 1}'
    compressed = b"".join(gzip_chunks([b"", payload, b"", b""]))
    assert decode_bulk_bytes(compressed) == payload


def test_empty_input_is_valid_empty_gzip():
    compressed = b"".join(gzip_chunks([]))
    assert is_gzip(compressed)
    assert decode_bulk_bytes(compressed) == b""
