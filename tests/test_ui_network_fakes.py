"""The UI conftest's network fakes must name what production actually calls.

The class of bug this pins
--------------------------
:mod:`repositories.metagame_repository` re-exports the MTGGoldfish scraper entry
points into its own namespace at import time, and its mixins deliberately look
them up *there* (``_pkg.get_archetypes(...)``) so tests have one place to swap
them. ``tests/ui/conftest.py`` patched only ``repositories.scrapers.mtggoldfish``,
which rebinds the scraper module's globals and leaves the package's copies bound
to the real functions — so every UI test that listed decks or opened one went to
``www.mtggoldfish.com`` for real.

That failure is invisible in a passing suite: the scrape succeeds, the assertions
still hold, and the only evidence is traffic. Nothing about the fix stops the
next name from being added to the re-export list and missed here, so this reads
both sides out of the source and compares them.

Source inspection on purpose: it is exact, costs milliseconds, and — unlike the
UI suite it guards — runs off Windows, where ``wx`` cannot even be imported.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from network_guard import NetworkAccessError, NetworkWatch, install_network_tripwire

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "repositories" / "metagame_repository"
UI_CONFTEST = ROOT / "tests" / "ui" / "conftest.py"

# The alias the package's mixins import themselves under for dynamic lookup.
PKG_ALIAS = "_pkg"


def _parse(path: Path) -> ast.Module:
    assert path.exists(), f"{path} is missing"
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _dynamic_lookups() -> dict[str, set[str]]:
    """``{module name: names read off the package at call time}``.

    Only modules that actually alias the package to :data:`PKG_ALIAS` count, so
    an unrelated local named ``_pkg`` elsewhere cannot pad the result.
    """
    found: dict[str, set[str]] = {}
    for path in sorted(PACKAGE.glob("*.py")):
        tree = _parse(path)
        aliases_package = any(
            isinstance(node, ast.Import)
            and any(
                alias.name == "repositories.metagame_repository" and alias.asname == PKG_ALIAS
                for alias in node.names
            )
            for node in ast.walk(tree)
        )
        if not aliases_package:
            continue
        names = {
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == PKG_ALIAS
        }
        if names:
            found[path.name] = names
    return found


def _package_reexports() -> set[str]:
    """Names ``__init__.py`` pulls in from the scrapers — i.e. the network ones."""
    tree = _parse(PACKAGE / "__init__.py")
    return {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and (node.module or "").startswith("repositories.scrapers")
        for alias in node.names
    }


def _conftest_patched_names() -> set[str]:
    """Attribute names the UI conftest patches on the metagame package.

    Matches ``monkeypatch.setattr(<pkg alias>, "<name>", ...)`` where the alias
    is whatever ``tests/ui/conftest.py`` imported the package as, so renaming the
    import cannot silently make this guard vacuous.
    """
    tree = _parse(UI_CONFTEST)
    aliases = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "repositories.metagame_repository"
    }
    assert aliases, "tests/ui/conftest.py no longer imports repositories.metagame_repository"

    patched: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "setattr"):
            continue
        if len(node.args) < 2:
            continue
        target, name = node.args[0], node.args[1]
        if isinstance(target, ast.Name) and target.id in aliases:
            if isinstance(name, ast.Constant) and isinstance(name.value, str):
                patched.add(name.value)
    return patched


def test_the_package_still_uses_dynamic_lookup() -> None:
    """Guard the guard: if ``_pkg.<name>`` disappears, this file must be rethought."""
    lookups = _dynamic_lookups()
    assert lookups, (
        "No module in repositories/metagame_repository looks names up off the "
        f"package as `{PKG_ALIAS}.<name>` any more. The re-export seam this "
        "guard checks has changed shape — revisit it rather than deleting it."
    )


@pytest.mark.parametrize("module", sorted(_dynamic_lookups()))
def test_every_dynamic_package_lookup_is_faked_by_the_ui_conftest(module: str) -> None:
    """Every name production resolves off the package must be a name we fake."""
    needed = _dynamic_lookups()[module]
    patched = _conftest_patched_names()
    missing = sorted(needed - patched)
    assert not missing, (
        f"repositories/metagame_repository/{module} resolves {missing} off the "
        "package namespace at call time, but tests/ui/conftest.py does not patch "
        f"{'them' if len(missing) > 1 else 'it'} there. Patching only "
        "repositories.scrapers.mtggoldfish leaves the package's import-time copy "
        "bound to the real function, and the UI suite goes on the network."
    )


def test_every_scraper_reexport_is_faked_by_the_ui_conftest() -> None:
    """The re-exported scraper entry points are exactly the network-touching ones."""
    reexports = _package_reexports()
    assert "get_archetypes" in reexports, "unexpected shape: __init__.py changed its re-exports"
    missing = sorted(reexports - _conftest_patched_names())
    assert not missing, (
        f"repositories/metagame_repository re-exports {missing} from the scrapers, "
        "but tests/ui/conftest.py does not fake them on the package namespace. "
        "Anything reachable through that namespace is a live HTTP call "
        "(tests/README.md §2)."
    )


# --- the tripwire itself ------------------------------------------------------
#
# The UI conftest's assertion is only worth as much as the recorder underneath
# it, and that recorder is only exercised on Windows. These run everywhere and
# make no real request: the first thing they do is take the transport away.


@pytest.mark.parametrize(
    ("call", "expected_host"),
    [
        pytest.param(
            lambda: __import__("requests").get("https://api.scryfall.com/cards/collection"),
            "api.scryfall.com",
            id="requests",
        ),
        pytest.param(
            lambda: __import__("curl_cffi.requests", fromlist=["get"]).get(
                "https://www.mtggoldfish.com/archetype/x/decks"
            ),
            "mtggoldfish.com",
            id="curl_cffi",
        ),
        pytest.param(
            lambda: __import__("urllib.request", fromlist=["urlopen"]).urlopen(
                "https://cards.scryfall.io/normal/front/a/b/c.jpg"
            ),
            "cards.scryfall.io",
            id="urllib",
        ),
    ],
)
def test_the_tripwire_blocks_and_records_each_transport(
    monkeypatch: pytest.MonkeyPatch, call, expected_host: str
) -> None:
    attempts = install_network_tripwire(monkeypatch)

    with pytest.raises(NetworkAccessError):
        call()

    assert len(attempts) == 1
    assert expected_host in attempts[0]


def test_the_watch_reports_only_calls_made_after_it_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-test attribution: an earlier test's leak is not charged to a later one."""
    import requests

    attempts = install_network_tripwire(monkeypatch)
    with pytest.raises(NetworkAccessError):
        requests.get("https://example.invalid/earlier")

    watch = NetworkWatch(attempts)
    assert watch.attempts == []
    assert not watch

    with pytest.raises(NetworkAccessError):
        requests.get("https://example.invalid/later")

    assert watch.attempts == ["requests.Session.request https://example.invalid/later"]
    assert watch
