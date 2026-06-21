"""Test helper utilities for managing global state in tests.

This module provides utilities for resetting global service and repository
instances to ensure test isolation and prevent state leakage between tests.
"""

import sys
import warnings
from pathlib import Path

# Add parent directory to sys.path to enable imports from repositories and services
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))


# ruff: noqa: E402
def _noop(*_args, **_kwargs):
    return None


def _optional_reset(module_path: str, attr_name: str):
    """Dynamically import a reset function, falling back to a no-op.

    The fallback exists so the test suite still collects in environments where
    an optional dependency (e.g. ``wx``) is unavailable and the target module
    cannot be imported. To avoid masking real regressions, only the expected
    import/attribute failures are tolerated, and any fallback that is *not*
    caused by a genuinely missing optional dependency is surfaced as a warning
    so that a renamed/removed/relocated reset function is loud rather than a
    silently broken test-isolation no-op.
    """
    try:
        module = __import__(module_path, fromlist=[attr_name])
    except ImportError as exc:  # pragma: no cover - depends on installed deps
        # A missing optional dependency (the module that failed to import is
        # not the target module itself) is the expected, benign fallback case.
        missing = getattr(exc, "name", None)
        if missing is not None and missing != module_path:
            return _noop
        warnings.warn(
            f"Could not import reset module {module_path!r}; test isolation for "
            f"{attr_name!r} is disabled (using a no-op).",
            stacklevel=2,
        )
        return _noop

    try:
        return getattr(module, attr_name)
    except AttributeError:
        warnings.warn(
            f"{module_path!r} has no attribute {attr_name!r}; test isolation for "
            f"this singleton is disabled (using a no-op). It may have been "
            f"renamed or removed.",
            stacklevel=2,
        )
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
reset_comp_rules_service = _optional_reset(
    "services.comp_rules_service", "reset_comp_rules_service"
)
reset_card_service = _optional_reset("services.card_service", "reset_card_service")
reset_metagame_service = _optional_reset("services.metagame_service", "reset_metagame_service")
reset_radar_service = _optional_reset("services.radar_service", "reset_radar_service")
reset_remote_snapshot_client = _optional_reset(
    "repositories.remote_snapshot_client", "reset_remote_snapshot_client"
)
reset_deck_cache = _optional_reset("repositories.deck_text_cache", "reset_deck_cache")


def reset_all_services() -> None:
    """Reset all global service instances."""
    reset_bundle_snapshot_client()
    reset_card_service()
    reset_collection_service()
    reset_comp_rules_service()
    reset_deck_service()
    reset_format_card_pool_service()
    reset_metagame_service()
    reset_radar_service()
    reset_search_service()
    reset_image_service()


def reset_all_repositories() -> None:
    """Reset all global repository instances."""
    reset_card_repository()
    reset_deck_repository()
    reset_deck_cache()
    reset_format_card_pool_repository()
    reset_metagame_repository()
    reset_radar_repository()
    reset_remote_snapshot_client()


def reset_all_globals() -> None:
    """Reset all global service and repository instances.

    This is the recommended function to call in test teardown or setup
    to ensure complete isolation between tests.
    """
    reset_all_services()
    reset_all_repositories()
