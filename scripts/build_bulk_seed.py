"""Build the bundled bulk-data seed shipped inside the installer.

Downloads Scryfall's ``default_cards`` bulk file and writes it back out
gzip-compressed to ``--out`` (default ``dist/seed/bulk_data.json.gz``). The
installer bundles that file next to the executable; on first run the app
decompresses it into the image cache (see ``services/image_service/seed.py``),
so a fresh install starts with the local index already present instead of
racing a cold download.

``default_cards`` is required (not the smaller ``oracle_cards``) because the
card inspector's printing navigation needs every printing, which only
``default_cards`` carries. The download is gzipped (~78 MB), far smaller than the
~620 MB uncompressed size.

Scryfall publishes the file as gzipped **JSONL** (one card per line) and the old
``.json.gz`` URLs now 404, so the stream is decompressed, rewritten into the JSON
array the app's readers expect, and re-compressed — see
``services.image_service.bulk_store``, which owns that pipeline and is shared
with the app's own download path so the two cannot drift.

Usage:
    python scripts/build_bulk_seed.py [--out PATH] [--timeout SECONDS]
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

import requests

# Run as a plain script (``python scripts/build_bulk_seed.py``) from the
# installer build, so the repo root has to be importable before the app package
# can be reached.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.image_service.bulk_store import (  # noqa: E402
    gunzip_chunks,
    gzip_chunks,
    jsonl_to_json_array,
)

BULK_DATA_URL = "https://api.scryfall.com/bulk-data/default-cards"
USER_AGENT = "MTGOTools-SeedBuilder/1.0"
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def build_seed(out_path: Path, timeout: float) -> Path:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    print(f"Resolving default_cards bulk download URI from {BULK_DATA_URL}")
    meta = session.get(BULK_DATA_URL, timeout=timeout)
    meta.raise_for_status()
    info = meta.json()
    # Scryfall retired ``download_uri``/``size`` when it moved to JSONL; fail
    # loudly with the available keys if the shape shifts again.
    try:
        download_uri = info["jsonl_download_uri"]
    except KeyError:
        raise RuntimeError(
            f"No 'jsonl_download_uri' in the bulk-data response (keys: {sorted(info)})"
        ) from None
    compressed = info.get("compressed_size", 0)
    print(f"  jsonl_download_uri = {download_uri}")
    print(f"  compressed size = {compressed / 1e6:.1f} MB")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(out_path.parent), suffix=".gz.tmp")
    tmp_path = Path(tmp_name)
    try:
        print(f"Streaming JSONL -> JSON array + re-gzipping to {out_path}")
        with session.get(download_uri, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            # The gzip here is file content, not a transfer encoding, so nothing
            # decodes it for us. Same pipeline the app's downloader uses.
            with os.fdopen(fd, "wb") as raw_out:
                for chunk in gzip_chunks(
                    jsonl_to_json_array(
                        gunzip_chunks(resp.iter_content(chunk_size=_DOWNLOAD_CHUNK_BYTES))
                    )
                ):
                    raw_out.write(chunk)
        os.replace(tmp_path, out_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    size_mb = out_path.stat().st_size / 1e6
    print(f"Wrote {out_path} ({size_mb:.1f} MB gzipped)")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=_repo_root() / "dist" / "seed" / "bulk_data.json.gz",
        help="Output path for the gzipped seed (default: dist/seed/bulk_data.json.gz)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="Per-request timeout in seconds (default: 300)",
    )
    args = parser.parse_args(argv)

    try:
        build_seed(args.out, args.timeout)
    except Exception as exc:  # noqa: BLE001 - top-level build-script guard
        print(f"ERROR: failed to build bulk seed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
