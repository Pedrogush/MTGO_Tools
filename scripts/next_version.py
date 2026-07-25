#!/usr/bin/env python3
"""Derive the project's semantic version from conventional-commit history.

Single source of truth: the repo-root ``VERSION`` file (bare ``MAJOR.MINOR.PATCH``).
Version numbers are never hand-picked; they are computed from
[Conventional Commit](https://www.conventionalcommits.org) messages:

    <type>!: ...            -> MAJOR   (also any body with "BREAKING CHANGE")
    feat: ...               -> MINOR
    fix: ... / perf: ...    -> PATCH
    anything else           -> no release-worthy change

Precedence is major > minor > patch.

Two ways to pick the commit range and base version:

  * ``--base REF`` (the model used by CI): the base is the PR's target branch.
    The base version is ``VERSION`` **as it exists at REF**, and the bump is the
    largest applicable one across commits in ``REF..HEAD``. This is how a PR's
    version is computed relative to what it will merge into.

  * no ``--base`` (handy locally): the base version is the current working-tree
    ``VERSION`` and the range is "commits since the latest ``vX.Y.Z`` tag" (or
    all history if there are no tags).

Usage:
    scripts/next_version.py current                 # current VERSION (working tree)
    scripts/next_version.py bump   [--base REF]     # major | minor | patch | none
    scripts/next_version.py next   [--base REF]     # the computed next version
    scripts/next_version.py apply  [--base REF]     # write the next version to VERSION

Dependency-free (stdlib + git) so it runs identically locally and in CI.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO_ROOT / "VERSION"

Version = tuple[int, int, int]

# type(scope)!: subject  ->  captures type and the optional breaking "!"
_SUBJECT_RE = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\([^)]*\))?(?P<bang>!)?:", re.IGNORECASE)
_BREAKING_BODY_RE = re.compile(r"^BREAKING[ -]CHANGE:", re.IGNORECASE | re.MULTILINE)
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

# Order matters: index in this map is the bump rank (higher = bigger bump).
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


def _parse(raw: str) -> Version:
    m = _VERSION_RE.match(raw.strip())
    if not m:
        raise SystemExit(f"Expected a bare MAJOR.MINOR.PATCH version, got: {raw!r}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def read_current() -> Version:
    return _parse(VERSION_FILE.read_text(encoding="utf-8"))


def version_at_ref(ref: str) -> Version:
    """The VERSION recorded at a git ref; falls back to the working tree."""
    raw = _git("show", f"{ref}:VERSION")
    if raw:
        return _parse(raw)
    return read_current()


def latest_release_tag() -> str | None:
    """The highest ``vX.Y.Z`` tag, or None if there are none."""
    tags = _git("tag", "--list", "v[0-9]*.[0-9]*.[0-9]*", "--sort=-v:refname")
    for line in tags.splitlines():
        line = line.strip()
        if re.match(r"^v\d+\.\d+\.\d+$", line):
            return line
    return None


def _commit_messages(rng: str) -> list[str]:
    """Full commit messages (subject+body) for a range, newest first.

    Uses an ASCII record separator so multi-line bodies stay grouped.
    """
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


def bump_level(base: str | None) -> str | None:
    """Largest bump implied by commits in ``base..HEAD`` (or since the last tag).

    ``base`` is an explicit ref (PR target branch) when given; otherwise we use
    the latest release tag, and if there is none there is no release yet.
    """
    if base:
        rng = f"{base}..HEAD"
    else:
        tag = latest_release_tag()
        if tag is None:
            return None
        rng = f"{tag}..HEAD"
    highest: str | None = None
    for message in _commit_messages(rng):
        level = _classify(message)
        if _RANK[level] > _RANK[highest]:
            highest = level
    return highest


def apply_bump(cur: Version, level: str | None) -> Version:
    major, minor, patch = cur
    if level == "major":
        return major + 1, 0, 0
    if level == "minor":
        return major, minor + 1, 0
    if level == "patch":
        return major, minor, patch + 1
    return cur


def fmt(v: Version) -> str:
    return f"{v[0]}.{v[1]}.{v[2]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["current", "bump", "next", "apply"])
    parser.add_argument(
        "--base",
        metavar="REF",
        help="Target branch/ref to compute against (PR mode). Base version is "
        "VERSION at REF; bump is computed across REF..HEAD.",
    )
    args = parser.parse_args(argv)

    base_version = version_at_ref(args.base) if args.base else read_current()
    level = bump_level(args.base)
    nxt = apply_bump(base_version, level)

    if args.command == "current":
        print(fmt(read_current()))
    elif args.command == "bump":
        print(level or "none")
    elif args.command == "next":
        print(fmt(nxt))
    elif args.command == "apply":
        prev = read_current()
        if nxt == prev:
            print(f"No version change (stays {fmt(nxt)}).")
        else:
            VERSION_FILE.write_text(f"{fmt(nxt)}\n", encoding="utf-8")
            print(f"VERSION {fmt(prev)} -> {fmt(nxt)} (bump: {level})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
