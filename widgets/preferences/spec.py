"""Declarative description of the app's preferences.

Preferences are **data**, for the same reason the menu bar's contents are
(:mod:`widgets.menu_bar.spec`): the dialog that renders them runs
``wx.Dialog.ShowModal``, which spins a nested modal loop on the main thread and
stops the automation socket being serviced (review finding §5.5). A harness that
reached a setting by "open Preferences, then click the dropdown" would deadlock
exactly the way clicking a menu did.

So the spec is addressable on its own. :class:`~widgets.preferences.dialog.PreferencesDialog`
renders it into wx controls; ``automation`` reads and writes the same spec
through :func:`describe` and :func:`apply_preference` without a dialog existing.
Phase 3b made that split for the menus and it is the reason twelve preference
items survived the toolbar's deletion still reachable from a script; collapsing
those items into a modal dialog would have thrown it away again.

Specs are rebuilt on every open, so a value always reflects current state rather
than the state at construction.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Preference:
    """One setting.

    ``kind`` is one of:

    ``choice``
        One of ``options``, given as ``((value, label), ...)``. ``current`` names
        the selected value and ``on_select`` receives the chosen value.
    ``toggle``
        A boolean. ``checked`` seeds it; ``on_toggle`` receives the new value.

    ``key`` is the stable, translation-independent name a script addresses the
    setting by -- ``label`` is translated and therefore cannot be one.
    ``help`` is the one-line explanation rendered under the control; the menu
    could not show one, which is the main thing a dialog buys.
    """

    key: str
    label: str
    kind: str = "choice"
    help: str = ""
    options: tuple[tuple[str, str], ...] = ()
    current: str = ""
    on_select: Callable[[str], None] | None = None
    checked: bool = False
    on_toggle: Callable[[bool], None] | None = None


@dataclass(frozen=True)
class PreferenceGroup:
    """A titled block of settings, rendered as one section card."""

    title: str
    items: tuple[Preference, ...] = field(default_factory=tuple)


def find_preference(groups: Sequence[PreferenceGroup], key: str) -> Preference | None:
    """The preference named ``key``, or ``None``."""
    for group in groups:
        for item in group.items:
            if item.key == key:
                return item
    return None


def apply_preference(groups: Sequence[PreferenceGroup], key: str, value: str) -> bool:
    """Set the preference named ``key`` to ``value``. Returns whether it applied.

    ``value`` for a ``choice`` matches either the option's value or its
    translated label -- a caller scripting the app knows the value, a caller
    reading ``describe`` sees the label. For a ``toggle`` it is one of
    ``on/off/true/false/1/0``, or ``toggle`` to flip it.
    """
    pref = find_preference(groups, key)
    if pref is None:
        return False
    if pref.kind == "choice" and pref.on_select is not None:
        for option_value, option_label in pref.options:
            if value in (option_value, option_label):
                pref.on_select(option_value)
                return True
        return False
    if pref.kind == "toggle" and pref.on_toggle is not None:
        lowered = value.strip().lower()
        if lowered == "toggle":
            pref.on_toggle(not pref.checked)
            return True
        if lowered in ("on", "true", "1", "yes"):
            pref.on_toggle(True)
            return True
        if lowered in ("off", "false", "0", "no"):
            pref.on_toggle(False)
            return True
    return False


def describe(groups: Sequence[PreferenceGroup]) -> list[dict[str, object]]:
    """A JSON-safe outline of ``groups``, for ``automation.cli prefs``."""
    out: list[dict[str, object]] = []
    for group in groups:
        rows: list[dict[str, object]] = []
        for item in group.items:
            row: dict[str, object] = {"key": item.key, "kind": item.kind, "label": item.label}
            if item.help:
                row["help"] = item.help
            if item.kind == "choice":
                row["options"] = [label for _value, label in item.options]
                row["values"] = [value for value, _label in item.options]
                row["current"] = item.current
            else:
                row["checked"] = item.checked
            rows.append(row)
        out.append({"title": group.title, "items": rows})
    return out


__all__ = [
    "Preference",
    "PreferenceGroup",
    "apply_preference",
    "describe",
    "find_preference",
]
