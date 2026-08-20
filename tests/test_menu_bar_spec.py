"""The menu bar's contents are data, so they can be tested without a window.

Phase 3b (#962) replaced six toolbar buttons and a twelve-item gear popup with a
menu bar. The automation harness reaches those actions through
:func:`widgets.menu_bar.spec.invoke_entry` rather than by clicking, because
``wx.PopupMenu`` blocks the thread the automation socket runs on — so this module
is the contract both the UI and the harness sit on.
"""

from __future__ import annotations

import pytest

from widgets.menu_bar.spec import MenuEntry, describe, invoke_entry, separator


def _calls() -> tuple[list[object], list[MenuEntry]]:
    seen: list[object] = []
    entries = [
        MenuEntry(label="Load Collection", on_activate=lambda: seen.append("load")),
        separator(),
        MenuEntry(
            kind="check",
            label="Check for updates",
            checked=True,
            on_toggle=lambda value: seen.append(("check", value)),
        ),
        MenuEntry(
            kind="radio",
            label="Language",
            options=(("en-US", "English"), ("pt-BR", "Português (Brasil)")),
            current="en-US",
            on_select=lambda value: seen.append(("lang", value)),
        ),
    ]
    return seen, entries


def test_invoke_runs_a_plain_item() -> None:
    seen, entries = _calls()
    assert invoke_entry(entries, ["Load Collection"]) is True
    assert seen == ["load"]


def test_invoke_toggles_a_check_item_to_the_opposite_of_its_current_state() -> None:
    seen, entries = _calls()
    assert invoke_entry(entries, ["Check for updates"]) is True
    assert seen == [("check", False)]


@pytest.mark.parametrize("segment", ["pt-BR", "Português (Brasil)"])
def test_invoke_selects_a_radio_option_by_value_or_by_label(segment: str) -> None:
    # The harness quotes whichever it has: a caller scripting the app knows the
    # locale code, a caller reading `menu --list` sees the translated label.
    seen, entries = _calls()
    assert invoke_entry(entries, ["Language", segment]) is True
    assert seen == [("lang", "pt-BR")]


def test_invoke_rejects_unknown_paths_rather_than_guessing() -> None:
    seen, entries = _calls()
    assert invoke_entry(entries, ["Nope"]) is False
    assert invoke_entry(entries, ["Language", "de-DE"]) is False
    # A submenu is not itself activatable, and a leaf takes no extra segment.
    assert invoke_entry(entries, ["Language"]) is False
    assert invoke_entry(entries, ["Load Collection", "extra"]) is False
    assert invoke_entry(entries, []) is False
    assert seen == []


def test_describe_drops_separators_and_reports_state() -> None:
    _seen, entries = _calls()
    assert describe(entries) == [
        {"kind": "item", "label": "Load Collection"},
        {"kind": "check", "label": "Check for updates", "checked": True},
        {
            "kind": "radio",
            "label": "Language",
            "options": ["English", "Português (Brasil)"],
            "current": "en-US",
        },
    ]
