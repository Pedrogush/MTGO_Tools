"""Root-level pytest fixtures for all tests.

This module provides fixtures that are available to all tests in the project.
"""

import pytest
from test_helpers import reset_all_globals

from utils.constants import timing


@pytest.fixture(autouse=True)
def reset_global_state():
    """Automatically reset all global service and repository instances after each test.

    This fixture ensures test isolation by resetting all singleton instances
    to None after each test completes, preventing state leakage between tests.
    """
    yield
    reset_all_globals()


@pytest.fixture(autouse=True)
def _fast_batch_resolve_debounce(monkeypatch):
    """Collapse the batch-resolver debounce so tests don't wait the real 0.5s.

    The Scryfall batch resolver waits ``IMAGE_BATCH_RESOLVE_DEBOUNCE_SECONDS`` to
    collect a burst before firing. That window is production behavior, not
    something unit tests should sit through — the resolver reads the constant
    live each window, so patching it here keeps the suite fast. Tests that
    exercise the debounce itself override this locally.
    """
    monkeypatch.setattr(timing, "IMAGE_BATCH_RESOLVE_DEBOUNCE_SECONDS", 0.0)
