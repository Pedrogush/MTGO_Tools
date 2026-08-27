"""Keep ``tests/ui/conftest.py``'s ``replacements`` dict honest.

``monkeypatch.setattr(utils.constants, NAME, tmp_path / ...)`` redirects a path
only for consumers that resolve ``constants.NAME`` at *call* time. Every other
consumer does ``from utils.constants import NAME`` at module scope — some then
bake the value into a constructor default — and is bound to the real path long
before the fixture runs, so the rebind does nothing at all.

That is easy to get wrong twice: the dict accumulated two entries naming constants
with no production consumer whatsoever, and the SQLite deck cache was "isolated"
by a constant that could never have worked. These tests fail loudly if either
mistake comes back, and they run everywhere (pure source inspection, no wx, no
GUI), unlike the UI tests they describe.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import utils.constants as constants

REPO_ROOT = Path(__file__).resolve().parents[1]
UI_CONFTEST = REPO_ROOT / "tests" / "ui" / "conftest.py"

# Where production code lives. Deliberately an explicit list rather than a repo
# walk: ``.claude/worktrees/`` holds full stale copies of the tree and would
# multiply every hit below.
PRODUCTION_PACKAGES = ("controllers", "repositories", "services", "utils", "widgets")

# The declaration site. Every constant is obviously "used" here, so counting it
# would make the orphan check below vacuous.
CONSTANTS_PACKAGE = REPO_ROOT / "utils" / "constants"

# Entries the fixture's comment claims actually redirect something. Keep this in
# sync with that comment — the point of the test is that the claim stays true.
LOAD_BEARING = frozenset({"CURR_DECK_FILE"})

# Constants that are baked into a constructor default at import time. Naming one
# of these in ``replacements`` looks like isolation and provides none; the fixture
# seeds the owning singleton instead (``_isolate_path_singletons``).
UNREACHABLE_BY_SETATTR = frozenset({"DECK_CACHE_DB_FILE"})


def _replacement_keys() -> list[str]:
    """Extract the ``replacements`` dict keys from the UI conftest source."""
    tree = ast.parse(UI_CONFTEST.read_text(encoding="utf-8"), filename=str(UI_CONFTEST))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "replacements" for t in node.targets):
            continue
        assert isinstance(node.value, ast.Dict), "replacements must stay a dict literal"
        keys = [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
        assert len(keys) == len(node.value.keys), "replacements keys must be plain strings"
        return keys
    raise AssertionError(f"no `replacements = {{...}}` assignment found in {UI_CONFTEST}")


def _production_sources() -> list[Path]:
    files: list[Path] = []
    for package in PRODUCTION_PACKAGES:
        for path in sorted((REPO_ROOT / package).rglob("*.py")):
            if CONSTANTS_PACKAGE in path.parents:
                continue
            files.append(path)
    return files


def _attribute_readers(name: str, sources: list[str]) -> int:
    """Count ``constants.<name>`` attribute reads — the only form setattr reaches."""
    pattern = re.compile(rf"\bconstants\.{re.escape(name)}\b")
    return sum(1 for text in sources if pattern.search(text))


@pytest.fixture(scope="module", name="production_sources")
def fixture_production_sources() -> list[str]:
    return [path.read_text(encoding="utf-8", errors="ignore") for path in _production_sources()]


def test_every_replaced_constant_still_exists() -> None:
    """A renamed constant must not leave a silently-dead line behind."""
    missing = [name for name in _replacement_keys() if not hasattr(constants, name)]
    assert not missing, f"tests/ui/conftest.py redirects constants that no longer exist: {missing}"


def test_the_dict_names_no_constant_without_a_production_consumer(
    production_sources: list[str],
) -> None:
    """Every entry must at least name a constant production code reads somewhere.

    An entry naming a constant nothing outside ``utils.constants`` reads is pure
    decoration; two such entries lived here until this test was added.
    """
    orphans = []
    for name in _replacement_keys():
        pattern = re.compile(rf"\b{re.escape(name)}\b")
        if not any(pattern.search(text) for text in production_sources):
            orphans.append(name)
    assert not orphans, (
        "tests/ui/conftest.py redirects constants that no production module uses; "
        f"delete them rather than growing the list: {orphans}"
    )


def test_the_load_bearing_entries_are_exactly_the_ones_declared(
    production_sources: list[str],
) -> None:
    """The comment on ``replacements`` must keep matching reality.

    If a consumer switches to ``constants.X`` attribute access, that entry starts
    working and belongs in ``LOAD_BEARING`` (and in the fixture's comment). If the
    last such consumer goes away, the entry stops isolating anything and the
    comment must stop claiming it does.
    """
    actual = {name for name in _replacement_keys() if _attribute_readers(name, production_sources)}
    assert actual == set(LOAD_BEARING), (
        "the `replacements` comment in tests/ui/conftest.py lists the entries that "
        f"actually redirect anything as {sorted(LOAD_BEARING)}, but attribute-style "
        f"`constants.X` reads say {sorted(actual)}. Update both together."
    )


def test_constructor_default_paths_are_not_faked_through_the_dict() -> None:
    """Adding these to the dict would look like a fix and be inert."""
    named = set(_replacement_keys()) & set(UNREACHABLE_BY_SETATTR)
    assert not named, (
        f"{sorted(named)} is bound into a constructor default at import time, so "
        "monkeypatching utils.constants cannot redirect it. Seed the owning "
        "singleton in `_isolate_path_singletons` instead."
    )
