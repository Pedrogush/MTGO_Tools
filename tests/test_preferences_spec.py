"""The preferences are data, so they can be tested without a dialog.

Phase 7 (#962) collapsed the ``Settings`` menu into a modal dialog.
``wx.Dialog.ShowModal`` runs a nested loop on the main thread and stops the
automation socket being serviced -- the same defect ``wx.PopupMenu`` has (review
§5.5) -- so the harness drives :mod:`widgets.preferences.spec` directly and never
opens the dialog. This module is the contract the dialog and the harness sit on.
"""

from __future__ import annotations

import pytest

from widgets.preferences.spec import (
    Preference,
    PreferenceGroup,
    apply_preference,
    describe,
    find_preference,
)


def _groups() -> tuple[list[object], list[PreferenceGroup]]:
    seen: list[object] = []
    groups = [
        PreferenceGroup(
            title="Application",
            items=(
                Preference(
                    key="language",
                    label="Language",
                    help="Applies immediately.",
                    options=(("en-US", "English"), ("pt-BR", "Português (Brasil)")),
                    current="en-US",
                    on_select=lambda value: seen.append(("lang", value)),
                ),
                Preference(
                    key="check_for_updates",
                    kind="toggle",
                    label="Check for updates",
                    checked=True,
                    on_toggle=lambda value: seen.append(("updates", value)),
                ),
            ),
        )
    ]
    return seen, groups


def test_find_preference_looks_across_groups() -> None:
    _seen, groups = _groups()
    assert find_preference(groups, "check_for_updates") is not None
    assert find_preference(groups, "nope") is None


@pytest.mark.parametrize("value", ["pt-BR", "Português (Brasil)"])
def test_a_choice_is_settable_by_value_or_by_translated_label(value: str) -> None:
    # A caller scripting the app knows the value; a caller reading ``describe``
    # sees the label. Same rule the menu spec follows.
    seen, groups = _groups()
    assert apply_preference(groups, "language", value) is True
    assert seen == [("lang", "pt-BR")]


@pytest.mark.parametrize(
    ("value", "expected"),
    [("on", True), ("true", True), ("1", True), ("off", False), ("no", False), ("toggle", False)],
)
def test_a_toggle_accepts_the_usual_words_and_flips_on_toggle(value: str, expected: bool) -> None:
    seen, groups = _groups()
    assert apply_preference(groups, "check_for_updates", value) is True
    assert seen == [("updates", expected)]


def test_unknown_keys_and_values_are_refused_rather_than_guessed() -> None:
    seen, groups = _groups()
    assert apply_preference(groups, "language", "de-DE") is False
    assert apply_preference(groups, "nope", "on") is False
    assert seen == []


def test_describe_is_json_safe_and_carries_current_state() -> None:
    _seen, groups = _groups()
    assert describe(groups) == [
        {
            "title": "Application",
            "items": [
                {
                    "key": "language",
                    "kind": "choice",
                    "label": "Language",
                    "help": "Applies immediately.",
                    "options": ["English", "Português (Brasil)"],
                    "values": ["en-US", "pt-BR"],
                    "current": "en-US",
                },
                {
                    "key": "check_for_updates",
                    "kind": "toggle",
                    "label": "Check for updates",
                    "checked": True,
                },
            ],
        }
    ]


def test_the_menu_bar_no_longer_carries_a_settings_menu() -> None:
    """#968 put ``Settings`` in the bar "so that phase 7 can collapse it".

    Guard against it coming back alongside the dialog, which would put the same
    five settings in two places and let them disagree.
    """
    import inspect

    from widgets.frames.app_frame.handlers import app_frame as handlers

    source = inspect.getsource(handlers)
    assert "_settings_menu_entries" not in source
    assert 'self._t("menu.settings")' not in source
