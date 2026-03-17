"""Shared infrastructure for e2e test modules."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from automation.client import AutomationClient, AutomationError

# ---------------------------------------------------------------------------
# Dummy deck used as a stable baseline for golden screenshots and assertions.
# Contains a realistic spread of cards with varied mana costs so mana symbols
# and card-image loading are exercised.
# ---------------------------------------------------------------------------
DUMMY_DECK_TEXT = """\
4 Lightning Bolt
4 Goblin Guide
4 Monastery Swiftspear
4 Eidolon of the Great Revel
4 Lava Spike
4 Skullcrack
4 Searing Blaze
4 Rift Bolt
4 Light Up the Stage
4 Inspiring Vantage
4 Sacred Foundry
4 Sunbaked Canyon
4 Fiery Islet
4 Mountain
Sideboard
4 Searing Blood
4 Rest in Peace
3 Smash to Smithereens
2 Deflecting Palm
2 Skullcrack
"""

# Directory where golden screenshots are saved for visual review.
GOLDEN_DIR = Path(__file__).parent.parent / "golden"


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


class RunResult:
    def __init__(self, name: str, passed: bool, message: str = "", duration: float = 0.0) -> None:
        self.name = name
        self.passed = passed
        self.message = message
        self.duration = duration


class E2ETestRunner:
    def __init__(self, client: AutomationClient) -> None:
        self.client = client
        self.results: list[RunResult] = []

    def run(self, name: str, fn: Callable[[], None]) -> RunResult:
        start = time.time()
        try:
            fn()
            result = RunResult(name, True, "OK", time.time() - start)
        except AssertionError as exc:
            result = RunResult(name, False, str(exc), time.time() - start)
        except AutomationError as exc:
            result = RunResult(name, False, f"AutomationError: {exc}", time.time() - start)
        except Exception as exc:  # noqa: BLE001
            result = RunResult(name, False, f"Unexpected error: {exc}", time.time() - start)
        self.results.append(result)
        status = "PASS" if result.passed else "FAIL"
        print(f"  [{status}] {name} ({result.duration:.2f}s)")
        if not result.passed:
            print(f"         {result.message}")
        return result

    def summary(self) -> int:
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total_time = sum(r.duration for r in self.results)
        print("\n" + "=" * 60)
        print(f"Tests: {passed} passed, {failed} failed  ({total_time:.2f}s)")
        print("=" * 60)
        return 1 if failed > 0 else 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def save_screenshot(client: AutomationClient, label: str) -> str:
    """Save a screenshot to the golden directory and return its path."""
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    path = str(GOLDEN_DIR / f"{label}.png")
    result = client.screenshot(path)
    return result.get("path", path)


def load_dummy_deck(client: AutomationClient) -> None:
    """Load the standard dummy deck and assert it succeeded."""
    result = client.load_deck_text(DUMMY_DECK_TEXT)
    assert result.get("loaded"), f"load_deck_text failed: {result}"
    assert result["mainboard_count"] > 0, "Mainboard should have cards after loading"
    assert result["sideboard_count"] > 0, "Sideboard should have cards after loading"
