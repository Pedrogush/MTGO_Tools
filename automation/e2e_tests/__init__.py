"""
End-to-end UI regression tests for MTGO Tools.

These tests run against the live application and cover:
- App launch / connectivity
- Deck builder: add/subtract cards to/from mainboard and sideboard
- Scrollbar persistence after zone modifications
- Mana symbol rendering in the builder search results
- Button enablement (copy, save)
- Sub-widget windows opening (opponent tracker, match history, etc.)
- Card face image loading in the deck zones

Usage:
    # 1. Start the app with automation enabled (Windows):
    cmd.exe /c "start python C:\\Users\\Pedro\\Documents\\GitHub\\mtgo_tools\\main.py --automation"

    # 2. Wait for the server to come up, then run:
    python -m automation.e2e_tests

    # Or run a specific test group:
    python -m automation.e2e_tests --only builder
    python -m automation.e2e_tests --only scrollbar
    python -m automation.e2e_tests --only mana
    python -m automation.e2e_tests --only buttons
    python -m automation.e2e_tests --only widgets
    python -m automation.e2e_tests --only images
    python -m automation.e2e_tests --only golden
    python -m automation.e2e_tests --only launch

Convention:
  When a UI bug is reproduced via the automation CLI, add a test to the
  relevant module in automation/e2e_tests/ that replicates the same command
  sequence so the fix can be verified automatically.
"""

from __future__ import annotations

import argparse
import sys

from automation.client import AutomationClient
from automation.e2e_tests.common import E2ETestRunner
from automation.e2e_tests.test_builder import ALL_TESTS as BUILDER_TESTS
from automation.e2e_tests.test_buttons import ALL_TESTS as BUTTON_TESTS
from automation.e2e_tests.test_golden import ALL_TESTS as GOLDEN_TESTS
from automation.e2e_tests.test_images import ALL_TESTS as IMAGE_TESTS
from automation.e2e_tests.test_launch import ALL_TESTS as LAUNCH_TESTS
from automation.e2e_tests.test_mana import ALL_TESTS as MANA_TESTS
from automation.e2e_tests.test_notes import ALL_TESTS as NOTES_TESTS
from automation.e2e_tests.test_scrollbar import ALL_TESTS as SCROLLBAR_TESTS
from automation.e2e_tests.test_widgets import ALL_TESTS as WIDGET_TESTS

ALL_TESTS = (
    LAUNCH_TESTS
    + BUILDER_TESTS
    + SCROLLBAR_TESTS
    + MANA_TESTS
    + NOTES_TESTS
    + BUTTON_TESTS
    + WIDGET_TESTS
    + IMAGE_TESTS
    + GOLDEN_TESTS
)

_AVAILABLE_GROUPS = "launch, builder, scrollbar, mana, notes, buttons, widgets, images, golden"


def run_all_tests(only: str | None = None) -> int:
    print("MTGO Tools — End-to-End UI Regression Tests")
    print("=" * 60)
    print()

    client = AutomationClient()
    print("Connecting to automation server…")
    if not client.wait_for_server(timeout=15.0):
        print("ERROR: Could not connect to automation server.")
        print("Start the app with:  python main.py --automation")
        return 1
    print("Connected.\n")

    runner = E2ETestRunner(client)
    groups_run = set()

    for group, name, fn in ALL_TESTS:
        if only is not None and group != only:
            continue
        groups_run.add(group)
        runner.run(name, lambda _fn=fn: _fn(client))

    if not groups_run:
        print(f"No tests found for group '{only}'. Available: {_AVAILABLE_GROUPS}")
        return 1

    return runner.summary()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run MTGO Tools end-to-end UI regression tests.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--only",
        metavar="GROUP",
        help=f"Run only tests in this group: {_AVAILABLE_GROUPS}",
    )
    args = parser.parse_args()
    return run_all_tests(only=args.only)
