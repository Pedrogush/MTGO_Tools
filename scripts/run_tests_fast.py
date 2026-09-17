"""Run the whole test suite the fast way: non-UI tests in parallel, UI tests alongside.

    python scripts/run_tests_fast.py              # everything
    python scripts/run_tests_fast.py -x -q        # extra args go to both pytest runs
    python scripts/run_tests_fast.py --no-ui      # only the parallel non-UI half
    python scripts/run_tests_fast.py --ui-only    # only the serial UI half

It starts two ``pytest`` processes at once, the same split CI uses:

* ``pytest -n <workers> --ignore=tests/ui`` -- everything that does not build a
  real window, spread across cores with pytest-xdist;
* ``pytest tests/ui`` -- the wx UI tests, serially in one process, because they
  create real top-level windows.

The non-UI run streams to the console; the UI run's output is written to a log
and printed once it finishes. The exit code is non-zero if either run failed.

Plain ``pytest`` still runs the whole suite serially, exactly as before. Don't
launch the app, or a second UI run, while this runs: the UI tests need the
desktop to themselves, and the real-data guard fails the run if the app writes
to config/ or cache/ meanwhile.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _pytest_command() -> list[str]:
    """``pytest`` from the running interpreter's environment, invoked as CI invokes it.

    The console script rather than ``python -m pytest``: ``-m`` puts the working
    directory on ``sys.path``, which has hidden an import bug before.
    """
    scripts = Path(sys.executable).parent
    for name in ("pytest.exe", "pytest"):
        candidate = scripts / name
        if candidate.exists():
            return [str(candidate)]
    return [sys.executable, "-m", "pytest"]


def _default_workers() -> int:
    # Leave one core for the UI run going on alongside.
    return max(1, (os.cpu_count() or 2) - 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "-n",
        "--workers",
        type=int,
        default=_default_workers(),
        help="xdist workers for the non-UI run (default: CPU count - 1)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--no-ui", action="store_true", help="skip the UI tests")
    group.add_argument("--ui-only", action="store_true", help="run only the UI tests")
    args, pytest_args = parser.parse_known_args(argv)

    pytest = _pytest_command()
    started = time.monotonic()
    ui_process = None
    ui_log = None
    if not args.no_ui:
        ui_log = tempfile.NamedTemporaryFile(
            "w+", prefix="mtgo-ui-tests-", suffix=".log", delete=False, encoding="utf-8"
        )
        ui_process = subprocess.Popen(
            [*pytest, "tests/ui", *pytest_args],
            cwd=REPO_ROOT,
            stdout=ui_log,
            stderr=subprocess.STDOUT,
        )
        print(f"UI tests running in the background; log: {ui_log.name}", flush=True)

    non_ui_code = 0
    if not args.ui_only:
        non_ui_code = subprocess.call(
            [*pytest, "-n", str(args.workers), "--ignore=tests/ui", *pytest_args],
            cwd=REPO_ROOT,
        )

    ui_code = 0
    if ui_process is not None and ui_log is not None:
        if not args.ui_only:
            print("\nWaiting for the UI tests...", flush=True)
        ui_code = ui_process.wait()
        ui_log.seek(0)
        print("\n===== UI tests (tests/ui) =====")
        print(ui_log.read())
        ui_log.close()
        os.unlink(ui_log.name)

    elapsed = time.monotonic() - started
    print(f"non-UI exit {non_ui_code}, UI exit {ui_code}, {elapsed:.0f}s wall")
    return non_ui_code or ui_code


if __name__ == "__main__":
    raise SystemExit(main())
