"""Every i18n key the app asks for by name must exist in the message tables.

``translate`` returns the *key itself* when it can't find one, so a typo or an
omission is not an exception, a log line, or a blank label — it is the literal
string ``guide.record.curated_prompt`` rendered on screen at full size, in the
place a sentence should be. That is exactly what shipped: the sideboard-guide
record walk's matchup picker carried that prompt in neither locale from the day
the feature landed (#782) until it was noticed while driving the flow by hand
for #1027. Nothing failed; the dialog simply displayed the key.

The scan is static, so it can only see keys written as literals at the call
site — ``self._t("app.status.ready")`` and friends. Keys assembled at runtime
(a variable, an f-string, the ``labels={...}`` dicts a panel is handed) are out
of its reach by construction, and the count assertion below is what keeps
"covers 389 sites" from silently decaying into "covers 3".

The companion check is that the two locale tables carry the *same* key set. A
missing pt-BR key degrades to the en-US string rather than to a raw key, which
is far less visible than the failure above and therefore easier to leave in
place — and half-fixing a missing key by adding it to en-US only is the most
likely way to reintroduce this bug.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from utils.i18n import MESSAGES, PLURAL_CATEGORIES, SUPPORTED_LOCALES

ROOT = Path(__file__).resolve().parent.parent

#: Package directories that make up the app itself. ``tests`` is excluded (its
#: literals are fixtures, and some are deliberately absent keys), and so is
#: anything outside these roots -- notably ``.claude/worktrees``, which holds
#: whole copies of the tree whose i18n tables are not the ones we ship.
SOURCE_DIRS = (
    "automation",
    "controllers",
    "repositories",
    "services",
    "utils",
    "widgets",
)

#: Callables whose first string-literal argument is an i18n key. ``_t`` is the
#: per-widget helper; ``t`` is the same helper passed by keyword into the
#: dialogs and bars that don't own a locale (see ``_GuideRecordBar``).
_KEY_FIRST = {"_t", "t", "_t_plural"}

#: Callables taking ``(locale, key, ...)`` -- the module-level entry points and
#: the aliases panels import them under.
_KEY_SECOND = {
    "translate",
    "translate_plural",
    "_i18n_translate",
    "_i18n_translate_plural",
}

#: The smallest number of literal call sites this scan is allowed to find. A
#: refactor may legitimately move sites around; a walk that quietly stopped
#: finding them would otherwise leave every assertion below passing on nothing.
_MIN_CALL_SITES = 300


def _source_files() -> list[Path]:
    files: list[Path] = []
    for name in SOURCE_DIRS:
        files.extend(p for p in (ROOT / name).rglob("*.py") if "__pycache__" not in p.parts)
    files.append(ROOT / "main.py")
    return sorted(files)


def _called_name(node: ast.Call) -> str | None:
    """The bare name of the callable in ``node``, attribute access included."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _literal_key_sites(source: str) -> list[tuple[int, str, bool]]:
    """``(lineno, key, is_plural)`` for every literal i18n key in ``source``."""
    sites: list[tuple[int, str, bool]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = _called_name(node)
        if name in _KEY_FIRST:
            index = 0
        elif name in _KEY_SECOND:
            index = 1
        else:
            continue
        if len(node.args) <= index:
            continue  # keyword-passed or computed; not statically readable
        arg = node.args[index]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            sites.append((node.lineno, arg.value, "plural" in name))
    return sites


def _requested_keys() -> list[tuple[str, int, str]]:
    """``(relative path, lineno, key)`` for every key the app asks for by name.

    A plural call site expands to the two keys ``translate_plural`` actually
    looks up, since a base with only ``.other`` defined fails on exactly one
    count and is otherwise invisible.
    """
    requested: list[tuple[str, int, str]] = []
    for path in _source_files():
        rel = path.relative_to(ROOT).as_posix()
        for lineno, key, is_plural in _literal_key_sites(path.read_text(encoding="utf-8")):
            if is_plural:
                requested.extend((rel, lineno, f"{key}.{c}") for c in PLURAL_CATEGORIES)
            else:
                requested.append((rel, lineno, key))
    return requested


def test_the_scan_finds_the_call_sites_it_claims_to_cover() -> None:
    """Guard the guard: a walk that found nothing would pass every check below."""
    assert len(_requested_keys()) >= _MIN_CALL_SITES


def test_every_literal_i18n_key_exists_in_the_message_table() -> None:
    """The bug this file exists for: a key with no entry renders as itself."""
    known = set(MESSAGES["en-US"])
    missing = sorted(
        f"{rel}:{lineno} asks for {key!r}"
        for rel, lineno, key in _requested_keys()
        if key not in known
    )
    assert missing == [], (
        "these keys have no entry, so translate() returns the key itself and the "
        "app renders it verbatim on screen:\n  " + "\n  ".join(missing)
    )


def test_a_key_absent_from_the_table_is_actually_reported() -> None:
    """Positive self-test, using the site that shipped broken (#782 → #1027).

    Without this, a scan that regressed to returning ``[]`` -- or a set
    membership test that always succeeded -- would leave the guard above green
    forever.
    """
    known = set(MESSAGES["en-US"]) - {"guide.record.curated_prompt"}
    missing = [(rel, key) for rel, _lineno, key in _requested_keys() if key not in known]
    assert missing == [
        (
            "widgets/frames/app_frame/handlers/sideboard_guide_record.py",
            "guide.record.curated_prompt",
        )
    ]


@pytest.mark.parametrize("locale", sorted(SUPPORTED_LOCALES))
def test_every_locale_carries_the_same_keys(locale: str) -> None:
    """A key added to one table only falls back silently to the other's string."""
    default = set(MESSAGES["en-US"])
    theirs = set(MESSAGES[locale])
    assert sorted(default - theirs) == [], f"{locale} is missing keys en-US defines"
    assert sorted(theirs - default) == [], f"{locale} defines keys en-US does not"
