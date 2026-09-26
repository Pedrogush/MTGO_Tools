"""Pure (wx-independent) card-rendering helpers for the deck views.

These were originally instance methods on ``CardBoxPanel``; they moved here when
the grid view migrated from per-card native widgets to a single custom-drawn
canvas (:class:`DeckGridView`). Keeping them as free functions makes them easy
to unit-test and lets the canvas reuse the exact DFC image-lookup and
color-resolution logic the old grid cells used.

:func:`load_card_face` is here for the same reason: every view that draws a card
face has to turn a file on disk into pixels at the size it draws them, and doing
that in more than one way is how one view ends up softer than another.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image as PilImage

from widgets.mana_icon_factory import ManaIconFactory


def load_card_face(path: str | Path, width: int, height: int) -> PilImage.Image:
    """Open a card image and resize it to fit a ``width`` x ``height`` box.

    The one resize a card face gets, in one place. It is a **single** LANCZOS
    step from the file straight to the size the card is drawn at: decoding to
    some intermediate size and scaling again from there resamples twice, and the
    second pass is what leaves a card visibly softer than the same card
    elsewhere in the app.

    Scaled to *fit*, never to fill, so the source's own proportions win over the
    caller's box -- a card whose aspect differs from the box by a pixel is
    letterboxed by that pixel rather than stretched. Callers draw the result
    centred in the box they asked for.

    Runs on a decode thread in every caller, so it only reads.
    """
    image = PilImage.open(str(path)).convert("RGB")
    w, h = image.size
    scale = min(width / w, height / h)
    return image.resize((max(1, int(w * scale)), max(1, int(h * scale))), PilImage.LANCZOS)


def build_image_name_candidates(card: dict[str, Any], meta: Any) -> list[str]:
    """Return the ordered card-image lookup names for ``card``.

    The image DB stores face-0 entries under the combined DFC name reliably;
    individual face names can collide with same-named back faces of other
    printings (e.g. "Witch Enchanter" also appears as face_index=1 of a
    different card). So when ``card["name"]`` is a single face name (no "//")
    and ``meta.name`` is the combined name, the combined name is promoted to the
    front of the candidate list.
    """
    candidates: list[str] = []
    base_name = card.get("name")
    if base_name:
        candidates.append(base_name)
    aliases = meta.get("aliases") if meta is not None else None
    if isinstance(aliases, list):
        for alias in aliases:
            if alias and alias not in candidates:
                candidates.append(alias)
    if base_name and "//" not in base_name and meta is not None:
        meta_name = meta.get("name")
        if meta_name and "//" in meta_name and meta_name in candidates:
            candidates.remove(meta_name)
            candidates.insert(0, meta_name)
    return candidates


def resolve_card_color(meta: dict[str, Any]) -> tuple[int, int, int]:
    """Resolve the placeholder-template background color for a card's metadata."""
    identity = meta.get("color_identity") or meta.get("colors") or []
    normalized = [str(c).lower() for c in identity if c]
    if not normalized:
        return ManaIconFactory.FALLBACK_COLORS["c"]
    if len(normalized) == 1:
        return ManaIconFactory.FALLBACK_COLORS.get(
            normalized[0], ManaIconFactory.FALLBACK_COLORS["c"]
        )
    return ManaIconFactory.FALLBACK_COLORS["multicolor"]
