#!/usr/bin/env python3
"""Keep the published GitHub Releases down to the ones anyone would install.

Two rules, applied in order:

1. **One release per ``MAJOR.MINOR`` line** -- the newest patch. Nobody wants
   1.0.0 once 1.0.4 exists; it is the same line with known bugs still in it.
   Keeping the newest patch of *each* line still lets someone stay on an older
   line deliberately (the last build before a redesign, say).
2. **At most ``--max`` releases** (default 10), newest first, in case the number
   of lines ever grows past that.

Only the **Release** is deleted, never the tag. Tags are the version history and
the base ``next_version.py`` computes from, they cost nothing, and deleting one
would let a number be silently reused. What a prune reclaims is the ~180 MB
installer attached to a release nobody should be downloading.

Usage:
    scripts/prune_releases.py --dry-run     # print what would go, delete nothing
    scripts/prune_releases.py               # prune for real
    scripts/prune_releases.py --max 5

Requires the ``gh`` CLI, authenticated (``GH_TOKEN`` in CI).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")

DEFAULT_MAX_RELEASES = 10


def _gh(*args: str) -> str:
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def published_releases() -> list[tuple[int, int, int]]:
    """Every published release tag parsed to a version, newest first.

    Releases whose tag isn't a bare ``vX.Y.Z`` are ignored rather than deleted:
    this script only has an opinion about the ones the release workflow made.
    """
    raw = _gh("release", "list", "--limit", "200", "--json", "tagName")
    versions = []
    for entry in json.loads(raw):
        match = _TAG_RE.match(entry.get("tagName", ""))
        if match:
            versions.append(tuple(int(part) for part in match.groups()))
    return sorted(versions, reverse=True)


def select_keep(
    versions: list[tuple[int, int, int]], max_releases: int = DEFAULT_MAX_RELEASES
) -> list[tuple[int, int, int]]:
    """The releases that survive: newest patch per line, capped at ``max_releases``."""
    newest_per_line: dict[tuple[int, int], tuple[int, int, int]] = {}
    for version in versions:
        line = (version[0], version[1])
        if version > newest_per_line.get(line, (-1, -1, -1)):
            newest_per_line[line] = version
    return sorted(newest_per_line.values(), reverse=True)[:max_releases]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max",
        type=int,
        default=DEFAULT_MAX_RELEASES,
        dest="max_releases",
        help=f"Most releases to keep (default {DEFAULT_MAX_RELEASES}).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would be deleted, delete nothing."
    )
    args = parser.parse_args(argv)

    versions = published_releases()
    if not versions:
        print("No versioned releases published; nothing to prune.")
        return 0

    keep = set(select_keep(versions, args.max_releases))
    drop = [version for version in versions if version not in keep]

    for version in sorted(keep, reverse=True):
        print(f"keep   v{version[0]}.{version[1]}.{version[2]}")
    if not drop:
        print(f"Nothing to prune ({len(keep)} release(s) published).")
        return 0

    for version in drop:
        tag = f"v{version[0]}.{version[1]}.{version[2]}"
        if args.dry_run:
            print(f"would delete {tag}")
            continue
        # The tag is deliberately left in place -- see the module docstring.
        _gh("release", "delete", tag, "--yes")
        print(f"deleted {tag} (tag kept)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
