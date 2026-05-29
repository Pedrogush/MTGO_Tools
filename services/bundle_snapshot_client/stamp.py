"""Stamp file freshness tracking for the bundle snapshot client."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from loguru import logger

from utils.constants import REMOTE_SNAPSHOT_CACHE_DIR

if TYPE_CHECKING:
    from services.bundle_snapshot_client.protocol import BundleSnapshotClientProto

    _Base = BundleSnapshotClientProto
else:
    _Base = object


class StampMixin(_Base):
    """Stamp file read/write for bundle freshness tracking."""

    def _read_stamp(self) -> dict[str, object]:
        """Return the parsed stamp file, or ``{}`` when missing/unreadable."""
        if not self.stamp_file.exists():
            return {}
        try:
            data = json.loads(self.stamp_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.debug(f"Could not read bundle stamp: {exc}")
            return {}

    def _is_stamp_fresh(self) -> bool:
        data = self._read_stamp()
        if not data:
            return False
        try:
            applied_at = float(data.get("applied_at", 0))
        except (TypeError, ValueError):
            return False
        return (time.time() - applied_at) < self.max_age

    def _write_stamp(
        self,
        generated_at: str,
        applied_at: float,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "generated_at": generated_at,
            "applied_at": applied_at,
        }
        if etag:
            payload["etag"] = etag
        if last_modified:
            payload["last_modified"] = last_modified
        try:
            REMOTE_SNAPSHOT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self.stamp_file.write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(f"Could not write bundle stamp: {exc}")
