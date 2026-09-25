#!/usr/bin/env python3
"""Refresh vendored MTGO archetype resources."""

from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404 - used for controlled git operations
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = ROOT / "vendor"
FORMAT_TARGET = VENDOR_DIR / "mtgo_format_data"
FORMAT_CARD_FILE = "card_colors.json"
PARSER_TARGET = VENDOR_DIR / "mtgo_archetype_parser" / "LICENSE"
METADATA_FILE = VENDOR_DIR / "vendor_sources.json"

# Neither vendored tree is redistributed any more: packaging/mtgo_tools.spec and
# packaging/installer.iss dropped both, because no module in this repository
# reads either one and MTGOFormatData publishes no licence to ship it under.
# They live in a developer checkout only. The licence copy is kept anyway, so
# that a tree on disk still states its own terms and so that restoring either
# one to the build stays a one-line change rather than a compliance review.
# Upstream file names vary, hence a candidate list rather than a single
# "LICENSE".
LICENSE_FILENAMES = (
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "LICENCE",
    "LICENCE.md",
    "LICENCE.txt",
    "COPYING",
    "COPYING.md",
    "COPYING.txt",
    "NOTICE",
)
# Written into vendor/mtgo_format_data/ so the tree on disk says where it came
# from and under what terms, even on the day upstream still publishes none.
PROVENANCE_FILE = "SOURCE.md"

SOURCES = {
    "MTGOFormatData": {
        "repo": "https://github.com/Badaro/MTGOFormatData.git",
        "target": FORMAT_TARGET,
    },
    "MTGOArchetypeParser": {
        "repo": "https://github.com/Badaro/MTGOArchetypeParser.git",
        "target": PARSER_TARGET,
    },
}


def run(cmd: list[str], cwd: Path | None = None) -> str:
    # Commands are internal git/poetry invocations; no shell usage
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)  # nosec B603
    return result.stdout.strip()


def clone(repo: str, dest: Path) -> Path:
    tempdir = Path(tempfile.mkdtemp(prefix="vendor-src-"))
    run(["git", "clone", "--depth", "1", repo, str(tempdir)])
    return tempdir


def find_license_files(tempdir: Path) -> list[Path]:
    """Return the licence-like files in a cloned repository's root."""
    return [tempdir / name for name in LICENSE_FILENAMES if (tempdir / name).is_file()]


def write_format_provenance(commit: str, copied_licenses: list[str]) -> None:
    """Record where the vendored format data came from and on what terms.

    MTGOFormatData publishes no licence file of its own (checked 2026-09-24:
    its repository root holds only ``Formats/`` and ``README.md``), so there is
    nothing to copy and the vendored tree would otherwise identify neither its
    origin nor its terms. This note is written unconditionally; if upstream
    ever adds a licence, ``copied_licenses`` is non-empty and the note points
    at the file instead of recording its absence.
    """
    repo = str(SOURCES["MTGOFormatData"]["repo"]).removesuffix(".git")
    if copied_licenses:
        terms = (
            "Upstream licence: see "
            + ", ".join(f"`{name}`" for name in sorted(copied_licenses))
            + ", copied from the upstream repository root."
        )
    else:
        terms = (
            "Upstream licence: **none published**. The upstream repository root "
            "carries no licence file and its README states no terms, so there "
            "is no grant to redistribute this data under \u2014 which is why nothing "
            "ships it. See `ATTRIBUTIONS.md` (License Compatibility)."
        )
    (FORMAT_TARGET / PROVENANCE_FILE).write_text(
        f"""# Vendored from MTGOFormatData

Repository: {repo}
Commit: {commit}

These files are the upstream `Formats/` tree copied verbatim by
`scripts/update_vendor_data.py`, for use in a developer checkout. Nothing
redistributes them: neither the Windows installer nor the frozen build copies
this tree (`packaging/installer.iss`, `packaging/mtgo_tools.spec`), because
there is no licence to ship it under and no module in the app reads it.

{terms}
""",
        encoding="utf-8",
    )


def refresh_format_data(tempdir: Path, commit: str) -> None:
    source_formats = tempdir / "Formats"
    if not source_formats.exists():
        raise RuntimeError(f"Expected Formats directory missing in {tempdir}")

    if FORMAT_TARGET.exists():
        shutil.rmtree(FORMAT_TARGET)
    FORMAT_TARGET.mkdir(parents=True, exist_ok=True)

    shutil.copy(source_formats / FORMAT_CARD_FILE, FORMAT_TARGET / FORMAT_CARD_FILE)
    for entry in source_formats.iterdir():
        if entry.name == FORMAT_CARD_FILE or entry.name.startswith(".git"):
            continue
        target_path = FORMAT_TARGET / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target_path)
        else:
            shutil.copy(entry, target_path)

    # The licence (when upstream has one) lives in the repository root, not in
    # Formats/, so the loop above would never reach it.
    copied = []
    for license_src in find_license_files(tempdir):
        shutil.copy(license_src, FORMAT_TARGET / license_src.name)
        copied.append(license_src.name)
    write_format_provenance(commit, copied)


def refresh_parser_license(tempdir: Path) -> None:
    licenses = find_license_files(tempdir)
    if not licenses:
        raise RuntimeError("Unable to locate a LICENSE in MTGOArchetypeParser repository.")
    PARSER_TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(licenses[0], PARSER_TARGET)


def update_metadata(updates: dict[str, str]) -> None:
    metadata: dict[str, dict[str, str]]
    if METADATA_FILE.exists():
        metadata = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    else:
        metadata = {}
    for key, commit in updates.items():
        entry = metadata.setdefault(key, {})
        entry["repository"] = SOURCES[key]["repo"].removesuffix(".git")
        entry["commit"] = commit
    METADATA_FILE.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def main() -> int:
    updates: dict[str, str] = {}
    for key, config in SOURCES.items():
        print(f"Updating {key}…", flush=True)
        tempdir = clone(config["repo"], ROOT)
        try:
            commit = run(["git", "rev-parse", "HEAD"], cwd=tempdir)
            updates[key] = commit
            if key == "MTGOFormatData":
                refresh_format_data(tempdir, commit)
            else:
                refresh_parser_license(tempdir)
        finally:
            shutil.rmtree(tempdir, ignore_errors=True)
    update_metadata(updates)
    print("Vendor resources refreshed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
