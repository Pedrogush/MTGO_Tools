"""Unit tests for the Rules Browser HTML renderer.

These exercise the pure-Python helpers without a wx App.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from widgets.frames.rules_browser.html_render import render_outline_to_html


@dataclass
class _Sub:
    rule_id: str
    title: str
    body: str


@dataclass
class _Sec:
    number: int
    title: str
    subsections: list[_Sub] = field(default_factory=list)


def _identity(text: str) -> str:
    return text


def test_render_outline_emits_section_anchor_per_section() -> None:
    sections = [_Sec(7, "Additional Rules", [_Sub("700", "General", "")])]
    out = render_outline_to_html(sections)
    assert '<a name="section-7">' in out


def test_render_outline_emits_subsection_anchor() -> None:
    sections = [_Sec(7, "Additional Rules", [_Sub("702", "Keyword Abilities", "")])]
    out = render_outline_to_html(sections)
    assert '<a name="702">' in out


def test_render_outline_emits_per_rule_anchor_in_body() -> None:
    body = "702.9. Flying\n\n702.9a Flying is an evasion ability."
    sections = [_Sec(7, "Additional Rules", [_Sub("702", "Keyword Abilities", body)])]
    out = render_outline_to_html(sections)
    assert '<a name="702.9">702.9</a>' in out
    assert '<a name="702.9a">702.9a</a>' in out


def test_render_outline_applies_cross_ref_linkifier() -> None:
    body = "702.9b A creature with flying. See rule 702.17 for reach."

    def linkifier(escaped: str) -> str:
        # naive replacement to verify the linkifier is invoked
        return escaped.replace("rule 702.17", '<a href="#702">rule 702.17</a>')

    sections = [_Sec(7, "Additional Rules", [_Sub("702", "Keyword Abilities", body)])]
    out = render_outline_to_html(sections, cross_ref_linkifier=linkifier)
    assert '<a href="#702">rule 702.17</a>' in out


def test_render_outline_renders_section_title_with_number() -> None:
    sections = [_Sec(1, "Game Concepts", [])]
    out = render_outline_to_html(sections)
    assert "1. Game Concepts" in out


def test_render_outline_renders_glossary_without_number_prefix() -> None:
    sections = [_Sec(0, "Glossary", [_Sub("glossary", "Glossary", "Some terms.")])]
    out = render_outline_to_html(sections)
    # Section heading should NOT be "0. Glossary" — number 0 is sentinel.
    assert "0. Glossary" not in out
    assert ">Glossary<" in out


def test_render_outline_html_escapes_body_text() -> None:
    body = '702.5a Enchant requires a "target" specifier.'
    sections = [_Sec(7, "Additional Rules", [_Sub("702", "Keyword Abilities", body)])]
    out = render_outline_to_html(sections)
    # Quotes must be HTML-escaped.
    assert "&quot;target&quot;" in out


def test_render_outline_paragraphs_separated_by_blank_lines() -> None:
    body = "702.9a Para one.\n\n702.9b Para two.\n\n702.9c Para three."
    sections = [_Sec(7, "Additional Rules", [_Sub("702", "Keyword Abilities", body)])]
    out = render_outline_to_html(sections)
    # Three paragraphs in the body plus the subsection header — at least
    # 4 <p> tags total (one per body paragraph; subsection heading uses h3).
    assert out.count("<p>") >= 3


def test_render_outline_empty_sections_still_produces_valid_html() -> None:
    out = render_outline_to_html([])
    assert out.startswith("<html>")
    assert out.endswith("</body></html>")
