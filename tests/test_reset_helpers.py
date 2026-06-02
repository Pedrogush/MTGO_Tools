"""Unit tests for the reset-function resolution in ``tests/test_helpers.py``.

These cover the fallback behaviour of ``_optional_reset`` so that a renamed,
removed, or relocated ``reset_*`` function produces a loud warning instead of a
silently broken (no-op) test-isolation hook, while a genuinely missing optional
dependency (e.g. ``wx``) stays silent.
"""

import sys
import types
import warnings

import pytest
import test_helpers


@pytest.fixture
def fake_module():
    """Register a throwaway module in ``sys.modules`` and clean it up."""
    created = []

    def _make(name):
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        created.append(name)
        return mod

    yield _make

    for name in created:
        sys.modules.pop(name, None)


def test_resolves_existing_attribute(fake_module):
    mod = fake_module("fake_reset_mod_exists")

    def reset_thing():
        return "called"

    mod.reset_thing = reset_thing

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning would fail the test
        fn = test_helpers._optional_reset("fake_reset_mod_exists", "reset_thing")

    assert fn is reset_thing
    assert fn() == "called"


def test_missing_attribute_warns(fake_module):
    """A renamed/removed reset function must surface a warning, not silence."""
    fake_module("fake_reset_mod_no_attr")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fn = test_helpers._optional_reset("fake_reset_mod_no_attr", "reset_renamed")

    assert fn() is None  # no-op fallback
    assert any("reset_renamed" in str(c.message) for c in caught)


def test_missing_target_module_warns():
    """An unimportable target module (its own name) must warn."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fn = test_helpers._optional_reset("definitely_not_a_real_module_xyz", "reset_y")

    assert fn() is None
    assert any("definitely_not_a_real_module_xyz" in str(c.message) for c in caught)


def test_transitive_missing_optional_dependency_is_silent(monkeypatch):
    """ImportError whose ``.name`` differs from the target module is benign.

    This is the expected CI fallback (e.g. the module imports ``wx`` which is
    not installed): the resolution should fall back to a no-op *silently*.
    """
    module_path = "pkg.target_mod"

    def fake_import(name, *args, **kwargs):
        # Simulate the target module importing an absent optional dependency.
        raise ImportError("No module named 'wx'", name="wx")

    monkeypatch.setattr(test_helpers, "__import__", fake_import, raising=False)
    # ``__import__`` is looked up as a builtin; patch builtins to be safe.
    import builtins

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fn = test_helpers._optional_reset(module_path, "reset_x")

    assert fn() is None
    assert not caught, [str(c.message) for c in caught]
