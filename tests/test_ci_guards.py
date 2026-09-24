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

#: The UI suite again, shuffled. Reports; never gates.
SHUFFLED_UI_JOB = "tests-ui-shuffled"

#: The job that turns the two halves' data files into one number.
COVERAGE_JOB = "coverage"

#: The one check a repository is likely to require by name in branch protection.
SUMMARY_JOB = "validation-summary"


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


def _without_comments(text: str) -> str:
    """``text`` with its ``#`` comment lines dropped.

    The job splitter hands a job every line up to the next job's key, so a
    block comment written above the *following* job -- and every ``#`` note
    inside a ``run:`` block -- reads as part of this one. A check on what a job
    *does* has to look past what it says about itself.
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


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

    ``develop`` is where work integrates, ``main`` is what releases, and
    ``staging`` is where a release is rehearsed -- ``develop`` merged in to get
    an installer built and verified without publishing anything. All three are
    pushed to only by merges, and all three must get a full run.
    """
    lines = _without_comments("\n".join(_trigger_block("push"))).splitlines()
    branches = [line.strip().lstrip("- ").strip() for line in lines]
    branches = [branch for branch in branches if branch and branch != "branches:"]
    assert sorted(branches) == ["develop", "main", "staging"]


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


def test_the_validation_summary_waits_for_the_tests_and_reads_their_result() -> None:
    """A failing test must block a merge even when only this check is required.

    Branch protection requires status checks one at a time, by name, so
    "Validation Summary" is the one a repository is likely to pick -- it reads
    as the whole verdict. While it listed neither test job in ``needs``, it did
    not wait for them and did not look at them: it went green beside a red test
    job, and the required check said the merge was fine. The workflow run was
    red the whole time, which is exactly what made it easy to miss.

    Listing them is not enough on its own -- ``if: always()`` means this job
    runs whatever they did -- so the result has to be read as well.
    """
    job = _without_comments(_job(SUMMARY_JOB))
    needs = re.search(r"needs:\s*\[([^\]]*)\]", job)
    assert needs is not None, f"`{SUMMARY_JOB}` declares no `needs:`"
    declared = {name.strip() for name in needs.group(1).split(",")}
    missing = {NON_UI_JOB, UI_JOB} - declared
    assert not missing, (
        f"`{SUMMARY_JOB}` does not wait for {sorted(missing)}. Required as a "
        "branch-protection check on its own, it would pass a PR whose tests failed."
    )
    for job_id in (NON_UI_JOB, UI_JOB):
        assert re.search(rf'needs\.{re.escape(job_id)}\.result[^\n]*!=\s*"success"', job), (
            f"`{SUMMARY_JOB}` waits for `{job_id}` but never fails on its "
            "result, and `if: always()` means it runs however that job ended."
        )


def test_ui_tests_never_run_in_parallel() -> None:
    """UI tests build real top-level windows; they share one process, one at a time."""
    ui_steps = [_main_run(UI_JOB), *_guard_steps(UI_JOB), *_named_steps(SHUFFLED_UI_JOB).values()]
    for step in ui_steps:
        assert not re.search(r"(^|\s)(-n|--numprocesses)(\s|=)", step), step


# ------------------------------------------------------------- order independence -------------------------------------------------------------
# tests/README.md asks authors to check that a shared-window file passes in any
# order, and for the length of the one-AppFrame-per-module refactor nothing
# enforced it. These pin the two halves of the answer: a job that actually
# shuffles, and the fact that it is not allowed to gate a pull request. A
# shuffled UI run finds real coupling intermittently, and an intermittent
# required check is one people learn to rerun rather than read.


def test_the_shuffled_ui_run_exists_and_actually_shuffles() -> None:
    steps = _without_comments("\n".join(_named_steps(SHUFFLED_UI_JOB).values()))
    assert re.search(
        r"pytest[^\n]*\s+tests/ui(\s|$|\s)", steps
    ), f"`{SHUFFLED_UI_JOB}` must run the tests/ui directory"
    assert re.search(r"(^|\s)-p\s+randomly(\s|$)", steps), (
        f"`{SHUFFLED_UI_JOB}` does not pass `-p randomly`, and pyproject.toml's "
        "addopts blocks the plugin by default -- so the job would run the UI "
        "suite a second time in exactly the same order as the job above."
    )


def test_the_default_order_is_the_file_order_everywhere_else() -> None:
    """A failure has to be reproducible from the command that produced it.

    pytest-randomly shuffles as soon as it is installed, and it is a dev
    dependency, so the block has to be in the config rather than on each
    gating command.
    """
    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    addopts = re.search(r"^addopts\s*=\s*\"([^\"]*)\"", config, flags=re.MULTILINE)
    assert addopts is not None, "pyproject.toml sets no pytest addopts"
    assert "-p no:randomly" in addopts.group(1), (
        "pytest-randomly is in requirements-dev.txt and shuffles by default. "
        "Without `-p no:randomly` in addopts, every local run and both gating "
        f"CI jobs reorder themselves, and only `{SHUFFLED_UI_JOB}` is meant to."
    )
    requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "pytest-randomly==" in requirements, (
        f"`{SHUFFLED_UI_JOB}` runs `-p randomly`, so the plugin has to be pinned "
        "where the test jobs install from."
    )


def test_the_shuffled_ui_run_never_gates_a_pull_request() -> None:
    job = _without_comments(_job(SHUFFLED_UI_JOB))
    condition = re.search(r"^    if:(.*)$", job, flags=re.MULTILINE)
    assert condition is not None, (
        f"`{SHUFFLED_UI_JOB}` has no `if:`, so it runs on every pull request. A "
        "shuffled UI run is intermittent by nature; gating on it teaches people "
        "to rerun a red check instead of reading it."
    )
    events = set(re.findall(r"'([a-z_]+)'", condition.group(1)))
    assert events == {"schedule", "workflow_dispatch"}, (
        f"`{SHUFFLED_UI_JOB}` should run on the schedule and on demand, not on "
        f"{sorted(events)}."
    )
    assert _trigger_block("schedule"), "ci.yml has no schedule for it to run on"
    assert SHUFFLED_UI_JOB not in _job(SUMMARY_JOB), (
        f"`{SUMMARY_JOB}` names `{SHUFFLED_UI_JOB}`. Waiting on a job that is "
        "skipped on every pull request would skip the summary with it, and the "
        "required check would never report at all."
    )


# ---------------------------------------------------------------- coverage ----------------------------------------------------------------
# pytest-cov has been pinned in requirements-dev.txt since before this split and
# was never passed to pytest: no report, no artifact, no number. These pin the
# three ways the wiring can come undone without anything going red -- a pytest
# run that stops measuring, a second run in the same job that overwrites the
# first's data instead of appending to it, and a combine job that reads only one
# half of a suite that runs as two.


@pytest.mark.parametrize("job_id", [NON_UI_JOB, UI_JOB])
def test_every_pytest_run_measures_coverage(job_id: str) -> None:
    """Both steps of both test jobs, or the combined number is silently partial."""
    for step in (*_guard_steps(job_id), _main_run(job_id)):
        assert re.search(r"(^|\s)--cov(\s|=)", _without_comments(step)), (
            f"`{job_id}` has a pytest step that does not pass --cov. Coverage is "
            "combined from every run of both jobs, so a step that stops "
            "measuring does not fail anything -- it just reports its files as "
            f"untested.\n{step}"
        )


@pytest.mark.parametrize("job_id", [NON_UI_JOB, UI_JOB])
def test_the_second_run_in_a_job_appends_instead_of_overwriting(job_id: str) -> None:
    """Two pytest runs, one ``.coverage`` file.

    The guard step runs first and writes the data file; the main run has to
    ``--cov-append`` onto it. Without that it starts a fresh file, and the
    guards' ~16 files silently report as uncovered -- which is exactly the
    failure mode of a design-system guard that runs but is not counted.
    """
    assert "--cov-append" in _without_comments(_main_run(job_id)), (
        f"`{job_id}`'s main pytest run must --cov-append onto the guard step's "
        "data file, or it overwrites it."
    )
    assert "--cov-append" not in _without_comments("".join(_guard_steps(job_id))), (
        f"`{job_id}`'s guard step runs first and owns the data file; appending "
        "there would carry a previous run's measurements into this one."
    )


@pytest.mark.parametrize("job_id", [NON_UI_JOB, UI_JOB])
def test_each_test_job_uploads_its_coverage_data(job_id: str) -> None:
    job = _without_comments(_job(job_id))
    assert "actions/upload-artifact" in job and "path: .coverage" in job, (
        f"`{job_id}` measures coverage but does not upload the data file, so "
        f"the `{COVERAGE_JOB}` job has nothing to combine."
    )
    assert "include-hidden-files: true" in job, (
        "`.coverage` is a dotfile and upload-artifact@v4 skips hidden files by "
        "default -- the upload would succeed and contain nothing."
    )


def test_the_coverage_job_combines_both_halves() -> None:
    """One number, from both jobs. Either half alone is a misleading figure."""
    job = _without_comments(_job(COVERAGE_JOB))
    needs = re.search(r"needs:\s*\[([^\]]*)\]", job)
    assert needs is not None, f"`{COVERAGE_JOB}` declares no `needs:`"
    assert sorted(name.strip() for name in needs.group(1).split(",")) == sorted(
        [NON_UI_JOB, UI_JOB]
    )
    assert "coverage combine" in job
    assert "coverage report" in job


def test_coverage_paths_are_stored_relative_so_the_two_halves_combine() -> None:
    """The test jobs run on Windows and the combine on Linux.

    ``coverage combine`` matches data files by the path each one recorded. With
    absolute paths a ``D:\\a\\...`` measurement and a ``/home/runner/...`` one
    are different files, and the combined report would show the whole app as
    untested rather than fail.
    """
    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.coverage.run]" in config, "coverage has no configuration to read"
    assert "relative_files = true" in config


def test_a_coverage_floor_belongs_on_the_combined_number_only() -> None:
    """Neither half of a suite that runs as two jobs may gate on the whole app.

    ``--cov-fail-under`` on ``tests-ui`` would measure every service the UI job
    never imports and fail a green run; on ``tests-non-ui`` it would do the same
    for every window. When a floor is set -- it is not yet, deliberately: see
    the comment above the ``coverage`` job -- it goes on the combined report.
    """
    for job_id in (NON_UI_JOB, UI_JOB):
        steps = _without_comments("\n".join(_named_steps(job_id).values()))
        assert "fail-under" not in steps, (
            f"`{job_id}` gates on its own partial coverage. The floor belongs on "
            f"the `{COVERAGE_JOB}` job, which reads both halves."
        )
    combined = _without_comments("\n".join(_named_steps(COVERAGE_JOB).values()))
    floors = re.findall(r"--fail-under[= ](\d+)", combined)
    assert len(floors) <= 1, "one floor, on one step"
    assert all(0 < int(floor) <= 100 for floor in floors)
