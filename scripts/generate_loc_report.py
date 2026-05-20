#!/usr/bin/env python3
"""Regenerate ``LOC_REPORT.md`` at the repo root.

Counts raw newlines (``wc -l`` semantics) for every git-tracked ``*.py`` file,
groups by top-level directory, and writes a markdown report stamped with the
current HEAD commit and date.

Usage::

    python scripts/generate_loc_report.py            # write LOC_REPORT.md
    python scripts/generate_loc_report.py --check    # exit 1 if stale (CI)
    python scripts/generate_loc_report.py --stdout   # print, don't write

The script is stdlib-only and resolves the repo root via ``git``, so it can be
invoked from any working directory (and from a git hook).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SECTIONS = [
    "controllers",
    "repositories",
    "widgets",
    "services",
    "tests",
    "automation",
    "utils",
]
REPORT_NAME = "LOC_REPORT.md"


def _git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def _repo_root() -> Path:
    return Path(_git("rev-parse", "--show-toplevel"))


def _section_of(path: str) -> str:
    top = path.split("/", 1)[0]
    return top if top in SECTIONS else "other"


def _count_lines(path: Path) -> int:
    # Match ``wc -l``: count newline bytes. Safe for any encoding.
    with path.open("rb") as f:
        return sum(chunk.count(b"\n") for chunk in iter(lambda: f.read(1 << 16), b""))


def build_report(root: Path) -> str:
    files = _git("ls-files", "*.py", cwd=root).splitlines()
    rows: list[tuple[int, str]] = []
    for rel in files:
        p = root / rel
        if not p.is_file():  # skip submodule pointers, deleted-but-staged, etc.
            continue
        rows.append((_count_lines(p), rel))

    buckets: dict[str, list[tuple[int, str]]] = {s: [] for s in SECTIONS + ["other"]}
    for loc, rel in rows:
        buckets[_section_of(rel)].append((loc, rel))
    for b in buckets.values():
        b.sort(key=lambda r: (-r[0], r[1]))

    commit = _git("rev-parse", "HEAD", cwd=root)
    commit_short = commit[:7]
    commit_date = _git("show", "-s", "--format=%cI", "HEAD", cwd=root)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    total_loc = sum(loc for loc, _ in rows)

    out: list[str] = []
    out.append("# Lines of Code by File (.py only)")
    out.append("")
    out.append(f"- Commit: `{commit_short}` ({commit})")
    out.append(f"- Commit date: {commit_date}")
    out.append(f"- Generated (UTC): {generated_at}")
    out.append(f"- Files counted: **{len(rows)}** (all git-tracked `*.py` files)")
    out.append(f"- Total lines: **{total_loc:,}**")
    out.append("")
    out.append(
        "Counts are raw `wc -l` (newline count). Files are grouped by top-level "
        "directory and sorted descending within each section. Regenerate with "
        "`python scripts/generate_loc_report.py`."
    )
    out.append("")

    out.append("## Summary")
    out.append("")
    out.append("| Section | Files | LOC |")
    out.append("|:--------|------:|----:|")
    for s in SECTIONS + ["other"]:
        b = buckets[s]
        if not b:
            continue
        out.append(f"| {s} | {len(b)} | {sum(r[0] for r in b):,} |")
    out.append("")

    for s in SECTIONS + ["other"]:
        b = buckets[s]
        if not b:
            continue
        out.append(f"## {s} ({len(b)} files, {sum(r[0] for r in b):,} LOC)")
        out.append("")
        out.append("| LOC | File |")
        out.append("|----:|:-----|")
        for loc, rel in b:
            out.append(f"| {loc} | `{rel}` |")
        out.append("")

    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if LOC_REPORT.md differs from freshly-generated content.",
    )
    mode.add_argument(
        "--stdout",
        action="store_true",
        help="Print the report to stdout instead of writing the file.",
    )
    args = parser.parse_args(argv)

    root = _repo_root()
    content = build_report(root)
    target = root / REPORT_NAME

    if args.stdout:
        sys.stdout.write(content)
        return 0

    if args.check:
        current = target.read_text() if target.exists() else ""
        # Strip volatile metadata before comparing: generation time changes every
        # run, and the HEAD commit differs between the author's branch (where they
        # regenerated) and the synthetic merge commit GitHub builds for PRs. The
        # check is about whether the *body* (counts, paths, sections) is current.
        volatile_prefixes = ("- Commit:", "- Commit date:", "- Generated (UTC):")

        def _canonical(text: str) -> str:
            return "\n".join(
                ln for ln in text.splitlines() if not ln.startswith(volatile_prefixes)
            )

        if _canonical(current) != _canonical(content):
            print(f"{REPORT_NAME} is stale; run scripts/generate_loc_report.py", file=sys.stderr)
            return 1
        return 0

    target.write_text(content)
    print(f"Wrote {target.relative_to(root)} ({content.count(chr(10)) + 1} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
