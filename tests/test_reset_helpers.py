"""Unit tests for the reset-function resolution in ``tests/test_helpers.py``.

These cover the fallback behaviour of ``_optional_reset`` so that a renamed,
removed, or relocated ``reset_*`` function produces a loud warning instead of a
silently broken (no-op) test-isolation hook, while a genuinely missing optional
dependency (e.g. ``wx``) stays silent.
"""

import inspect
import re
import sys
import types
import warnings
from pathlib import Path

import pytest
import test_helpers

_REPO_ROOT = Path(test_helpers.__file__).resolve().parent.parent
# Module-level ``def reset_*(`` declarations (column 0, i.e. not class methods).
_RESET_DEF_RE = re.compile(r"^def (reset_[a-zA-Z0-9_]+)\(", re.MULTILINE)


def _discover_reset_singletons():
    """Find every module-level ``reset_*`` function under repositories/ and services/.

    Returns a list of ``(name, source_path)`` tuples. These are the global
    singleton reset hooks the test-isolation harness is expected to invoke.
    """
    found = []
    for package in ("repositories", "services"):
        for path in sorted((_REPO_ROOT / package).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for name in _RESET_DEF_RE.findall(text):
                found.append((name, path))
    return found


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

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        # Simulate *only* the target module importing an absent optional
        # dependency; delegate everything else so pytest internals keep working.
        if name == module_path:
            raise ImportError("No module named 'wx'", name="wx")
        return real_import(name, *args, **kwargs)

    # ``__import__`` is looked up as a builtin, so patching builtins is what
    # actually intercepts the call inside ``_optional_reset``.
    monkeypatch.setattr(builtins, "__import__", fake_import)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fn = test_helpers._optional_reset(module_path, "reset_x")

    assert fn() is None
    assert not caught, [str(c.message) for c in caught]


def test_import_error_without_name_warns(monkeypatch):
    """An ImportError with no ``.name`` (``exc.name is None``) must warn.

    Without a populated ``name`` attribute we cannot distinguish a benign
    missing optional dependency from a broken target module, so the safe
    behaviour is to surface a warning rather than silently no-op.
    """
    module_path = "pkg.nameless_target"

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == module_path:
            raise ImportError("import failed with no name attribute")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fn = test_helpers._optional_reset(module_path, "reset_x")

    assert fn() is None
    assert any(module_path in str(c.message) for c in caught)


def test_every_reset_singleton_is_wired_into_reset_all_globals():
    """Guard: each discovered ``reset_*`` singleton must be reset by the harness.

    A new module-level ``reset_*`` function added under repositories/ or
    services/ that is not wired into ``reset_all_globals()`` leaks its cached
    instance across the whole test session, defeating isolation. This test
    fails loudly so the harness is kept in sync.
    """
    aggregate_source = "\n".join(
        inspect.getsource(fn)
        for fn in (
            test_helpers.reset_all_services,
            test_helpers.reset_all_repositories,
        )
    )

    discovered = _discover_reset_singletons()
    assert discovered, "expected to discover at least one reset_* singleton"

    missing = sorted({name for name, _ in discovered if f"{name}()" not in aggregate_source})
    assert not missing, (
        "reset_all_globals() does not invoke these reset_* singletons, leaking "
        f"state between tests: {missing}"
    )
