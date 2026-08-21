#!/usr/bin/env python3
"""Derive the project's next release version from what has landed on ``main``.

Single source of truth: the repo-root ``VERSION`` file (bare ``MAJOR.MINOR.PATCH``).
Version numbers are never hand-picked; they are computed **after merge**, from the
commits that have landed since the last release tag.

Why after merge (docs/VERSIONING.md has the full story): the number a change
deserves depends on everything that shipped alongside it, and that set is only
final once the merge lands. Computing it on a PR branch meant pinning a number
against a base that then moved, which is how ``main`` once went *backwards* from
1.4.0 to 1.3.3.

The range and the base
----------------------
The base version is read from the newest ``vX.Y.Z`` **tag**, not from the
``VERSION`` file, and the commit range is ``<that tag>..HEAD``. Tags are what
actually shipped, so they cannot drift the way a file on a branch can. With no
tags at all, the ``VERSION`` file is the base and all history is in range.

How the level is chosen
-----------------------
Automation on its own only ever proposes a **patch**. A minor or a major is a
deliberate act, because "is this one feature or ten steps of one feature?" is a
judgement no commit parser can make -- the UI redesign landed as ten PRs, each
carrying ``feat(ui):`` commits, and inference turned one feature into three
minor bumps.

So an explicit marker decides, and inference only fills in the floor:

    Release-As: 2.4.0            -> exactly that version, overriding everything
    Version-Bump: major|minor|patch
    <type>!: ...  /  BREAKING CHANGE:   -> major
    feat: / fix: / perf: ...     -> patch
    refactor, chore, docs, test, style, ci, merges, ...  -> no release

Markers are git trailers, so they go on their own line in any commit in the
range (a PR's own commit, or the merge commit's message). The largest signal in
the range wins, with an explicit marker outranking inference at the same level.
There is deliberately no "suppress" marker: anything that isn't a
``feat``/``fix``/``perf`` already produces no release, and a ``fix:`` that
landed on ``main`` is a fix users should be able to install.

Usage:
    scripts/next_version.py current              # what VERSION currently says
    scripts/next_version.py base                 # version of the newest release tag
    scripts/next_version.py bump  [--since REF]  # major | minor | patch | none
    scripts/next_version.py next  [--since REF]  # the version this release should carry
    scripts/next_version.py apply [--since REF]  # write that version into VERSION

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

# Explicit markers. Both are git trailers: own line, anywhere in the message.
_BUMP_TRAILER_RE = re.compile(
    r"^Version-Bump:[ \t]*(?P<level>major|minor|patch)[ \t]*$", re.IGNORECASE | re.MULTILINE
)
_RELEASE_AS_RE = re.compile(
    r"^Release-As:[ \t]*v?(?P<version>\d+\.\d+\.\d+)[ \t]*$", re.IGNORECASE | re.MULTILINE
)

# Order matters: index in this map is the bump rank (higher = bigger bump).
_RANK = {None: 0, "patch": 1, "minor": 2, "major": 3}

# Commit types that, absent an explicit marker, are worth shipping at all.
_RELEASE_WORTHY_TYPES = ("feat", "fix", "perf")


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


def latest_release_tag() -> str | None:
    """The highest ``vX.Y.Z`` tag, or None if there are none.

    Sorted by version, not by date: tags are the release record, and a release
    cut out of chronological order must not change what "latest" means.
    """
    tags = _git("tag", "--list", "v[0-9]*.[0-9]*.[0-9]*", "--sort=-v:refname")
    for line in tags.splitlines():
        line = line.strip()
        if re.match(r"^v\d+\.\d+\.\d+$", line):
            return line
    return None


def base_version(since: str | None = None) -> Version:
    """The version this release builds on: the newest release tag's number.

    Falls back to the ``VERSION`` file when the repo has no release tags yet,
    which is only true before the first release.
    """
    tag = since or latest_release_tag()
    if tag is None:
        return read_current()
    if _VERSION_RE.match(tag.lstrip("vV")):
        return _parse(tag.lstrip("vV"))
    # An explicit --since that isn't a version tag (a SHA, say): the range is
    # meaningful but carries no number, so the file is the only base available.
    return read_current()


def _commit_messages(rng: str) -> list[str]:
    """Full commit messages (subject+body) for a range, newest first.

    Uses an ASCII record separator so multi-line bodies stay grouped.
    """
    sep = "\x1e"
    raw = _git("log", rng, f"--format=%B{sep}")
    if not raw:
        return []
    return [chunk.strip() for chunk in raw.split(sep) if chunk.strip()]


def explicit_pin(message: str) -> Version | None:
    """``Release-As: X.Y.Z`` in a commit message, if present."""
    m = _RELEASE_AS_RE.search(message)
    return _parse(m.group("version")) if m else None


def classify(message: str) -> str | None:
    """Map a single commit message to a bump level, or None.

    An explicit ``Version-Bump:`` trailer wins over what the subject implies, so
    a ``feat:`` that is one step of a larger feature can be held at ``patch``
    and the PR that completes it can carry the ``minor``.
    """
    marker = _BUMP_TRAILER_RE.search(message)
    if marker:
        return marker.group("level").lower()
    subject = message.splitlines()[0] if message else ""
    m = _SUBJECT_RE.match(subject)
    if m and m.group("bang"):
        return "major"
    if _BREAKING_BODY_RE.search(message):
        return "major"
    if not m:
        return None
    # Inference never proposes more than a patch; minors and majors are opted
    # into with a marker. See the module docstring for why.
    return "patch" if m.group("type").lower() in _RELEASE_WORTHY_TYPES else None


def _range(since: str | None) -> str:
    tag = since or latest_release_tag()
    return f"{tag}..HEAD" if tag else "HEAD"


def bump_level(since: str | None = None) -> str | None:
    """Largest bump implied by the commits since the last release tag."""
    highest: str | None = None
    for message in _commit_messages(_range(since)):
        level = classify(message)
        if _RANK[level] > _RANK[highest]:
            highest = level
    return highest


def pinned_version(since: str | None = None) -> Version | None:
    """The newest ``Release-As:`` pin in range, if any commit carries one."""
    for message in _commit_messages(_range(since)):  # newest first
        pin = explicit_pin(message)
        if pin is not None:
            return pin
    return None


def apply_bump(cur: Version, level: str | None) -> Version:
    major, minor, patch = cur
    if level == "major":
        return major + 1, 0, 0
    if level == "minor":
        return major, minor + 1, 0
    if level == "patch":
        return major, minor, patch + 1
    return cur


def next_version(since: str | None = None) -> Version:
    """The version this release should carry, pin and markers accounted for."""
    pin = pinned_version(since)
    if pin is not None:
        return pin
    return apply_bump(base_version(since), bump_level(since))


def fmt(v: Version) -> str:
    return f"{v[0]}.{v[1]}.{v[2]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["current", "base", "bump", "next", "apply"])
    parser.add_argument(
        "--since",
        metavar="REF",
        help="Range base to compute against (default: the newest vX.Y.Z tag).",
    )
    args = parser.parse_args(argv)

    if args.command == "current":
        print(fmt(read_current()))
        return 0
    if args.command == "base":
        print(fmt(base_version(args.since)))
        return 0
    if args.command == "bump":
        print("pinned" if pinned_version(args.since) else (bump_level(args.since) or "none"))
        return 0

    nxt = next_version(args.since)
    if args.command == "next":
        print(fmt(nxt))
    elif args.command == "apply":
        prev = read_current()
        if nxt == prev:
            print(f"No version change (stays {fmt(nxt)}).")
        else:
            VERSION_FILE.write_text(f"{fmt(nxt)}\n", encoding="utf-8")
            print(f"VERSION {fmt(prev)} -> {fmt(nxt)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
