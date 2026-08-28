"""The UI suite's metagame reads must resolve from fakes, never from the wire.

``pytest tests/ui`` used to make real MTGGoldfish and Scryfall requests. The
conftest faked ``repositories.scrapers.mtggoldfish.get_archetypes`` and
``get_archetype_decks``, but :mod:`repositories.metagame_repository` re-exports
those names into its *own* namespace at import time, and every mixin that needs
them looks them up there (``_pkg.get_archetypes(...)``). Rebinding the scraper
module left the package's copies pointing at the real functions, so the three
production entry points below went straight to ``www.mtggoldfish.com``.

These tests drive the real :class:`MetagameRepository` — no repository fake, per
``tests/README.md`` §1 — and assert two things at once: that the fixture data
comes back (so the fake is genuinely the function being called) and that the
session-scoped tripwire recorded nothing (so no request escaped).
"""

from __future__ import annotations

from typing import Any

import pytest

import repositories.scrapers.mtggoldfish as mtggoldfish
from repositories.metagame_repository import MetagameRepository


@pytest.fixture(name="repo")
def fixture_repo(tmp_path, monkeypatch: pytest.MonkeyPatch) -> MetagameRepository:
    """A real repository (``tests/README.md`` §1) over a guaranteed-cold cache.

    Constructed directly, with its two cache files injected, rather than taken
    from ``get_metagame_repository()``: every layer of caching between the call
    and the scraper has to be cold, or these tests pass whether or not the fake
    is in place.

    ``repositories.scrapers.mtggoldfish`` is the other such layer. It binds its
    own JSON cache paths with ``from utils.constants import ...`` at module
    scope, so the UI conftest's rebind of ``utils.constants`` never reaches them
    and the scraper keeps reading the developer's real ``cache/`` — a separate
    isolation leak, not fixed here. Redirect them so the call under test has
    nowhere to go but the fake.
    """
    monkeypatch.setattr(
        mtggoldfish, "ARCHETYPE_LIST_CACHE_FILE", tmp_path / "archetype_list.json", raising=False
    )
    monkeypatch.setattr(
        mtggoldfish,
        "ARCHETYPE_DECKS_CACHE_FILE",
        tmp_path / "archetype_decks.json",
        raising=False,
    )
    return MetagameRepository(
        archetype_list_cache_file=tmp_path / "repo_archetype_list.json",
        archetype_decks_cache_file=tmp_path / "repo_archetype_decks.json",
    )


def test_archetype_listing_resolves_from_the_fake(repo, blocked_network) -> None:
    """``get_archetypes_for_format`` -> ``archetype_resolution._pkg.get_archetypes``."""
    archetypes = repo.get_archetypes_for_format("modern", force_refresh=True)

    assert [a["name"] for a in archetypes] == ["Mono Red Aggro", "Azorius Control"]
    assert blocked_network.attempts == []


def test_deck_listing_resolves_from_the_fake(repo, blocked_network) -> None:
    """``get_decks_for_archetype`` -> ``deck_operations._pkg.get_archetype_decks``."""
    decks = repo.get_decks_for_archetype(
        {"name": "Azorius Control", "href": "azorius-control"}, force_refresh=True
    )

    assert [d["player"] for d in decks] == ["TestPilot"]
    assert blocked_network.attempts == []


def test_deck_text_download_resolves_from_the_fake(repo, blocked_network) -> None:
    """``download_deck_content`` -> ``deck_operations._pkg.fetch_deck_text``.

    The deck number is deliberately not a real MTGGoldfish id: ``fetch_deck_text``
    consults a SQLite deck cache whose path is baked into a constructor default
    and so escapes the conftest's redirect, and a warm entry there would hide a
    missing fake.
    """
    text = repo.download_deck_content(
        {"name": "Azorius Control", "number": "ui-network-guard-probe"}
    )

    assert "4 Mountain" in text
    assert blocked_network.attempts == []


def test_background_refresh_resolves_from_the_fake(repo, blocked_network) -> None:
    """The stale-while-revalidate thread uses ``background._pkg.get_archetypes``.

    Joined explicitly: the refresh runs on a daemon thread, and an unjoined one
    would be doing its network call after the test's own assertions had passed.
    """
    import threading

    received: list[list[dict[str, Any]]] = []
    done = threading.Event()

    def _capture(fresh: list[dict[str, Any]]) -> None:
        received.append(fresh)
        done.set()

    repo._trigger_background_refresh("modern", _capture)
    assert done.wait(timeout=10), "background refresh never completed"

    assert [a["name"] for a in received[0]] == ["Mono Red Aggro", "Azorius Control"]
    assert blocked_network.attempts == []
