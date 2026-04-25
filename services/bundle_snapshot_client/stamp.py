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

    def _is_stamp_fresh(self) -> bool:
        if not self.stamp_file.exists():
            return False
        try:
            data = json.loads(self.stamp_file.read_text(encoding="utf-8"))
            applied_at = float(data.get("applied_at", 0))
            return (time.time() - applied_at) < self.max_age
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.debug(f"Could not read bundle stamp: {exc}")
            return False

    def _write_stamp(self, generated_at: str, applied_at: float) -> None:
        try:
            REMOTE_SNAPSHOT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self.stamp_file.write_text(
                json.dumps({"generated_at": generated_at, "applied_at": applied_at}, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning(f"Could not write bundle stamp: {exc}")
