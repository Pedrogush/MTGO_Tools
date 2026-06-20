"""Static guard against the 'unrepainted runtime layout change' class of bug.

Showing/hiding a widget at runtime and then calling a bare ``Window.Layout()``
does not force the top-level window to repaint. On Windows this leaves "ghost"
pixels behind from native controls (notably accent-coloured ``wx.Button``s) until
an external repaint occurs. The cure is to route runtime visibility/layout
changes through :mod:`widgets.wx_layout` (``relayout`` / ``set_shown``), which
repaints the owning frame.

This test parses every widget source file and fails if a *runtime* method
toggles a widget's visibility (``.Show(...)``/``.Hide(...)``) and calls a bare
``.Layout()`` *without* also routing the repaint through
:mod:`widgets.wx_layout` (``relayout``/``set_shown``) — the exact shape that
ghosts — so the bug cannot be reintroduced unnoticed.

A method that calls ``relayout``/``set_shown`` is considered compliant even if
it also has intermediate ``.Layout()`` calls (e.g. laying out an inner sizer
inside a ``Freeze``/``Thaw`` block), because the sanctioned helper guarantees the
top-level repaint. Construction methods (``__init__``, ``_build_*`` …) are exempt:
nothing is on screen yet, so there is no stale paint to clear.
"""

from __future__ import annotations

import ast
from pathlib import Path

WIDGETS_DIR = Path(__file__).resolve().parents[1] / "widgets"

# Methods that run before the window is shown — Show/Hide + Layout there is fine.
_CONSTRUCTION_PREFIXES = (
    "__init__",
    "build",
    "_build",
    "create",
    "_create",
    "setup",
    "_setup",
    "compose",
    "_compose",
    "_init_",
    "_make_",
)

# Files allowed to call bare Layout()/Show() because they *are* the sanctioned
# repaint plumbing or otherwise vetted.
_EXEMPT_FILES = {"wx_layout.py"}


def _is_construction(func_name: str) -> bool:
    return func_name.startswith(_CONSTRUCTION_PREFIXES)


_REPAINT_HELPERS = {"relayout", "set_shown"}


def _called_names(node: ast.AST) -> tuple[set[str], set[str]]:
    """Return (method names via ``x.NAME(...)``, function names via ``NAME(...)``)."""
    attrs: set[str] = set()
    funcs: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Attribute):
            attrs.add(child.func.attr)
        elif isinstance(child.func, ast.Name):
            funcs.add(child.func.id)
    return attrs, funcs


def _violations_in_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if _is_construction(node.name):
            continue
        attrs, funcs = _called_names(node)
        toggles_visibility = bool(attrs & {"Show", "Hide"})
        bare_layout = "Layout" in attrs
        routed_through_helper = bool(funcs & _REPAINT_HELPERS)
        if toggles_visibility and bare_layout and not routed_through_helper:
            out.append(f"{path.name}:{node.lineno} {node.name}()")
    return out


def test_no_runtime_show_hide_with_bare_layout():
    violations: list[str] = []
    for path in sorted(WIDGETS_DIR.rglob("*.py")):
        if path.name in _EXEMPT_FILES:
            continue
        violations.extend(_violations_in_file(path))

    assert not violations, (
        "Runtime Show/Hide followed by a bare Window.Layout() leaves repaint "
        "ghosts on Windows. Route these through widgets.wx_layout.set_shown / "
        "relayout instead of calling Layout() directly:\n  " + "\n  ".join(violations)
    )
