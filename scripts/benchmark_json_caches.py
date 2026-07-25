#!/usr/bin/env python3
"""Benchmark the card metadata caches to understand their load times.

Compares stdlib ``json`` against ``msgspec`` (with and without schemas) so the
speed improvement from the msgspec migration is clearly visible.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

from loguru import logger

from services.image_service import (
    BULK_DATA_CACHE,
    PRINTING_INDEX_CACHE,
)
from services.image_service.bulk_store import decode_bulk_bytes, is_gzip
from services.image_service.schemas import (
    _bulk_cards_decoder,
    _printing_index_decoder,
)
from utils.json_io import fast_load


def _format_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.1f} ms"
    return f"{seconds:.2f} s"


def _benchmark_variant(
    path: Path,
    iterations: int,
    label: str,
    loader,
) -> list[float]:
    """Run *loader* against *path* for *iterations* and return elapsed times."""
    durations: list[float] = []
    for i in range(iterations):
        start = time.perf_counter()
        try:
            loader(path)
        except Exception as exc:
            logger.error(f"{label}: failed on iteration {i + 1}: {exc}")
            return []
        durations.append(time.perf_counter() - start)
        logger.info(f"  {label} iter {i + 1}: {_format_duration(durations[-1])}")
    return durations


def _summarise(label: str, durations: list[float]) -> None:
    if not durations:
        return
    logger.info(
        "{label}: min={min}  avg={avg}  max={max}",
        label=label,
        min=_format_duration(min(durations)),
        avg=_format_duration(statistics.mean(durations)),
        max=_format_duration(max(durations)),
    )


def _benchmark(path: Path, iterations: int, label: str) -> None:
    if not path.exists():
        logger.warning(f"{label} cache not found at {path}")
        return

    # The bulk cache is stored gzip-compressed on disk (bulk_store). This tool
    # measures JSON *decode* speed, so materialize the decompressed JSON to a
    # temp file once and benchmark that; otherwise every variant would just fail
    # to parse the gzip bytes. `original_path` is kept for the typed-schema
    # selection, since `read_path` may now be the decompressed temp file.
    original_path = path
    temp_path: Path | None = None
    raw = path.read_bytes()
    if is_gzip(raw):
        fd, tmp_name = tempfile.mkstemp(suffix=".json")
        temp_path = Path(tmp_name)
        with os.fdopen(fd, "wb") as fh:
            fh.write(decode_bulk_bytes(raw))
        path = temp_path
    try:
        _benchmark_decoded(path, original_path=original_path, iterations=iterations, label=label)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _benchmark_decoded(path: Path, *, original_path: Path, iterations: int, label: str) -> None:
    size_mb = path.stat().st_size / (1024 * 1024)
    logger.info(f"\n{'='*60}")
    logger.info(f"{label} ({size_mb:.1f} MB)  —  {iterations} iteration(s)")
    logger.info(f"{'='*60}")

    # stdlib json
    logger.info("--- stdlib json ---")
    stdlib_times = _benchmark_variant(
        path,
        iterations,
        "stdlib",
        lambda p: json.loads(p.read_bytes()),
    )
    _summarise("stdlib json", stdlib_times)

    # msgspec Any (no schema)
    logger.info("--- msgspec Any (no schema) ---")
    msgspec_any_times = _benchmark_variant(
        path,
        iterations,
        "msgspec[Any]",
        fast_load,
    )
    _summarise("msgspec Any", msgspec_any_times)

    # msgspec typed (only available for known schemas)
    if original_path == PRINTING_INDEX_CACHE:
        logger.info("--- msgspec PrintingIndexPayload (typed schema) ---")
        typed_times = _benchmark_variant(
            path,
            iterations,
            "msgspec[schema]",
            lambda p: _printing_index_decoder.decode(p.read_bytes()),
        )
        _summarise("msgspec typed", typed_times)
    elif original_path == BULK_DATA_CACHE:
        logger.info("--- msgspec list[BulkCard] (typed schema, partial fields) ---")
        typed_times = _benchmark_variant(
            path,
            iterations,
            "msgspec[schema]",
            lambda p: _bulk_cards_decoder.decode(p.read_bytes()),
        )
        _summarise("msgspec typed", typed_times)
    else:
        typed_times = []

    # Speedup summary
    if stdlib_times and msgspec_any_times:
        speedup_any = statistics.mean(stdlib_times) / statistics.mean(msgspec_any_times)
        logger.info(f"msgspec Any speedup: {speedup_any:.2f}x")
    if stdlib_times and typed_times:
        speedup_typed = statistics.mean(stdlib_times) / statistics.mean(typed_times)
        logger.info(f"msgspec typed speedup: {speedup_typed:.2f}x")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure how long it takes to load the card metadata caches into memory."
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1,
        help="How many times to load each cache (default: 1).",
    )
    parser.add_argument(
        "--skip-bulk",
        action="store_true",
        help="Skip measuring the full bulk_data.json cache.",
    )
    parser.add_argument(
        "--skip-printings",
        action="store_true",
        help="Skip measuring the compact printings index cache.",
    )

    args = parser.parse_args()

    if args.iterations < 1:
        parser.error("--iterations must be at least 1")

    if args.skip_bulk and args.skip_printings:
        parser.error("Cannot skip both caches; nothing to benchmark.")

    if not args.skip_printings:
        _benchmark(PRINTING_INDEX_CACHE, args.iterations, "Printings index")

    if not args.skip_bulk:
        _benchmark(BULK_DATA_CACHE, args.iterations, "Bulk data")

    return 0


if __name__ == "__main__":
    sys.exit(main())
