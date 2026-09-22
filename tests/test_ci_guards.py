"""The regression guards must actually run in CI, on the PRs that need them.

Two failures this pins, both found in phase 9 of issue #962:

1. **CI never ran on the redesign.** ``ci.yml``'s ``pull_request`` trigger
   carried ``branches: [main]``. That filters on the PR's *base* branch, so a
   stack of PRs targeting each other -- which is how all thirteen phases of the
   redesign were delivered -- matched nothing. Thirteen PRs, ~20k lines, and the
   only workflow that ran on any of them was the version bumper. The guards
   existed; CI simply never called them.

2. **A guard list is a list.** The ``Design-system guards`` steps name their
   files explicitly, so renaming or deleting one leaves a step quietly running
   fewer tests than it says it does.

And one the test-suite split introduced: the suite runs as two jobs (non-UI
tests in parallel, UI tests serially), each running its guard files in a named
step first and then everything else with those files ``--ignore``'d. Two hand
written lists per job are exactly the kind that drift, and the failure is
silent either way -- a file missing from the ignores runs twice, a file ignored
but not guarded never runs at all.

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

#: The two jobs that together run the whole suite.
NON_UI_JOB = "tests-non-ui"
UI_JOB = "tests-ui"


def _workflow() -> str:
    assert CI.exists(), f"{CI} is missing"
    return CI.read_text(encoding="utf-8")


def _jobs() -> dict[str, str]:
    """Each job's text, keyed by job id (the two-space-indented keys under ``jobs:``)."""
    text = _workflow()
    body = text[text.index("\njobs:") :]
    heads = list(re.finditer(r"^  ([A-Za-z0-9_-]+):[ \t]*$", body, flags=re.MULTILINE))
    return {
        head.group(1): body[head.end() : heads[i + 1].start() if i + 1 < len(heads) else None]
        for i, head in enumerate(heads)
    }


def _job(job_id: str) -> str:
    jobs = _jobs()
    assert job_id in jobs, f"ci.yml has no `{job_id}` job; it has {sorted(jobs)}"
    return jobs[job_id]


def _named_steps(job_id: str) -> dict[str, str]:
    """Each named step of a job, keyed by its name."""
    steps: dict[str, str] = {}
    for chunk in re.split(r"^      - ", _job(job_id), flags=re.MULTILINE)[1:]:
        first_line = chunk.splitlines()[0]
        if first_line.startswith("name:"):
            steps[first_line[len("name:") :].strip()] = chunk
    return steps


def _guard_steps(job_id: str) -> list[str]:
    return [text for name, text in _named_steps(job_id).items() if name.startswith(GUARD_STEP)]


def _guard_paths_of(job_id: str) -> list[str]:
    """The test paths the job's guard step runs."""
    return [path for step in _guard_steps(job_id) for path in re.findall(r"(tests/\S+\.py)", step)]


def _guard_paths() -> list[str]:
    """The test paths listed in every guard step's ``run:`` block."""
    return _guard_paths_of(NON_UI_JOB) + _guard_paths_of(UI_JOB)


def _main_run(job_id: str) -> str:
    """The job's full-suite pytest step: the one that is not the guard step."""
    runs = [
        text
        for name, text in _named_steps(job_id).items()
        if name.startswith("Run ") and "pytest" in text
    ]
    assert len(runs) == 1, f"`{job_id}` should have exactly one `Run ...` pytest step"
    return runs[0]


def _ignored(job_id: str) -> list[str]:
    return re.findall(r"--ignore=(\S+)", _main_run(job_id))


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


def test_push_trigger_is_limited_to_the_long_lived_branches() -> None:
    """The other half of the pair -- unfiltering push would run CI on every branch.

    ``develop`` is where work integrates and ``main`` is what releases; both
    are pushed to only by merges, and both must get a full run.
    """
    branches = [line.strip().lstrip("- ").strip() for line in _trigger_block("push")]
    branches = [branch for branch in branches if branch and branch != "branches:"]
    assert sorted(branches) == ["develop", "main"]


def test_pull_request_trigger_is_not_filtered_by_base_branch() -> None:
    body = "\n".join(_trigger_block("pull_request"))
    assert "branches:" not in body, (
        "ci.yml filters pull_request by base branch again. `branches:` on a "
        "pull_request trigger matches the PR's BASE, so a stacked PR (base "
        "`redesign/phase-7`, not `main`) runs no CI at all -- which is how all "
        "thirteen PRs of the #962 redesign shipped without the guards ever "
        "running. Push is filtered to main/develop; pull_request must not be."
    )


def test_the_guard_step_exists_and_is_not_empty() -> None:
    for job_id in (NON_UI_JOB, UI_JOB):
        assert len(_guard_steps(job_id)) == 1, (
            f"`{job_id}` no longer has a '{GUARD_STEP}' step. The full pytest run "
            "still covers these files, but nothing then names a design-system "
            "regression as one."
        )
    assert len(_guard_paths()) >= 15, "the guard steps list suspiciously few files"


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


@pytest.mark.parametrize("job_id", [NON_UI_JOB, UI_JOB])
def test_each_guard_file_runs_exactly_once(job_id: str) -> None:
    """The main run skips exactly the files the guard step already ran.

    A guard file missing from the ignores runs twice (the duplication this split
    removed); a file ignored but not guarded runs nowhere.
    """
    guarded = sorted(_guard_paths_of(job_id))
    ignored = sorted(path for path in _ignored(job_id) if path != "tests/ui")
    assert ignored == guarded, (
        f"`{job_id}`: the `Run ...` step's --ignore list and the '{GUARD_STEP}' "
        f"step's file list must be the same set.\n  only guarded: "
        f"{sorted(set(guarded) - set(ignored))}\n  only ignored: "
        f"{sorted(set(ignored) - set(guarded))}"
    )


def test_the_two_test_jobs_cover_the_whole_suite_between_them() -> None:
    """Non-UI runs ``tests/`` minus ``tests/ui``; UI runs ``tests/ui``; guards sit on their side."""
    assert "tests/ui" in _ignored(NON_UI_JOB)
    assert re.search(
        r"pytest[^\n]*\s+tests/ui(\s|$)", _main_run(UI_JOB)
    ), f"`{UI_JOB}` must run the tests/ui directory"
    assert all(not path.startswith("tests/ui/") for path in _guard_paths_of(NON_UI_JOB))
    assert all(path.startswith("tests/ui/") for path in _guard_paths_of(UI_JOB))


def test_ui_tests_never_run_in_parallel() -> None:
    """UI tests build real top-level windows; they share one process, one at a time."""
    ui_steps = [_main_run(UI_JOB), *_guard_steps(UI_JOB)]
    for step in ui_steps:
        assert not re.search(r"(^|\s)(-n|--numprocesses)(\s|=)", step), step
