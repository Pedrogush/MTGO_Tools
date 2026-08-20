"""Declarative description of one menu's contents.

The menus are data, not widgets. :class:`AppMenuBar` renders a spec into a real
``wx.Menu`` at the moment the user opens it, and the automation harness invokes
the very same spec by label (``automation/server/introspection.py``) without
popping anything up.

That split exists because ``wx.PopupMenu`` runs a **nested modal loop on the main
thread** (review finding §5.5): while a menu is on screen the automation socket
is not serviced, so a harness that reached these actions by "click the menu, then
click the item" would deadlock. Keeping the spec addressable independently of the
widget is what lets the six companion windows and the twelve preference items
stay reachable from the harness after the toolbar buttons are gone.

Specs are rebuilt on every open, so radio checks and the conditional update entry
always reflect current state rather than the state at construction.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class MenuEntry:
    """One row of a menu.

    ``kind`` is one of:

    ``item``
        A plain action. ``on_activate`` runs it.
    ``check``
        A toggle. ``checked`` seeds it; ``on_toggle`` receives the new value.
    ``radio``
        A submenu of mutually exclusive options. ``options`` is
        ``((value, label), ...)``, ``current`` names the selected value and
        ``on_select`` receives the chosen value.
    ``separator``
        A rule. Carries nothing else.

    ``help`` is the one-line explanation wx passes to a frame's status bar on
    hover. The app owns its status strip (:mod:`widgets.status_bar`) rather than
    using ``wx.StatusBar``, so nothing renders it *yet* -- it is carried because
    it is the idiomatic home for the copy that used to be the toolbar tooltips,
    and dropping it would mean deleting six translated strings per locale.
    """

    kind: str = "item"
    label: str = ""
    help: str = ""
    on_activate: Callable[[], None] | None = None
    checked: bool = False
    on_toggle: Callable[[bool], None] | None = None
    options: tuple[tuple[str, str], ...] = ()
    current: str = ""
    on_select: Callable[[str], None] | None = None


def separator() -> MenuEntry:
    return MenuEntry(kind="separator")


@dataclass(frozen=True)
class MenuSpec:
    """A top-level menu: its title plus a builder for its (current) entries."""

    title: str
    build: Callable[[], Sequence[MenuEntry]]


def invoke_entry(entries: Sequence[MenuEntry], path: Sequence[str]) -> bool:
    """Activate the entry named by ``path`` (``["Tools", "Radar"]`` minus the menu).

    Returns whether something was activated. Used by the automation harness so a
    menu item can be driven without the modal popup loop; also makes the menu
    tree unit-testable with no wx window in play.
    """
    if not path:
        return False
    label, rest = path[0], path[1:]
    for entry in entries:
        if entry.label != label:
            continue
        if entry.kind == "item" and not rest and entry.on_activate is not None:
            entry.on_activate()
            return True
        if entry.kind == "check" and not rest and entry.on_toggle is not None:
            entry.on_toggle(not entry.checked)
            return True
        if entry.kind == "radio" and len(rest) == 1 and entry.on_select is not None:
            for value, option_label in entry.options:
                if option_label == rest[0] or value == rest[0]:
                    entry.on_select(value)
                    return True
            return False
    return False


def describe(entries: Sequence[MenuEntry]) -> list[dict[str, object]]:
    """A JSON-safe outline of ``entries``, for ``automation.cli menu --list``."""
    out: list[dict[str, object]] = []
    for entry in entries:
        if entry.kind == "separator":
            continue
        row: dict[str, object] = {"kind": entry.kind, "label": entry.label}
        if entry.kind == "check":
            row["checked"] = entry.checked
        if entry.kind == "radio":
            row["options"] = [label for _value, label in entry.options]
            row["current"] = entry.current
        out.append(row)
    return out


__all__ = ["MenuEntry", "MenuSpec", "describe", "invoke_entry", "separator"]
