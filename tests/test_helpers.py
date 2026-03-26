"""Test helper utilities for managing global state in tests.

This module provides utilities for resetting global service and repository
instances to ensure test isolation and prevent state leakage between tests.
"""

import sys
from pathlib import Path

# Add parent directory to sys.path to enable imports from repositories and services
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))


# ruff: noqa: E402
def _optional_reset(module_path: str, attr_name: str):
    """Dynamically import a reset function, falling back to a no-op."""
    try:
        module = __import__(module_path, fromlist=[attr_name])
        return getattr(module, attr_name)
    except Exception:  # pragma: no cover - used in CI without optional deps

        def _noop(*_args, **_kwargs):
            return None

        return _noop


reset_card_repository = _optional_reset("repositories.card_repository", "reset_card_repository")
reset_deck_repository = _optional_reset("repositories.deck_repository", "reset_deck_repository")
reset_format_card_pool_repository = _optional_reset(
    "repositories.format_card_pool_repository", "reset_format_card_pool_repository"
)
reset_metagame_repository = _optional_reset(
    "repositories.metagame_repository", "reset_metagame_repository"
)
reset_radar_repository = _optional_reset("repositories.radar_repository", "reset_radar_repository")
reset_bundle_snapshot_client = _optional_reset(
    "services.bundle_snapshot_client", "reset_bundle_snapshot_client"
)
reset_deck_service = _optional_reset("services.deck_service", "reset_deck_service")
reset_format_card_pool_service = _optional_reset(
    "services.format_card_pool_service", "reset_format_card_pool_service"
)
reset_image_service = _optional_reset("services.image_service", "reset_image_service")
reset_search_service = _optional_reset("services.search_service", "reset_search_service")
reset_collection_service = _optional_reset(
    "services.collection_service", "reset_collection_service"
)


def reset_all_services() -> None:
    """Reset all global service instances."""
    reset_bundle_snapshot_client()
    reset_collection_service()
    reset_deck_service()
    reset_format_card_pool_service()
    reset_search_service()
    reset_image_service()


def reset_all_repositories() -> None:
    """Reset all global repository instances."""
    reset_card_repository()
    reset_deck_repository()
    reset_format_card_pool_repository()
    reset_metagame_repository()
    reset_radar_repository()


def reset_all_globals() -> None:
    """Reset all global service and repository instances.

    This is the recommended function to call in test teardown or setup
    to ensure complete isolation between tests.
    """
    reset_all_services()
    reset_all_repositories()
