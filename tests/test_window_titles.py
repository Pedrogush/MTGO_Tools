"""No top-level window may name itself with an English string literal.

Phase 4 of issue #962 counted **7 of the app's 18 top-level windows** carrying
hard-coded, untranslated titles: the diagnostics export, the sideboard-guide
entry editor, the guide import options, the offline-images dialog, the mana
keyboard, the splash frame and the comp-rules popup. Every one of them had been
added after the locale catalogues existed, and every one was invisible to the
existing i18n test, which only checks that the two catalogues agree with each
other -- it cannot see a string that never entered a catalogue.

So this guard looks at the other end: the ``title=`` argument of every top-level
window construction in ``widgets/``. A literal there is, by construction, a
string the pt-BR user will read in English.

Titles are separated out from the general "untranslated literal" problem on
purpose. A window *title* is the one string the OS repeats outside the window --
in the taskbar, in Alt-Tab, in the window list -- so an English title is visible
even when the window is not, and a guard scoped to titles has no exceptions,
which is what makes it worth keeping. (The wider gap is real and is **not**
covered here: a mechanical count at the time of writing found 41 literal
``label=`` / ``title=`` / ``hint=`` strings across 14 files in ``widgets/``.)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

WIDGETS = Path(__file__).resolve().parent.parent / "widgets"

#: Calls whose ``title=`` names a top-level window: the ``super().__init__`` of a
#: wx.Frame/Dialog/MiniFrame subclass, and direct construction of a stock one.
TOP_LEVEL_CALLS = frozenset({"wx.Dialog", "wx.Frame", "wx.MiniFrame", "super().__init__"})


def _callee(node: ast.Call) -> str:
    """A dotted-ish name for the thing being called, or ``""``."""
    parts: list[str] = []
    cur: ast.expr = node.func
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    elif isinstance(cur, ast.Call) and isinstance(cur.func, ast.Name):
        parts.append(f"{cur.func.id}()")
    else:
        return ""
    return ".".join(reversed(parts))


def _title_sites() -> list[tuple[Path, int, str, ast.expr]]:
    sites: list[tuple[Path, int, str, ast.expr]] = []
    for path in sorted(WIDGETS.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            callee = _callee(node)
            if callee not in TOP_LEVEL_CALLS:
                continue
            for kw in node.keywords:
                if kw.arg == "title":
                    sites.append((path, node.lineno, callee, kw.value))
    return sites


def test_the_guard_can_see_the_windows_it_guards() -> None:
    """A guard that found nothing would pass forever; pin the population."""
    sites = _title_sites()
    assert len(sites) >= 14, (
        f"only found {len(sites)} top-level title= sites; the AST shapes this "
        "guard recognises have probably drifted"
    )


@pytest.mark.parametrize(
    "path,lineno,callee,value",
    _title_sites(),
    ids=[f"{p.parent.name}/{p.name}:{n}" for p, n, _c, _v in _title_sites()],
)
def test_window_title_is_not_a_literal(
    path: Path, lineno: int, callee: str, value: ast.expr
) -> None:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        pytest.fail(
            f"{path}:{lineno} names a top-level window {value.value!r} as a "
            "literal, so it renders in English in pt-BR. Add a "
            "'window.title.*' key to utils/i18n/_en_us/window.py and "
            "utils/i18n/_pt_br/window.py and translate it -- via self._t() if "
            "the window is handed a locale, or utils.i18n.t() if it is not."
        )


def test_every_window_title_key_is_used() -> None:
    """A key nobody reads is a translation that never reaches the screen."""
    from utils.i18n import MESSAGES

    sources = "\n".join(p.read_text(encoding="utf-8") for p in WIDGETS.rglob("*.py"))
    unused = sorted(
        key for key in MESSAGES["en-US"] if key.startswith("window.title.") and key not in sources
    )
    assert not unused, f"window title keys nothing uses: {unused}"
