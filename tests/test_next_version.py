"""Tests for the release-version computation.

This logic has been wrong twice in ways that only showed up in the published
release history -- a feature that shipped as a patch, and a `main` that went
backwards from 1.4.0 to 1.3.3 -- so the rules are pinned here rather than left
to be re-read out of a workflow log.

The pure functions (``classify``, ``apply_bump``, ``select_keep``) are exercised
directly. The git-backed ones are exercised against real throwaway repositories
built in ``tmp_path``, because what they actually have to get right is how git
orders and ranges commits, which a mock would simply assert away.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import next_version as nv
from scripts.prune_releases import select_keep


# --------------------------------------------------------------- classify ---
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("fix: correct wallet totals", "patch"),
        ("perf(images): stream the bulk file", "patch"),
        # Inference never proposes more than a patch: a minor is opted into.
        ("feat: add mulligan tracker", "patch"),
        ("feat(ui): rebuild the charts", "patch"),
        ("refactor(theme): add the token layer", None),
        ("chore: bump a pin", None),
        ("docs: explain versioning", None),
        ("ci(release): publish on merge", None),
        ("Merge pull request #997 from Pedrogush/fix/pile-view", None),
        ("not a conventional subject at all", None),
        # Breaking is an explicit author signal, so it still reaches major.
        ("feat!: rewrite deck storage", "major"),
        ("fix(deck)!: drop the legacy format", "major"),
        ("refactor: rework storage\n\nBREAKING CHANGE: deck files move", "major"),
    ],
)
def test_classify_infers_at_most_a_patch(message: str, expected: str | None) -> None:
    assert nv.classify(message) == expected


@pytest.mark.parametrize("level", ["major", "minor", "patch"])
def test_version_bump_trailer_decides(level: str) -> None:
    """The marker wins over whatever the subject would have implied."""
    assert nv.classify(f"feat: land the redesign\n\nVersion-Bump: {level}") == level
    assert nv.classify(f"chore: no user-facing change\n\nVersion-Bump: {level}") == level


def test_version_bump_trailer_is_case_insensitive_and_trailer_only() -> None:
    assert nv.classify("fix: x\n\nversion-bump: MINOR") == "minor"
    # Prose that merely mentions the marker mid-line must not trigger it.
    assert nv.classify("fix: mention Version-Bump: minor inline") == "patch"


def test_version_bump_trailer_holds_a_feat_down_to_a_patch() -> None:
    """The case the UI redesign needed: one step of a feature, not the feature."""
    assert nv.classify("feat(ui): own-drawn text input borders\n\nVersion-Bump: patch") == "patch"


def test_release_as_pin_is_read_from_a_trailer() -> None:
    assert nv.explicit_pin("chore: cut the milestone\n\nRelease-As: 2.0.0") == (2, 0, 0)
    assert nv.explicit_pin("chore: cut the milestone\n\nRelease-As: v2.4.1") == (2, 4, 1)
    assert nv.explicit_pin("fix: ordinary change") is None


# -------------------------------------------------------------- apply_bump ---
@pytest.mark.parametrize(
    ("current", "level", "expected"),
    [
        ((1, 1, 5), "patch", (1, 1, 6)),
        ((1, 1, 5), "minor", (1, 2, 0)),
        ((1, 1, 5), "major", (2, 0, 0)),
        ((1, 1, 5), None, (1, 1, 5)),
    ],
)
def test_apply_bump(current, level, expected) -> None:
    assert nv.apply_bump(current, level) == expected


# ------------------------------------------------------------ git-backed ---
def _run(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway git repo that ``next_version`` operates on."""
    _run(tmp_path, "init", "-q", "-b", "main")
    _run(tmp_path, "config", "user.email", "test@example.com")
    _run(tmp_path, "config", "user.name", "test")
    (tmp_path / "VERSION").write_text("1.1.5\n", encoding="utf-8")
    _run(tmp_path, "add", "VERSION")
    _run(tmp_path, "commit", "-q", "-m", "chore: init")
    monkeypatch.setattr(nv, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(nv, "VERSION_FILE", tmp_path / "VERSION")
    return tmp_path


def _commit(repo: Path, message: str) -> None:
    marker = repo / "file.txt"
    marker.write_text(message, encoding="utf-8")
    _run(repo, "add", "file.txt")
    _run(repo, "commit", "-q", "-m", message)


def _tag(repo: Path, tag: str) -> None:
    _run(repo, "tag", "-a", tag, "-m", tag)


def test_base_comes_from_the_newest_tag_not_the_version_file(repo: Path) -> None:
    """A VERSION file that disagrees with the tags must not set the base.

    This is the regression that let `main` sit at 1.3.6 while the release history
    said something else entirely.
    """
    _tag(repo, "v1.1.5")
    (repo / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    assert nv.base_version() == (1, 1, 5)


def test_latest_tag_is_by_version_not_by_date(repo: Path) -> None:
    """v1.10.0 outranks v1.9.0, and a late-cut old tag doesn't become 'latest'."""
    _tag(repo, "v1.9.0")
    _commit(repo, "fix: something")
    _tag(repo, "v1.10.0")
    _commit(repo, "fix: something else")
    _tag(repo, "v1.2.0")  # cut out of order, deliberately
    assert nv.latest_release_tag() == "v1.10.0"


def test_only_commits_since_the_tag_count(repo: Path) -> None:
    _commit(repo, "feat: shipped long ago\n\nVersion-Bump: major")
    _tag(repo, "v1.1.5")
    _commit(repo, "fix: landed after the release")
    # The pre-tag major is out of range, so this is an ordinary patch.
    assert nv.bump_level() == "patch"
    assert nv.next_version() == (1, 1, 6)


def test_nothing_release_worthy_means_no_bump(repo: Path) -> None:
    _tag(repo, "v1.1.5")
    _commit(repo, "docs: explain the thing")
    _commit(repo, "chore: tidy up")
    assert nv.bump_level() is None
    assert nv.next_version() == (1, 1, 5)


def test_ten_feature_steps_stay_a_patch_until_one_claims_the_minor(repo: Path) -> None:
    """The UI-redesign shape: ten `feat` PRs, one feature, one minor bump."""
    _tag(repo, "v1.0.4")
    for phase in range(9):
        _commit(repo, f"feat(ui): redesign phase {phase}\n\nVersion-Bump: patch")
    assert nv.next_version() == (1, 0, 5)

    _commit(repo, "feat(ui): land the full redesign\n\nVersion-Bump: minor")
    assert nv.bump_level() == "minor"
    assert nv.next_version() == (1, 1, 0)


def test_largest_signal_in_the_range_wins(repo: Path) -> None:
    _tag(repo, "v1.1.5")
    _commit(repo, "fix: a small thing")
    _commit(repo, "feat: a real feature\n\nVersion-Bump: minor")
    _commit(repo, "fix: another small thing")
    assert nv.next_version() == (1, 2, 0)


def test_release_as_pin_overrides_the_computed_bump(repo: Path) -> None:
    _tag(repo, "v1.1.5")
    _commit(repo, "feat: milestone\n\nRelease-As: 2.0.0")
    _commit(repo, "fix: a follow-up")
    assert nv.bump_level() == "patch"  # what inference alone would have said
    assert nv.next_version() == (2, 0, 0)  # what the pin says


def test_no_tags_at_all_falls_back_to_the_version_file(repo: Path) -> None:
    _commit(repo, "fix: the very first fix")
    assert nv.base_version() == (1, 1, 5)
    assert nv.next_version() == (1, 1, 6)


def test_apply_writes_the_computed_version(repo: Path) -> None:
    _tag(repo, "v1.1.5")
    _commit(repo, "fix: something worth shipping")
    nv.main(["apply"])
    assert (repo / "VERSION").read_text(encoding="utf-8").strip() == "1.1.6"


# ------------------------------------------------------------- retention ---
def test_select_keep_keeps_the_newest_patch_and_the_baseline_of_each_line() -> None:
    """Two per line: the newest patch, and the ``x.y.0`` it started from.

    The middle patches go -- 1.1.5 and 1.0.4/1.0.2 are superseded builds of a
    line whose newest is already kept.
    """
    versions = [(1, 1, 6), (1, 1, 5), (1, 1, 0), (1, 0, 5), (1, 0, 4), (1, 0, 2), (1, 0, 0)]
    assert select_keep(versions) == [(1, 1, 6), (1, 1, 0), (1, 0, 5), (1, 0, 0)]


def test_select_keep_keeps_an_upgrade_path_within_a_line() -> None:
    """The case that motivated the rule (#1003 -> v1.2.1).

    Under the newest-patch-only rule v1.2.0 was deleted the instant v1.2.1
    published, so there was no published release to upgrade *from* and the
    in-app updater could not be exercised end to end.
    """
    assert select_keep([(1, 2, 1), (1, 2, 0), (1, 1, 8)]) == [(1, 2, 1), (1, 2, 0), (1, 1, 8)]


def test_select_keep_does_not_double_count_a_line_that_is_only_a_baseline() -> None:
    """A line whose newest patch *is* its ``.0`` contributes one release, not two."""
    assert select_keep([(1, 3, 0), (1, 2, 4), (1, 2, 0)]) == [(1, 3, 0), (1, 2, 4), (1, 2, 0)]


def test_select_keep_skips_a_baseline_that_was_never_published() -> None:
    """A line that never shipped a ``.0`` just does not contribute one."""
    assert select_keep([(1, 4, 3), (1, 4, 1)]) == [(1, 4, 3)]


def test_select_keep_caps_the_total() -> None:
    versions = [(1, minor, 0) for minor in range(15)]
    kept = select_keep(versions, max_releases=10)
    assert len(kept) == 10
    assert kept[0] == (1, 14, 0)  # newest survives
    assert kept[-1] == (1, 5, 0)  # the oldest five are dropped


def test_select_keep_is_ordered_newest_first() -> None:
    kept = select_keep([(1, 0, 0), (2, 1, 3), (1, 4, 2)])
    assert kept == [(2, 1, 3), (1, 4, 2), (1, 0, 0)]


def test_the_cap_still_wins_over_a_baseline() -> None:
    """``--max`` is a hard ceiling, applied last and newest-first.

    A repo with more lines than the cap can lose a ``.0`` off the *oldest* end.
    That is the intended precedence: the cap bounds storage, and the lines it
    reaches are ones nobody is upgrading from any more.
    """
    versions = [(1, 0, 0), (1, 0, 1), (1, 1, 0), (1, 1, 1)]
    assert select_keep(versions, max_releases=3) == [(1, 1, 1), (1, 1, 0), (1, 0, 1)]
