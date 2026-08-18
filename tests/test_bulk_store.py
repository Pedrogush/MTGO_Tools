"""Tests for gzip-on-disk bulk storage helpers."""

from __future__ import annotations

import gzip
import json

from services.image_service.bulk_store import (
    decode_bulk_bytes,
    gunzip_chunks,
    gzip_chunks,
    is_gzip,
    jsonl_to_json_array,
)
from services.image_service.schemas import _bulk_cards_decoder


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


def test_gunzip_chunks_inverts_gzip_chunks():
    payload = b'{"name": "Island"}\n' * 500
    chunks = [payload[i : i + 13] for i in range(0, len(payload), 13)]
    assert b"".join(gunzip_chunks(gzip_chunks(chunks))) == payload


def test_gunzip_chunks_handles_concatenated_members():
    """Concatenated gzip members are one valid stream; truncating them loses data."""
    members = gzip.compress(b"one\n") + gzip.compress(b"two\n") + gzip.compress(b"three\n")
    for size in (1, 5, 17, len(members)):
        wire = [members[i : i + size] for i in range(0, len(members), size)]
        assert b"".join(gunzip_chunks(wire)) == b"one\ntwo\nthree\n", f"chunk size {size}"


# ---------------------------------------------------------------------------
# JSONL -> JSON array
#
# Scryfall retired the JSON-array bulk files; the download pipeline rewrites the
# JSONL stream back into an array so the stored format and every reader stay
# unchanged. See services/image_service/bulk_store.py.
# ---------------------------------------------------------------------------

CARD_LINES = [
    b'{"id": "aaa", "name": "Lightning Bolt"}',
    b'{"id": "bbb", "name": "Island"}',
    b'{"id": "ccc", "name": "Forest"}',
]


def test_jsonl_becomes_a_json_array():
    out = b"".join(jsonl_to_json_array([b"\n".join(CARD_LINES)]))
    assert json.loads(out) == [
        {"id": "aaa", "name": "Lightning Bolt"},
        {"id": "bbb", "name": "Island"},
        {"id": "ccc", "name": "Forest"},
    ]


def test_records_split_across_chunks_are_rejoined():
    """HTTP chunks land mid-record, so a partial line must carry into the next."""
    payload = b"\n".join(CARD_LINES)
    for size in (1, 2, 3, 7, 16, 64, len(payload)):
        chunks = [payload[i : i + size] for i in range(0, len(payload), size)]
        out = b"".join(jsonl_to_json_array(chunks))
        assert json.loads(out) == json.loads(
            b"".join(jsonl_to_json_array([payload]))
        ), f"chunk size {size}"


def test_trailing_newline_does_not_add_an_empty_record():
    with_newline = b"".join(jsonl_to_json_array([b"\n".join(CARD_LINES) + b"\n"]))
    without = b"".join(jsonl_to_json_array([b"\n".join(CARD_LINES)]))
    assert json.loads(with_newline) == json.loads(without)
    assert len(json.loads(with_newline)) == 3


def test_blank_lines_are_skipped():
    payload = b"\n\n" + b"\n\n".join(CARD_LINES) + b"\n\n"
    assert len(json.loads(b"".join(jsonl_to_json_array([payload])))) == 3


def test_empty_input_yields_an_empty_array():
    assert json.loads(b"".join(jsonl_to_json_array([]))) == []
    assert json.loads(b"".join(jsonl_to_json_array([b"", b"\n", b"  "]))) == []


def test_embedded_newline_escape_is_not_a_record_separator():
    """A literal newline inside a JSON string is escaped, so splitting is safe."""
    line = json.dumps({"id": "x", "oracle_text": "Draw a card.\nThen discard."}).encode()
    out = json.loads(b"".join(jsonl_to_json_array([line])))
    assert out == [{"id": "x", "oracle_text": "Draw a card.\nThen discard."}]


def test_full_download_pipeline_feeds_the_real_decoder():
    """gunzip -> JSONL-to-array -> gzip, then the decoder the readers actually use."""
    cards = [
        {"id": "aaa", "name": "Lightning Bolt", "set": "lea", "collector_number": "161"},
        {"id": "bbb", "name": "Scalding Tarn", "set": "mh2", "collector_number": "254"},
    ]
    upstream = gzip.compress(b"\n".join(json.dumps(c).encode() for c in cards))
    wire = [upstream[i : i + 8] for i in range(0, len(upstream), 8)]

    stored = b"".join(gzip_chunks(jsonl_to_json_array(gunzip_chunks(wire))))

    assert is_gzip(stored)
    decoded = _bulk_cards_decoder.decode(decode_bulk_bytes(stored))
    assert [c.name for c in decoded] == ["Lightning Bolt", "Scalding Tarn"]
    assert [c.set for c in decoded] == ["lea", "mh2"]
