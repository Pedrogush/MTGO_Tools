"""Tests for archetype resolver utility.

These wire a real :class:`MetagameRepository` against ``tmp_path`` cache files
rather than mocking the repository, so the resolver exercises the production
cache-read and live-scrape-fallback paths. ``wx`` is only an indirect import of
the repository package (via ``utils.constants``) and is not importable in the
WSL dev environment, so a minimal stub is injected before the repository import;
on the Windows CI runner the real ``wx`` is used instead.
"""

import json
import sys
import time
import types
from typing import Any

import pytest


class _WxStub(types.ModuleType):
    """A permissive ``wx`` stand-in fabricating attributes on demand."""

    def __getattr__(self, name: str) -> Any:  # noqa: D401 - simple stub
        value: Any = type(name, (), {})
        setattr(self, name, value)
        return value


def _install_wx_stub() -> None:
    """Install a ``wx`` stub only when the real module is unavailable."""
    try:
        import wx  # noqa: F401
    except Exception:
        sys.modules["wx"] = _WxStub("wx")


_install_wx_stub()

import repositories.metagame_repository as metagame_pkg  # noqa: E402
from repositories.metagame_repository import MetagameRepository  # noqa: E402
from services.archetype_resolver import (  # noqa: E402
    find_archetype_by_name,
    normalize_archetype_name,
)


class TestNormalizeArchetypeName:
    def test_lowercase(self):
        assert normalize_archetype_name("UR Murktide") == "ur murktide"

    def test_strip_whitespace(self):
        assert normalize_archetype_name("  UR Murktide  ") == "ur murktide"

    def test_collapse_spaces(self):
        assert normalize_archetype_name("UR   Murktide") == "ur murktide"

    def test_collapse_tabs_and_newlines(self):
        assert normalize_archetype_name("UR\tMurktide\nTempo") == "ur murktide tempo"

    def test_empty_string(self):
        assert normalize_archetype_name("") == ""


def _write_archetype_cache(cache_file, mtg_format, items):
    """Seed a real archetype-list cache file with a fresh entry.

    With ``REMOTE_SNAPSHOTS_ENABLED`` disabled (the default), a fresh local
    cache short-circuits ``get_archetypes_for_format`` before any network
    access, so the repository runs its real cache-read path end to end.
    """
    payload = {mtg_format: {"timestamp": time.time(), "items": items}}
    cache_file.write_text(json.dumps(payload), encoding="utf-8")


class TestFindArchetypeByName:
    @pytest.fixture
    def cache_files(self, tmp_path):
        return (
            tmp_path / "archetype_cache.json",
            tmp_path / "archetype_decks_cache.json",
        )

    @pytest.fixture
    def repo(self, cache_files):
        """A real MetagameRepository backed by temp cache files."""
        archetype_cache_file, archetype_decks_cache_file = cache_files
        return MetagameRepository(
            cache_ttl=3600,
            archetype_list_cache_file=archetype_cache_file,
            archetype_decks_cache_file=archetype_decks_cache_file,
        )

    @pytest.fixture
    def seeded_repo(self, repo, cache_files):
        """Repository whose fresh cache holds the standard Modern archetypes."""
        archetype_cache_file, _ = cache_files
        _write_archetype_cache(
            archetype_cache_file,
            "Modern",
            [
                {"name": "UR Murktide", "href": "/archetype/ur-murktide"},
                {"name": "Azorius Control", "href": "/archetype/azorius-control"},
                {"name": "Mono Black Midrange", "href": "/archetype/mono-black-midrange"},
            ],
        )
        return repo

    def test_exact_match(self, seeded_repo):
        result = find_archetype_by_name("UR Murktide", "Modern", seeded_repo)
        assert result == {"name": "UR Murktide", "href": "/archetype/ur-murktide"}

    def test_case_insensitive_match(self, seeded_repo):
        result = find_archetype_by_name("ur murktide", "Modern", seeded_repo)
        assert result == {"name": "UR Murktide", "href": "/archetype/ur-murktide"}

    def test_no_match(self, seeded_repo):
        result = find_archetype_by_name("Jund Saga", "Modern", seeded_repo)
        assert result is None

    def test_partial_match(self, seeded_repo):
        result = find_archetype_by_name("Murktide", "Modern", seeded_repo)
        assert result == {"name": "UR Murktide", "href": "/archetype/ur-murktide"}

    def test_partial_match_stored_name_in_input(self, seeded_repo):
        # Reverse direction: stored name is a substring of the longer input,
        # exercising the `normalized_name in normalized_input` branch.
        result = find_archetype_by_name("UR Murktide Tempo", "Modern", seeded_repo)
        assert result == {"name": "UR Murktide", "href": "/archetype/ur-murktide"}

    def test_exact_match_takes_precedence_over_partial(self, repo, cache_files):
        # "Murktide" is a partial match for "UR Murktide" but an exact match
        # for the standalone "Murktide" entry; the exact match must win even
        # though the partial candidate appears first in the list.
        archetype_cache_file, _ = cache_files
        _write_archetype_cache(
            archetype_cache_file,
            "Modern",
            [
                {"name": "UR Murktide", "href": "/archetype/ur-murktide"},
                {"name": "Murktide", "href": "/archetype/murktide"},
            ],
        )
        result = find_archetype_by_name("Murktide", "Modern", repo)
        assert result == {"name": "Murktide", "href": "/archetype/murktide"}

    def test_scrape_failure_returns_none(self, repo, monkeypatch):
        # No cache file and no remote snapshot: the repository falls through to
        # the live MTGGoldfish scrape (a seam we don't own). Faking that seam to
        # raise drives the resolver's real except-branch -> None.
        def _boom(_mtg_format):
            raise RuntimeError("Network error")

        monkeypatch.setattr(metagame_pkg, "get_archetypes", _boom)
        result = find_archetype_by_name("UR Murktide", "Modern", repo)
        assert result is None

    def test_empty_archetype_list(self, repo, cache_files):
        archetype_cache_file, _ = cache_files
        _write_archetype_cache(archetype_cache_file, "Modern", [])
        result = find_archetype_by_name("UR Murktide", "Modern", repo)
        assert result is None

    def test_uses_default_repo_when_none(self, tmp_path, monkeypatch):
        """When no repo is passed, the default singleton repository is used."""
        archetype_cache_file = tmp_path / "default_archetype_cache.json"
        archetype_decks_cache_file = tmp_path / "default_archetype_decks_cache.json"
        _write_archetype_cache(
            archetype_cache_file,
            "Modern",
            [{"name": "UR Murktide", "href": "/archetype/ur-murktide"}],
        )

        # Point the package singleton factory at a real repo backed by the temp
        # cache. The resolver then exercises its real default-repo branch
        # (`repo = metagame_repo or get_metagame_repository()`) against a real
        # MetagameRepository and we assert on the returned value, not a call.
        default_repo = MetagameRepository(
            cache_ttl=3600,
            archetype_list_cache_file=archetype_cache_file,
            archetype_decks_cache_file=archetype_decks_cache_file,
        )
        monkeypatch.setattr(
            "services.archetype_resolver.get_metagame_repository",
            lambda: default_repo,
        )

        result = find_archetype_by_name("UR Murktide", "Modern")

        assert result == {"name": "UR Murktide", "href": "/archetype/ur-murktide"}
