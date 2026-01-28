"""Ownership status formatting helpers."""

from __future__ import annotations


def format_owned_status(owned: int, required: int) -> tuple[str, tuple[int, int, int]]:
    """Return a display label and RGB color for owned vs required counts."""
    if owned >= required:
        return (f"Owned {owned}/{required}", (120, 200, 120))
    if owned > 0:
        return (f"Owned {owned}/{required}", (230, 200, 90))
    return (f"Owned 0/{required}", (230, 120, 120))
