"""Pure helpers that render a Section→Subsection outline into HTML.

Kept separate from any wx imports so the helpers can be unit-tested without
a wx App.  The output targets ``wx.html.HtmlWindow`` which renders an
HTML 3.2-ish dialect — minimal CSS, no JS.  Anchors are emitted both for
subsections (``<a name="702">``) and individual rules (``<a name="702.9">``)
so cross-reference links jump to the right paragraph rather than just the
section heading.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from html import escape

# Subsection anchor renderer expects a stable ``Section`` / ``Subsection``
# duck-typed shape — ``rule_id``, ``title``, ``body``, ``subsections``,
# ``number`` — so the renderer doesn't need a service-layer import.
# Match a rule paragraph header — ``702.9.`` or ``702.9a``-style — at the
# start of a line. Used to inject per-rule anchors when laying out the body.
_RULE_HEADER_LINE_RE = re.compile(r"^(\d{3}\.\d+[a-z]?)(?=[\s.])")


def render_outline_to_html(
    sections: Iterable[object],
    *,
    bg_color: str = "#22272E",
    text_color: str = "#E6EDF3",
    link_color: str = "#7AA2F7",
    cross_ref_linkifier: object | None = None,
) -> str:
    """Render the full outline to a single HTML document.

    ``cross_ref_linkifier`` should be a callable ``(escaped_text) -> str`` —
    typically ``services.comp_rules_service.linkify_cross_refs`` — applied to
    each rule paragraph after escaping.  Pass ``None`` to disable.
    """
    parts: list[str] = [
        "<html><body bgcolor=",
        f'"{bg_color}" text="{text_color}" link="{link_color}">',
    ]
    for sec in sections:
        number = getattr(sec, "number", 0)
        title = getattr(sec, "title", "")
        anchor = f"section-{number}"
        parts.append(
            f'<h2><a name="{escape(anchor)}">'
            f'<font color="{text_color}">{escape(_format_section_heading(number, title))}</font>'
            "</a></h2>"
        )
        for sub in getattr(sec, "subsections", []):
            parts.append(_render_subsection(sub, text_color, cross_ref_linkifier))
    parts.append("</body></html>")
    return "".join(parts)


def _format_section_heading(number: int, title: str) -> str:
    return title if number == 0 else f"{number}. {title}"


def _render_subsection(sub: object, text_color: str, cross_ref_linkifier: object | None) -> str:
    rule_id = getattr(sub, "rule_id", "")
    title = getattr(sub, "title", "")
    body = getattr(sub, "body", "")
    heading = (
        f'<h3><a name="{escape(rule_id)}">'
        f'<font color="{text_color}">{escape(rule_id)}. {escape(title)}</font>'
        "</a></h3>"
    )
    return heading + _render_body_paragraphs(body, cross_ref_linkifier)


def _render_body_paragraphs(body: str, cross_ref_linkifier: object | None) -> str:
    """Convert a raw rule body into anchored ``<p>`` paragraphs.

    Paragraphs are separated by blank lines in the source text.  When the
    first non-empty line of a paragraph begins with a ``\\d+\\.\\d+[a-z]?``
    rule-id token, that token is wrapped in an ``<a name="...">`` anchor so
    cross-references can jump straight to the rule.
    """
    paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    out: list[str] = []
    for para in paragraphs:
        escaped = escape(para)
        # Convert intra-paragraph newlines to <br> so multi-line examples
        # (``Example: …``) keep their visual break.
        escaped = escaped.replace("\n", "<br>")
        if cross_ref_linkifier is not None:
            escaped = cross_ref_linkifier(escaped)
        anchored = _anchor_first_rule_id(escaped)
        out.append(f"<p>{anchored}</p>")
    return "".join(out)


def _anchor_first_rule_id(escaped_paragraph: str) -> str:
    """Wrap the leading rule-id token in an ``<a name="…">`` anchor.

    The cross-ref linkifier must run *before* this so we don't double-wrap
    the same token. Looks only at the first 12 chars of the paragraph for
    a rule-id prefix; that keeps us safe from also matching IDs deeper in
    the body that are already pure text.
    """
    match = _RULE_HEADER_LINE_RE.match(escaped_paragraph)
    if match is None:
        return escaped_paragraph
    rule_id = match.group(1)
    # If this token was already linkified by the cross-ref pass we'd see an
    # ``<a href=…>`` lead-in instead — guard by checking the raw start.
    return f'<a name="{rule_id}">{rule_id}</a>{escaped_paragraph[len(rule_id):]}'
