"""Process-wide runtime flags set during application startup."""

from __future__ import annotations

_automation_enabled: bool = False


def set_automation_enabled(enabled: bool) -> None:
    global _automation_enabled
    _automation_enabled = bool(enabled)


def is_automation_enabled() -> bool:
    return _automation_enabled
