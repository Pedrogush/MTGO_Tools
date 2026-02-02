#!/usr/bin/env python3
"""
Example test runner for UI automation.

This script demonstrates how to write automated UI tests using the
automation client.

Usage:
    # First, start the app with automation enabled:
    python main.py --automation

    # Then run this test script:
    python -m automation.test_runner
"""

import sys
import time
from typing import Callable

from automation.client import AutomationClient, AutomationError, ConnectionError


class TestResult:
    """Simple test result container."""

    def __init__(self, name: str, passed: bool, message: str = "", duration: float = 0.0):
        self.name = name
        self.passed = passed
        self.message = message
        self.duration = duration


class UITestRunner:
    """Run automated UI tests."""

    def __init__(self, client: AutomationClient):
        self.client = client
        self.results: list[TestResult] = []

    def run_test(self, name: str, test_fn: Callable[[], None]) -> TestResult:
        """Run a single test and capture the result."""
        start_time = time.time()
        try:
            test_fn()
            duration = time.time() - start_time
            result = TestResult(name, True, "OK", duration)
        except AssertionError as e:
            duration = time.time() - start_time
            result = TestResult(name, False, str(e), duration)
        except Exception as e:
            duration = time.time() - start_time
            result = TestResult(name, False, f"Error: {e}", duration)

        self.results.append(result)
        status = "PASS" if result.passed else "FAIL"
        print(f"  [{status}] {name} ({result.duration:.2f}s)")
        if not result.passed:
            print(f"         {result.message}")
        return result

    def print_summary(self) -> None:
        """Print test summary."""
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total_time = sum(r.duration for r in self.results)

        print("\n" + "=" * 50)
        print(f"Tests: {passed} passed, {failed} failed")
        print(f"Time: {total_time:.2f}s")
        print("=" * 50)


def test_connection(client: AutomationClient) -> None:
    """Test that we can connect to the app."""
    result = client.ping()
    assert "status" in result, "Ping response should contain 'status'"
    assert result["status"] == "ok", f"Expected status 'ok', got '{result['status']}'"


def test_get_window_info(client: AutomationClient) -> None:
    """Test getting window information."""
    info = client.get_window_info()
    assert "title" in info, "Window info should contain 'title'"
    assert "MTGO" in info["title"], f"Window title should contain 'MTGO', got '{info['title']}'"
    assert info["visible"], "Window should be visible"


def test_get_status(client: AutomationClient) -> None:
    """Test getting status bar text."""
    status = client.get_status()
    # Status should be a string (may be empty initially)
    assert isinstance(status, str), f"Status should be a string, got {type(status)}"


def test_list_widgets(client: AutomationClient) -> None:
    """Test listing available widgets."""
    result = client.list_widgets()
    assert "widgets" in result, "Response should contain 'widgets'"
    widgets = result["widgets"]
    assert "toolbar" in widgets, "Should have toolbar widget"
    assert "research_panel" in widgets, "Should have research_panel widget"


def test_get_format(client: AutomationClient) -> None:
    """Test getting current format."""
    format_name = client.get_format()
    assert isinstance(format_name, str), f"Format should be a string, got {type(format_name)}"
    # Format should be one of the known formats
    known_formats = {"Modern", "Standard", "Pioneer", "Legacy", "Vintage", "Pauper"}
    assert format_name in known_formats, f"Unknown format: {format_name}"


def test_screenshot(client: AutomationClient) -> None:
    """Test taking a screenshot."""
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name

    try:
        result = client.screenshot(path)
        assert "path" in result, "Screenshot result should contain 'path'"
        assert os.path.exists(result["path"]), f"Screenshot file should exist: {result['path']}"
        assert result["width"] > 0, "Screenshot width should be > 0"
        assert result["height"] > 0, "Screenshot height should be > 0"
    finally:
        if os.path.exists(path):
            os.unlink(path)


def test_switch_tab(client: AutomationClient) -> None:
    """Test switching tabs."""
    result = client.switch_tab("Stats")
    assert result.get("switched"), f"Should switch to Stats tab: {result}"

    result = client.switch_tab("Deck Tables")
    assert result.get("switched"), f"Should switch to Deck Tables tab: {result}"


def run_all_tests() -> int:
    """Run all UI tests."""
    print("MTGO Tools UI Automation Tests")
    print("=" * 50)
    print()

    # Connect to the app
    print("Connecting to automation server...")
    client = AutomationClient()

    try:
        if not client.wait_for_server(timeout=10.0):
            print("ERROR: Could not connect to automation server.")
            print("Make sure the app is running with: python main.py --automation")
            return 1
    except Exception as e:
        print(f"ERROR: {e}")
        return 1

    print("Connected!")
    print()

    # Run tests
    runner = UITestRunner(client)

    print("Running tests...")
    runner.run_test("Connection", lambda: test_connection(client))
    runner.run_test("Window Info", lambda: test_get_window_info(client))
    runner.run_test("Status Bar", lambda: test_get_status(client))
    runner.run_test("List Widgets", lambda: test_list_widgets(client))
    runner.run_test("Get Format", lambda: test_get_format(client))
    runner.run_test("Screenshot", lambda: test_screenshot(client))
    runner.run_test("Switch Tabs", lambda: test_switch_tab(client))

    runner.print_summary()

    # Return exit code based on results
    failed = sum(1 for r in runner.results if not r.passed)
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(run_all_tests())
