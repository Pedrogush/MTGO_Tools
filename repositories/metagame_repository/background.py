"""Background archetype refresh thread for stale-while-revalidate reads."""

from __future__ import annotations

import repositories.metagame_repository as _pkg
import threading
from collections.abc import Callable
from typing import Any

from loguru import logger


class BackgroundRefreshMixin:
    """Spawn daemon threads that refresh the archetype cache without blocking."""

    def _trigger_background_refresh(
        self, mtg_format: str, callback: Callable[[list[dict[str, Any]]], None]
    ) -> None:
        """Fetch fresh archetypes in a daemon thread and call *callback* on success.

        Resolution order mirrors the main fetch (remote snapshot → live scrape).
        On failure the exception is logged and *callback* is not invoked.
        """

        def _do_refresh() -> None:
            try:
                remote = self._remote_client_or_default()
                if remote is not None:
                    try:
                        fresh = remote.get_archetypes_for_format(mtg_format)
                        if fresh is not None:
                            self._save_cached_archetypes(mtg_format, fresh)
                            callback(fresh)
                            return
                    except Exception:
                        pass
                fresh = _pkg.get_archetypes(mtg_format)
                self._save_cached_archetypes(mtg_format, fresh)
                callback(fresh)
            except Exception as exc:
                logger.warning(f"[background-refresh] archetypes for {mtg_format} failed: {exc}")

        threading.Thread(
            target=_do_refresh, daemon=True, name=f"archetype-bg-{mtg_format}"
        ).start()
