"""Tests for archetype resolver utility."""

import json
from pathlib import Path

import pytest

from utils.archetype_resolver import find_archetype_by_name, normalize_archetype_name

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Minimal stub — no MagicMock needed for a pure-function test
# ---------------------------------------------------------------------------


class _FakeRepo:
    """Minimal stand-in for MetagameRepository that serves a fixed archetype list."""

    def __init__(self, archetypes: list[dict]) -> None:
        self._archetypes = archetypes

    def get_archetypes_for_format(self, _format: str) -> list[dict]:
        return self._archetypes


class _ErrorRepo:
    """Stub that always raises on get_archetypes_for_format."""

    def get_archetypes_for_format(self, _format: str) -> list[dict]:
        raise Exception("Network error")


# ---------------------------------------------------------------------------
# Fixture archetypes (real MTGGoldfish Modern names)
# ---------------------------------------------------------------------------

_FIXTURE_ARCHETYPES: list[dict] = json.loads(
    (FIXTURES_DIR / "archetypes_modern.json").read_text(encoding="utf-8")
)

# Small inline list used by basic tests (unchanged from original intent)
_BASIC_ARCHETYPES = [
    {"name": "UR Murktide", "href": "/archetype/ur-murktide"},
    {"name": "Azorius Control", "href": "/archetype/azorius-control"},
    {"name": "Mono Black Midrange", "href": "/archetype/mono-black-midrange"},
]


# ---------------------------------------------------------------------------
# normalize_archetype_name
# ---------------------------------------------------------------------------


class TestNormalizeArchetypeName:
    def test_lowercase(self):
        assert normalize_archetype_name("UR Murktide") == "ur murktide"

    def test_strip_whitespace(self):
        assert normalize_archetype_name("  UR Murktide  ") == "ur murktide"

    def test_collapse_spaces(self):
        assert normalize_archetype_name("UR   Murktide") == "ur murktide"

    def test_empty_string(self):
        assert normalize_archetype_name("") == ""


# ---------------------------------------------------------------------------
# find_archetype_by_name — basic list
# ---------------------------------------------------------------------------


class TestFindArchetypeByName:
    @pytest.fixture
    def repo(self):
        return _FakeRepo(_BASIC_ARCHETYPES)

    def test_exact_match(self, repo):
        result = find_archetype_by_name("UR Murktide", "Modern", repo)
        assert result is not None
        assert result["name"] == "UR Murktide"

    def test_case_insensitive_match(self, repo):
        result = find_archetype_by_name("ur murktide", "Modern", repo)
        assert result is not None
        assert result["name"] == "UR Murktide"

    def test_no_match(self, repo):
        result = find_archetype_by_name("Jund Saga", "Modern", repo)
        assert result is None

    def test_partial_match(self, repo):
        result = find_archetype_by_name("Murktide", "Modern", repo)
        assert result is not None
        assert result["name"] == "UR Murktide"

    def test_network_failure(self):
        result = find_archetype_by_name("UR Murktide", "Modern", _ErrorRepo())
        assert result is None

    def test_empty_archetype_list(self):
        result = find_archetype_by_name("UR Murktide", "Modern", _FakeRepo([]))
        assert result is None


# ---------------------------------------------------------------------------
# find_archetype_by_name — real MTGGoldfish fixture names
# ---------------------------------------------------------------------------


class TestFindArchetypeByNameRealData:
    """Ensure fuzzy matching works against real MTGGoldfish archetype name formats."""

    @pytest.fixture
    def repo(self):
        return _FakeRepo(_FIXTURE_ARCHETYPES)

    def test_exact_match_tron(self, repo):
        result = find_archetype_by_name("Tron", "Modern", repo)
        assert result is not None
        assert result["name"] == "Tron"

    def test_exact_match_living_end(self, repo):
        result = find_archetype_by_name("Living End", "Modern", repo)
        assert result is not None
        assert result["name"] == "Living End"

    def test_case_insensitive_hammer_time(self, repo):
        result = find_archetype_by_name("hammer time", "Modern", repo)
        assert result is not None
        assert result["name"] == "Hammer Time"

    def test_partial_match_yawgmoth(self, repo):
        result = find_archetype_by_name("Yawgmoth", "Modern", repo)
        assert result is not None
        assert result["name"] == "Yawgmoth"

    def test_partial_match_amulet(self, repo):
        result = find_archetype_by_name("Amulet", "Modern", repo)
        assert result is not None
        assert result["name"] == "Amulet Titan"

    def test_no_match_unknown_deck(self, repo):
        result = find_archetype_by_name("Jund Saga NonExistent", "Modern", repo)
        assert result is None
