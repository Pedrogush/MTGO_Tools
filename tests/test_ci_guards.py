"""The regression guards must actually run in CI, on the PRs that need them.

Two failures this pins, both found in phase 9 of issue #962:

1. **CI never ran on the redesign.** ``ci.yml``'s ``pull_request`` trigger
   carried ``branches: [main]``. That filters on the PR's *base* branch, so a
   stack of PRs targeting each other -- which is how all thirteen phases of the
   redesign were delivered -- matched nothing. Thirteen PRs, ~20k lines, and the
   only workflow that ran on any of them was the version bumper. The guards
   existed; CI simply never called them.

2. **A guard list is a list.** The ``Design-system guards`` step names its files
   explicitly, so renaming or deleting one leaves the step quietly running fewer
   tests than it says it does.

Parsed as text rather than as YAML on purpose: PyYAML is not a dependency of
this project and adding one so a test can read a workflow file would be a poor
trade.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"

GUARD_STEP = "Design-system guards"


def _workflow() -> str:
    assert CI.exists(), f"{CI} is missing"
    return CI.read_text(encoding="utf-8")


def _guard_paths() -> list[str]:
    """The test paths listed in the guard step's ``run:`` block."""
    text = _workflow()
    start = text.index(GUARD_STEP)
    # The block ends at the next step (a "- name:" at the same indentation).
    end = text.index("\n      - name:", start)
    return re.findall(r"(tests/\S+\.py)", text[start:end])


def _trigger_block(name: str) -> list[str]:
    """The indented lines belonging to a top-level ``on:`` key, e.g. ``push``."""
    text = _workflow()
    lines = text[text.index("\non:") : text.index("\njobs:")].splitlines()
    for i, line in enumerate(lines):
        if line.strip() == f"{name}:" and line.startswith("  ") and not line.startswith("   "):
            body: list[str] = []
            for follow in lines[i + 1 :]:
                if follow.strip() and not follow.startswith("    "):
                    break
                body.append(follow)
            return body
    raise AssertionError(f"ci.yml has no `{name}:` trigger at all")


def test_push_trigger_is_still_limited_to_main() -> None:
    """The other half of the pair -- unfiltering push would run CI on every branch."""
    assert any("main" in line for line in _trigger_block("push"))


def test_pull_request_trigger_is_not_filtered_by_base_branch() -> None:
    body = "\n".join(_trigger_block("pull_request"))
    assert "branches:" not in body, (
        "ci.yml filters pull_request by base branch again. `branches:` on a "
        "pull_request trigger matches the PR's BASE, so a stacked PR (base "
        "`redesign/phase-7`, not `main`) runs no CI at all -- which is how all "
        "thirteen PRs of the #962 redesign shipped without the guards ever "
        "running. Push is filtered to main; pull_request must not be."
    )


def test_the_guard_step_exists_and_is_not_empty() -> None:
    assert GUARD_STEP in _workflow(), (
        f"ci.yml no longer has a '{GUARD_STEP}' step. The full pytest run still "
        "covers these files, but nothing then names a design-system regression "
        "as one."
    )
    assert len(_guard_paths()) >= 15, "the guard step lists suspiciously few files"


@pytest.mark.parametrize("rel", _guard_paths())
def test_every_guard_the_workflow_names_exists(rel: str) -> None:
    assert (ROOT / rel).exists(), (
        f"ci.yml's '{GUARD_STEP}' step runs {rel}, which does not exist. pytest "
        "exits 4 on a missing path, so this fails loudly rather than silently -- "
        "but fix the list, do not delete the entry without a replacement."
    )


def test_the_contrast_guard_is_specifically_named() -> None:
    """Issue #962's acceptance criterion names this test in particular."""
    assert "tests/test_theme_contrast.py" in _guard_paths(), (
        "test_theme_contrast.py is the regression guard for the whole redesign: "
        "every foreground/background pair in the app against WCAG AA, plus the "
        "chart palette against colour-vision deficiency. It must run in CI."
    )
