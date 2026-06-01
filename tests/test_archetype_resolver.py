"""Tests for archetype resolver utility."""

from unittest.mock import MagicMock, patch

import pytest

from services.archetype_resolver import find_archetype_by_name, normalize_archetype_name


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


class TestFindArchetypeByName:
    @pytest.fixture
    def mock_repo(self):
        repo = MagicMock()
        repo.get_archetypes_for_format.return_value = [
            {"name": "UR Murktide", "href": "/archetype/ur-murktide"},
            {"name": "Azorius Control", "href": "/archetype/azorius-control"},
            {"name": "Mono Black Midrange", "href": "/archetype/mono-black-midrange"},
        ]
        return repo

    def test_exact_match(self, mock_repo):
        result = find_archetype_by_name("UR Murktide", "Modern", mock_repo)
        assert result is not None
        assert result["name"] == "UR Murktide"

    def test_case_insensitive_match(self, mock_repo):
        result = find_archetype_by_name("ur murktide", "Modern", mock_repo)
        assert result is not None
        assert result["name"] == "UR Murktide"

    def test_no_match(self, mock_repo):
        result = find_archetype_by_name("Jund Saga", "Modern", mock_repo)
        assert result is None

    def test_partial_match(self, mock_repo):
        result = find_archetype_by_name("Murktide", "Modern", mock_repo)
        assert result is not None
        assert result["name"] == "UR Murktide"

    def test_partial_match_stored_name_in_input(self, mock_repo):
        # Reverse direction: stored name is a substring of the longer input,
        # exercising the `normalized_name in normalized_input` branch.
        result = find_archetype_by_name("UR Murktide Tempo", "Modern", mock_repo)
        assert result is not None
        assert result["name"] == "UR Murktide"

    def test_exact_match_takes_precedence_over_partial(self):
        # "Murktide" is a partial match for "UR Murktide" but an exact match
        # for the standalone "Murktide" entry; the exact match must win even
        # though the partial candidate appears first in the list.
        repo = MagicMock()
        repo.get_archetypes_for_format.return_value = [
            {"name": "UR Murktide", "href": "/archetype/ur-murktide"},
            {"name": "Murktide", "href": "/archetype/murktide"},
        ]
        result = find_archetype_by_name("Murktide", "Modern", repo)
        assert result is not None
        assert result["name"] == "Murktide"

    def test_network_failure(self, mock_repo):
        mock_repo.get_archetypes_for_format.side_effect = Exception("Network error")
        result = find_archetype_by_name("UR Murktide", "Modern", mock_repo)
        assert result is None

    def test_empty_archetype_list(self, mock_repo):
        mock_repo.get_archetypes_for_format.return_value = []
        result = find_archetype_by_name("UR Murktide", "Modern", mock_repo)
        assert result is None

    def test_uses_default_repo_when_none(self):
        """When no repo is passed, the default singleton repository is used."""
        singleton = MagicMock()
        singleton.get_archetypes_for_format.return_value = [
            {"name": "UR Murktide", "href": "/archetype/ur-murktide"},
        ]
        with patch(
            "services.archetype_resolver.get_metagame_repository",
            return_value=singleton,
        ) as mock_get_repo:
            result = find_archetype_by_name("UR Murktide", "Modern")

        mock_get_repo.assert_called_once_with()
        singleton.get_archetypes_for_format.assert_called_once_with("Modern")
        assert result is not None
        assert result["name"] == "UR Murktide"
