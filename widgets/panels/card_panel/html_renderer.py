"""Pure helpers that render an MTG-card-like HTML view of a card.

Only standard library + ``re`` is used here — kept separate from any wx imports
so the helpers are unit-testable without a wx App.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from html import escape
from pathlib import Path
from typing import Any, Protocol

# Match either {SYMBOL} or a bare token previously normalized.
_MANA_TOKEN_RE = re.compile(r"\{([^{}]+)\}")
# Reminder text in MTG oracle text is parenthetical and italicized.
_REMINDER_RE = re.compile(r"\(([^)]+)\)")

# Colour used for keyword hyperlinks in the oracle text — picked to contrast
# against the dark panel background while staying close to the existing
# DARK_ACCENT in ``utils.constants.colors``.
_KEYWORD_LINK_COLOR = "#7AA2F7"

PngResolver = Callable[[str], Path | None]


class _KeywordEntryLike(Protocol):
    """Protocol mirroring ``services.comp_rules_service.KeywordEntry``.

    Defined locally so this renderer stays free of service-layer imports.
    """

    title: str
    rule_id: str


KeywordLookup = Mapping[str, _KeywordEntryLike]


def replace_mana_symbols(
    text: str,
    png_resolver: PngResolver,
    *,
    symbol_size: int = 18,
) -> str:
    """Replace ``{X}`` tokens in ``text`` with ``<img>`` tags.

    The text is HTML-escaped first so existing characters cannot inject markup.
    Tokens whose PNG cannot be resolved fall back to the literal ``{X}`` form
    so the user still sees the symbol verbatim.
    """
    if not text:
        return ""

    parts: list[str] = []
    last = 0
    for match in _MANA_TOKEN_RE.finditer(text):
        parts.append(escape(text[last : match.start()]))
        token = match.group(1).strip()
        png = png_resolver(token)
        if png is not None:
            uri = Path(png).resolve().as_uri()
            # ``align="absmiddle"`` centres the icon vertically on the text
            # line. Without it, wx.html.HtmlWindow hangs the image from the
            # baseline and the circle floats above the text below.
            parts.append(
                f'<img src="{uri}" width="{symbol_size}" height="{symbol_size}" '
                f'align="absbottom" alt="{{{escape(token)}}}">'
            )
        else:
            parts.append(escape(match.group(0)))
        last = match.end()
    parts.append(escape(text[last:]))
    return "".join(parts)


def _italicize_reminder_text(html: str) -> str:
    """Wrap parenthetical reminder text in ``<i>`` tags.

    Operates on already-escaped HTML — parens stay as raw chars after escape().
    """
    return _REMINDER_RE.sub(lambda m: f"<i>({m.group(1)})</i>", html)


# Tags whose text content should NOT be linkified. ``<i>`` covers reminder
# text (already a parenthetical explanation, no need to link the keyword
# inside its own gloss); ``<a>`` prevents nesting links.
_LINKIFY_SKIP_TAGS = frozenset({"i", "a"})
# Splits an HTML string into alternating text and tag tokens. The capture
# group keeps the tags themselves in the result of ``re.split``.
_TAG_SPLIT_RE = re.compile(r"(<[^>]+>)")
_TAG_NAME_RE = re.compile(r"<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9]*)")


def _build_keyword_pattern(lookup: KeywordLookup) -> re.Pattern[str] | None:
    """Compile a single regex matching any keyword title (longest-first).

    Returns None when the lookup is empty so callers can short-circuit.
    """
    titles = sorted({entry.title for entry in lookup.values()}, key=len, reverse=True)
    if not titles:
        return None
    # Word-boundary lookarounds keep ``trample`` from matching inside
    # ``trampled``; ``re.IGNORECASE`` lets ``Flying`` and ``flying`` both link.
    return re.compile(
        r"(?<!\w)(" + "|".join(re.escape(t) for t in titles) + r")(?!\w)",
        re.IGNORECASE,
    )


def _replace_keywords_in_text(
    text: str,
    pattern: re.Pattern[str],
    lookup: KeywordLookup,
) -> str:
    def _repl(match: re.Match[str]) -> str:
        matched = match.group(1)
        entry = lookup.get(matched.lower())
        if entry is None:
            return matched
        # ``<font>`` inside ``<a>`` so the link picks up our colour — wx.html
        # ignores ``color`` attrs on ``<a>`` but honours ``<font color>``.
        return (
            f'<a href="rule:{entry.rule_id}">'
            f'<font color="{_KEYWORD_LINK_COLOR}">{matched}</font>'
            f"</a>"
        )

    return pattern.sub(_repl, text)


def linkify_keywords(html: str, lookup: KeywordLookup) -> str:
    """Wrap keyword occurrences in ``<a href="rule:NNN">`` anchors.

    The pass walks the HTML token-by-token so it can skip text inside
    ``<i>`` (reminder text) and ``<a>`` (already a link) — those would
    either over-link the gloss or nest anchors.
    """
    if not lookup:
        return html
    pattern = _build_keyword_pattern(lookup)
    if pattern is None:
        return html

    parts = _TAG_SPLIT_RE.split(html)
    out: list[str] = []
    skip_depth = 0
    for part in parts:
        if not part:
            continue
        if part.startswith("<"):
            tag_match = _TAG_NAME_RE.match(part)
            if tag_match is not None:
                is_close = bool(tag_match.group(1))
                tag_name = tag_match.group(2).lower()
                if tag_name in _LINKIFY_SKIP_TAGS:
                    if is_close:
                        skip_depth = max(0, skip_depth - 1)
                    else:
                        skip_depth += 1
            out.append(part)
        else:
            if skip_depth == 0:
                out.append(_replace_keywords_in_text(part, pattern, lookup))
            else:
                out.append(part)
    return "".join(out)


def render_oracle_body(
    text: str,
    png_resolver: PngResolver,
    keyword_lookup: KeywordLookup | None = None,
) -> str:
    """Render an oracle text block. Newlines become paragraph breaks.

    When ``keyword_lookup`` is provided, keyword titles found in the text are
    wrapped in ``<a href="rule:NNN">`` anchors after mana/reminder passes so
    the link spans don't get clipped by reminder ``<i>`` tags.
    """
    if not text:
        return ""
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    rendered: list[str] = []
    for para in paragraphs:
        body = replace_mana_symbols(para, png_resolver)
        body = _italicize_reminder_text(body)
        if keyword_lookup:
            body = linkify_keywords(body, keyword_lookup)
        rendered.append(f"<p>{body}</p>")
    return "".join(rendered)


def render_flavor_text(text: str) -> str:
    if not text:
        return ""
    safe = escape(text).replace("\n", "<br>")
    return f"<p><i>{safe}</i></p>"


def _format_pt_from(meta: Any, *, prefix: str = "") -> str:
    power = _meta_get(meta, f"{prefix}power")
    toughness = _meta_get(meta, f"{prefix}toughness")
    loyalty = _meta_get(meta, f"{prefix}loyalty")
    if power is not None and toughness is not None and (str(power) != "" or str(toughness) != ""):
        return f"{escape(str(power))}/{escape(str(toughness))}"
    if loyalty:
        return escape(str(loyalty))
    return ""


def _meta_get(meta: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a dict-like meta (``dict`` or ``CardEntry``)."""
    if meta is None:
        return default
    getter = getattr(meta, "get", None)
    if callable(getter):
        return getter(key, default)
    try:
        return meta[key]
    except (KeyError, AttributeError, TypeError):
        return default


def _render_face_block(
    *,
    name: str,
    mana_cost_html: str,
    type_line: str,
    edition_label: str,
    oracle_html: str,
    flavor_html: str,
    pt: str,
) -> str:
    """Render a single card face as a self-contained block of rows."""
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0">'
        f'<tr><td align="left"><b><font size="+1">{name}</font></b></td>'
        f'<td align="right">{mana_cost_html}</td></tr>'
        '<tr><td colspan="2"><hr></td></tr>'
        f'<tr><td align="left"><font color="#A8B2BD">{type_line}</font></td>'
        f'<td align="right"><font color="#A8B2BD">{edition_label}</font></td></tr>'
        '<tr><td colspan="2"><hr></td></tr>'
        f'<tr><td colspan="2">{oracle_html}{flavor_html}</td></tr>'
        f'<tr><td align="right" colspan="2"><b><font size="+1">{pt}</font></b></td></tr>'
        "</table>"
    )


def build_card_html(
    meta: Any,
    printing: dict[str, Any] | None,
    png_resolver: PngResolver,
    *,
    empty_text: str = "Select a card to inspect.",
    keyword_lookup: KeywordLookup | None = None,
) -> str:
    """Build the full card-view HTML.

    ``meta`` carries the oracle-level fields (name, mana_cost, type_line,
    oracle_text, power, toughness, loyalty), and — when present — the matching
    ``back_*`` fields for the back face of a double-faced/split/MDFC card.
    ``printing`` carries printing-specific fields (set_name, collector_number,
    flavor_text, artist). Both may be partial — missing fields render as empty
    placeholders.
    """
    if meta is None:
        return (
            f'<html><body bgcolor="#22272E" text="#E6EDF3">'
            f'<p align="center">{escape(empty_text)}</p>'
            f"</body></html>"
        )

    full_name = str(_meta_get(meta, "name") or "")
    front_name_str, back_name_fallback = _split_face_names(full_name)
    front_name = escape(front_name_str)
    front_mana = replace_mana_symbols(str(_meta_get(meta, "mana_cost") or ""), png_resolver)
    front_type = escape(str(_meta_get(meta, "type_line") or ""))
    front_oracle = render_oracle_body(
        str(_meta_get(meta, "oracle_text") or ""),
        png_resolver,
        keyword_lookup=keyword_lookup,
    )
    front_pt = _format_pt_from(meta)

    set_name = ""
    set_code = ""
    collector = ""
    artist = ""
    flavor_html = ""
    if printing:
        set_name = escape(str(printing.get("set_name") or ""))
        set_code = escape(str(printing.get("set") or "")).upper()
        collector = escape(str(printing.get("collector_number") or ""))
        artist = escape(str(printing.get("artist") or ""))
        flavor_html = render_flavor_text(str(printing.get("flavor_text") or ""))

    edition_label = ""
    if set_name and set_code:
        edition_label = f"{set_name} ({set_code})"
    elif set_name:
        edition_label = set_name
    elif set_code:
        edition_label = set_code

    front_block = _render_face_block(
        name=front_name,
        mana_cost_html=front_mana,
        type_line=front_type,
        edition_label=edition_label,
        oracle_html=front_oracle,
        flavor_html=flavor_html,
        pt=front_pt,
    )

    back_block = ""
    back_oracle_text = str(_meta_get(meta, "back_oracle_text") or "")
    back_type_line = str(_meta_get(meta, "back_type_line") or "")
    back_name_str = str(_meta_get(meta, "back_name") or back_name_fallback or "")
    if back_oracle_text or back_type_line or back_name_str:
        back_block = _render_face_block(
            name=escape(back_name_str),
            mana_cost_html=replace_mana_symbols(
                str(_meta_get(meta, "back_mana_cost") or ""), png_resolver
            ),
            type_line=escape(back_type_line),
            edition_label="",
            oracle_html=render_oracle_body(
                back_oracle_text, png_resolver, keyword_lookup=keyword_lookup
            ),
            flavor_html="",
            pt=_format_pt_from(meta, prefix="back_"),
        )

    footer = (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0">'
        '<tr><td colspan="2"><hr></td></tr>'
        f'<tr><td align="left"><font color="#A8B2BD" size="-1">{collector}</font></td>'
        f'<td align="center"><font color="#A8B2BD" size="-1"><i>{artist}</i></font></td></tr>'
        "</table>"
    )

    # wx.html.HtmlWindow renders HTML 3.2-ish; tables are the most reliable
    # way to align "left half / right half" rows. CSS support is minimal.
    return (
        '<html><body bgcolor="#22272E" text="#E6EDF3">'
        f"{front_block}{back_block}{footer}"
        "</body></html>"
    )


def _split_face_names(full_name: str) -> tuple[str, str]:
    """Split ``"A // B"`` into ``("A", "B")``; non-DFCs return ``(full_name, "")``."""
    if "//" not in full_name:
        return full_name, ""
    parts = [piece.strip() for piece in full_name.split("//", 1)]
    return parts[0], parts[1] if len(parts) == 2 else ""
