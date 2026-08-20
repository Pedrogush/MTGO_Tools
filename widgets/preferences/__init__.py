"""The app's preferences: a data spec plus the dialog that renders it."""

from widgets.preferences.dialog import (
    PREFERENCES_DIALOG_WIDTH,
    PreferencesDialog,
    show_preferences_dialog,
)
from widgets.preferences.spec import (
    Preference,
    PreferenceGroup,
    apply_preference,
    describe,
    find_preference,
)

__all__ = [
    "PREFERENCES_DIALOG_WIDTH",
    "Preference",
    "PreferenceGroup",
    "PreferencesDialog",
    "apply_preference",
    "describe",
    "find_preference",
    "show_preferences_dialog",
]
