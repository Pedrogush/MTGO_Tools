"""Pure helpers that render an MTG-card-like HTML view of a card.

Only standard library + ``re`` is used here — kept separate from any wx imports
so the helpers are unit-testable without a wx App.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from html import escape
from pathlib import Path
from typing import Any

# Match either {SYMBOL} or a bare token previously normalized.
_MANA_TOKEN_RE = re.compile(r"\{([^{}]+)\}")
# Reminder text in MTG oracle text is parenthetical and italicized.
_REMINDER_RE = re.compile(r"\(([^)]+)\)")

PngResolver = Callable[[str], Path | None]


def replace_mana_symbols(
    text: str,
    png_resolver: PngResolver,
    *,
    symbol_size: int = 14,
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
            parts.append(
                f'<img src="{uri}" width="{symbol_size}" height="{symbol_size}" '
                f'alt="{{{escape(token)}}}">'
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


def render_oracle_body(text: str, png_resolver: PngResolver) -> str:
    """Render an oracle text block. Newlines become paragraph breaks."""
    if not text:
        return ""
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    rendered: list[str] = []
    for para in paragraphs:
        body = replace_mana_symbols(para, png_resolver)
        body = _italicize_reminder_text(body)
        rendered.append(f"<p>{body}</p>")
    return "".join(rendered)


def render_flavor_text(text: str) -> str:
    if not text:
        return ""
    safe = escape(text).replace("\n", "<br>")
    return f"<p><i>{safe}</i></p>"


def _format_pt_from(meta: Any) -> str:
    power = _meta_get(meta, "power")
    toughness = _meta_get(meta, "toughness")
    loyalty = _meta_get(meta, "loyalty")
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


def build_card_html(
    meta: Any,
    printing: dict[str, Any] | None,
    png_resolver: PngResolver,
    *,
    empty_text: str = "Select a card to inspect.",
) -> str:
    """Build the full card-view HTML.

    ``meta`` carries the oracle-level fields (name, mana_cost, type_line,
    oracle_text, power, toughness, loyalty). ``printing`` carries
    printing-specific fields (set_name, collector_number, flavor_text, artist).
    Both may be partial — missing fields render as empty placeholders.
    """
    if meta is None:
        return (
            f'<html><body bgcolor="#22272E" text="#E6EDF3">'
            f'<p align="center">{escape(empty_text)}</p>'
            f"</body></html>"
        )

    name = escape(str(_meta_get(meta, "name") or ""))
    mana_cost = replace_mana_symbols(str(_meta_get(meta, "mana_cost") or ""), png_resolver)
    type_line = escape(str(_meta_get(meta, "type_line") or ""))
    oracle_html = render_oracle_body(str(_meta_get(meta, "oracle_text") or ""), png_resolver)
    pt = _format_pt_from(meta)

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

    # wx.html.HtmlWindow renders HTML 3.2-ish; tables are the most reliable
    # way to align "left half / right half" rows. CSS support is minimal.
    return f"""<html>
<body bgcolor="#22272E" text="#E6EDF3">
<table width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
  <td align="left"><b><font size="+1">{name}</font></b></td>
  <td align="right">{mana_cost}</td>
</tr>
<tr><td colspan="2"><hr></td></tr>
<tr>
  <td align="left"><font color="#A8B2BD">{type_line}</font></td>
  <td align="right"><font color="#A8B2BD">{edition_label}</font></td>
</tr>
<tr><td colspan="2"><hr></td></tr>
<tr><td colspan="2">{oracle_html}{flavor_html}</td></tr>
<tr><td colspan="2"><hr></td></tr>
<tr>
  <td align="left"><font color="#A8B2BD" size="-1">{collector}</font></td>
  <td align="center"><font color="#A8B2BD" size="-1"><i>{artist}</i></font></td>
</tr>
<tr>
  <td align="right" colspan="2"><b><font size="+1">{pt}</font></b></td>
</tr>
</table>
</body>
</html>"""
