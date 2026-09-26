"""The UI fixtures must not reach for the application's controller singleton.

``controllers.app_controller`` keeps one ``AppController`` behind
``get_deck_selector_controller``. That global belongs to the running app, whose
composition root (``widgets.frames.app_frame.make_app_frame``) is the only thing
that asks for it.

``build_app_frame`` used to reset the global and take the fresh instance, and
the two window fixtures then disagreed about which controller was current. A
module that used ``shared_frame`` and then ``deck_selector_factory`` -- which
``tests/ui/test_deck_selector.py`` does, twice over -- left its shared window
driving a controller that the singleton no longer named: a different card,
deck, metagame and image service than anything that went through the accessor
would get, while ``tests/conftest.py`` recycled those service singletons after
every test underneath both of them.

Nothing else in the suite reads the global, so the fix was to stop writing it:
every test window is built on an ``AppController()`` of its own. This is the
pin. It is static and it is cheap, so it runs in the parallel half of the suite
rather than costing the serial UI job anything, and it fails on the import line
rather than on whatever behaviour the swap happened to change three tests
later.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
UI_TESTS_DIR = TESTS_DIR / "ui"

#: The accessors that read or clear the module global. Neither belongs in a test.
SINGLETON_NAMES = frozenset({"get_deck_selector_controller", "reset_deck_selector_controller"})


def _ui_sources() -> list[Path]:
    paths = sorted(UI_TESTS_DIR.glob("*.py"))
    assert paths, f"no Python files under {UI_TESTS_DIR}"
    return paths


def _names_used(path: Path) -> set[str]:
    """Every bare name and attribute name the file mentions.

    Both spellings are caught: ``from controllers.app_controller import
    get_deck_selector_controller`` and ``app_controller.get_deck_selector_controller()``.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
    return names


@pytest.mark.parametrize("path", _ui_sources(), ids=lambda path: path.name)
def test_no_ui_test_touches_the_controller_singleton(path: Path) -> None:
    used = sorted(_names_used(path) & SINGLETON_NAMES)
    assert not used, (
        f"{path.relative_to(TESTS_DIR.parent)} names {used}. A test window is built on an "
        "``AppController()`` of its own (tests/ui/conftest.py::build_app_frame); "
        "taking or clearing the global makes ``shared_frame`` and "
        "``deck_selector_factory`` disagree about which controller is current."
    )
