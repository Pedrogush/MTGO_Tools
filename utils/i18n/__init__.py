"""Localization helpers for lightweight UI string translation."""

from __future__ import annotations

from typing import Final, Literal

from utils.i18n._en_us import MESSAGES as _EN_US
from utils.i18n._pt_br import MESSAGES as _PT_BR

LocaleCode = Literal["en-US", "pt-BR"]

DEFAULT_LOCALE: Final[LocaleCode] = "en-US"
SUPPORTED_LOCALES: Final[tuple[LocaleCode, ...]] = ("en-US", "pt-BR")

LOCALE_LABELS: Final[dict[LocaleCode, str]] = {
    "en-US": "English",
    "pt-BR": "Português (Brasil)",
}

MESSAGES: Final[dict[LocaleCode, dict[str, str]]] = {
    "en-US": _EN_US,
    "pt-BR": _PT_BR,
}


def normalize_locale(locale: str | None) -> LocaleCode:
    """Normalize locale values to the supported locale set."""
    if locale in SUPPORTED_LOCALES:
        return locale
    return DEFAULT_LOCALE


def translate(locale: str | None, key: str, **kwargs: object) -> str:
    """Return a translated string with fallback to default locale and key text."""
    normalized = normalize_locale(locale)
    template = MESSAGES.get(normalized, {}).get(key)
    if template is None:
        template = MESSAGES[DEFAULT_LOCALE].get(key)
    if template is None:
        return key
    if not kwargs:
        return template
    return template.format(**kwargs)


# ---------------------------------------------------------------------------
# The ambient locale
# ---------------------------------------------------------------------------
# Most of the app passes a locale explicitly: every frame that a controller
# builds is handed one, and ``_t`` on that frame closes over it. Seven top-level
# windows are not built that way -- the diagnostics, guide-entry, import-options,
# offline-images and mana-keyboard windows are opened from wherever the user
# happens to be, the comp-rules popup is opened by a link inside rendered HTML,
# and the splash frame exists before a controller does. All seven carried
# hard-coded English titles (found by phase 4 of issue #962) and none of them has
# a locale to hand.
#
# Threading one through seven constructors would have been seven signatures
# changed to carry a value that is, in fact, process-global: there is one
# language setting and changing it re-translates the running UI. So the process
# keeps it. ``translate()`` still takes an explicit locale and is unchanged --
# this is a default for callers that genuinely have none, not a replacement.

_current_locale: LocaleCode = DEFAULT_LOCALE


def set_current_locale(locale: str | None) -> LocaleCode:
    """Record the language the app is running in. Returns the normalized value.

    Called from :meth:`controllers.app_controller.settings.SettingsMixin.set_language`
    and once at controller construction, so it tracks both the restored setting
    and every later change.
    """
    global _current_locale
    _current_locale = normalize_locale(locale)
    return _current_locale


def current_locale() -> LocaleCode:
    """The language the app is running in, defaulting to :data:`DEFAULT_LOCALE`."""
    return _current_locale


def t(key: str, **kwargs: object) -> str:
    """:func:`translate` against the ambient locale, for callers that have none."""
    return translate(_current_locale, key, **kwargs)


#: The plural categories this module supports. Both shipped locales -- en-US and
#: pt-BR -- use the same rule (exactly one, or everything else), so a key needs
#: exactly two forms. A locale with a richer rule (Russian's few/many, Polish,
#: Arabic's zero/two) would need a real per-locale CLDR rule here rather than
#: another ``if``; the two-form assumption is asserted by tests/test_i18n.py.
PLURAL_CATEGORIES: Final[tuple[str, str]] = ("one", "other")


def translate_plural(locale: str | None, key_base: str, count: int, **kwargs: object) -> str:
    """Translate ``f"{key_base}.one"`` or ``f"{key_base}.other"`` for *count*.

    The count is passed to the template as ``{n}``, so the number's position
    inside the string is the translator's decision rather than the caller's.

    This exists because the deck-count label was built as
    ``f"{total} card{'s' if total != 1 else ''}"`` -- English pluralisation
    compiled into the layout, in the one string phase 7 made responsible for
    ellipsising. Programmer pluralisation does not merely fail to translate; it
    silently produces "1 cards" the moment a locale disagrees with English about
    where the boundary is.
    """
    category = "one" if abs(count) == 1 else "other"
    return translate(locale, f"{key_base}.{category}", n=count, **kwargs)
