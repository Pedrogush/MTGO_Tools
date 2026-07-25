#!/usr/bin/env python3
"""Derive the project's semantic version from conventional-commit history.

Single source of truth:
  * The repo-root ``VERSION`` file holds the current released version.
  * ``vX.Y.Z`` git tags mark releases.

The NEXT version is computed by scanning conventional-commit subjects (and
bodies, for breaking-change footers) since the most recent ``vX.Y.Z`` tag:

    <type>!: ...            -> MAJOR   (also any body with "BREAKING CHANGE")
    feat: ...               -> MINOR
    fix: ... / perf: ...    -> PATCH
    anything else           -> no release-worthy change

Precedence is major > minor > patch. If nothing release-worthy landed since the
last tag, the next version equals the current one (no release).

When no ``vX.Y.Z`` tag exists yet, this reports the current VERSION unchanged so
the CI workflow can establish the baseline tag without a spurious bump.

Usage:
    scripts/next_version.py current      # print current version (from VERSION)
    scripts/next_version.py next         # print the computed next version
    scripts/next_version.py bump         # print: major | minor | patch | none
    scripts/next_version.py apply        # write the next version into VERSION
                                         # (every other file derives from it)

The command is intentionally dependency-free (stdlib + git) so it runs the same
locally and in CI.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO_ROOT / "VERSION"

# type(scope)!: subject  ->  captures type and the optional breaking "!"
_SUBJECT_RE = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\([^)]*\))?(?P<bang>!)?:", re.IGNORECASE)
_BREAKING_BODY_RE = re.compile(r"^BREAKING[ -]CHANGE:", re.IGNORECASE | re.MULTILINE)

# Order matters: index in this list is the bump rank (higher = bigger bump).
_RANK = {None: 0, "patch": 1, "minor": 2, "major": 3}


def _git(*args: str) -> str:
    """Run a git command in the repo and return stripped stdout ('' on failure)."""
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return out.stdout.strip()


def read_current() -> tuple[int, int, int]:
    raw = VERSION_FILE.read_text(encoding="utf-8").strip()
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", raw)
    if not m:
        raise SystemExit(
            f"VERSION file must contain a bare MAJOR.MINOR.PATCH version, got: {raw!r}"
        )
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def latest_release_tag() -> str | None:
    """Return the highest ``vX.Y.Z`` tag, or None if there are none."""
    tags = _git("tag", "--list", "v[0-9]*.[0-9]*.[0-9]*", "--sort=-v:refname")
    for line in tags.splitlines():
        line = line.strip()
        if re.match(r"^v\d+\.\d+\.\d+$", line):
            return line
    return None


def _commit_messages_since(ref: str | None) -> list[str]:
    """Full commit messages (subject+body) since ref, newest first.

    Uses an ASCII record separator so multi-line bodies stay grouped.
    """
    rng = f"{ref}..HEAD" if ref else "HEAD"
    sep = "\x1e"
    raw = _git("log", rng, f"--format=%B{sep}")
    if not raw:
        return []
    return [chunk.strip() for chunk in raw.split(sep) if chunk.strip()]


def _classify(message: str) -> str | None:
    """Map a single commit message to a bump level, or None."""
    subject = message.splitlines()[0] if message else ""
    m = _SUBJECT_RE.match(subject)
    if m and m.group("bang"):
        return "major"
    if _BREAKING_BODY_RE.search(message):
        return "major"
    if not m:
        return None
    ctype = m.group("type").lower()
    if ctype == "feat":
        return "minor"
    if ctype in ("fix", "perf"):
        return "patch"
    return None


def bump_level_since(ref: str | None) -> str | None:
    if ref is None:
        # No release tag yet: don't invent a bump; the baseline tag is created
        # at the current VERSION by the workflow.
        return None
    highest: str | None = None
    for message in _commit_messages_since(ref):
        level = _classify(message)
        if _RANK[level] > _RANK[highest]:
            highest = level
    return highest


def apply_bump(cur: tuple[int, int, int], level: str | None) -> tuple[int, int, int]:
    major, minor, patch = cur
    if level == "major":
        return major + 1, 0, 0
    if level == "minor":
        return major, minor + 1, 0
    if level == "patch":
        return major, minor, patch + 1
    return cur


def fmt(v: tuple[int, int, int]) -> str:
    return f"{v[0]}.{v[1]}.{v[2]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["current", "next", "bump", "apply"])
    args = parser.parse_args(argv)

    current = read_current()
    tag = latest_release_tag()
    level = bump_level_since(tag)
    nxt = apply_bump(current, level)

    if args.command == "current":
        print(fmt(current))
    elif args.command == "bump":
        print(level or "none")
    elif args.command == "next":
        print(fmt(nxt))
    elif args.command == "apply":
        if nxt == current:
            print(f"No version change (current {fmt(current)}, last tag {tag or 'none'}).")
        else:
            VERSION_FILE.write_text(f"{fmt(nxt)}\n", encoding="utf-8")
            print(f"VERSION {fmt(current)} -> {fmt(nxt)} (bump: {level})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
