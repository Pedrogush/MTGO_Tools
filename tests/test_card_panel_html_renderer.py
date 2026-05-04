"""Unit tests for the pure HTML helpers powering the Card panel's Oracle tab.

These exercise rendering without a wx dependency, so they run under WSL Python.
"""

from __future__ import annotations

from dataclasses import dataclass

from widgets.panels.card_panel.html_renderer import (
    build_card_html,
    linkify_keywords,
    render_oracle_body,
    replace_mana_symbols,
)


def _no_png(token: str):  # noqa: ARG001
    return None


@dataclass(frozen=True)
class _KW:
    title: str
    rule_id: str


def _kw_lookup(*pairs: tuple[str, str]) -> dict[str, _KW]:
    return {title.lower(): _KW(title=title, rule_id=rule_id) for title, rule_id in pairs}


def test_replace_mana_symbols_falls_back_to_braced_text() -> None:
    out = replace_mana_symbols("Pay {2}{R}", _no_png)
    assert out == "Pay {2}{R}"


def test_replace_mana_symbols_html_escapes_surrounding_text() -> None:
    out = replace_mana_symbols("a < b > c", _no_png)
    assert out == "a &lt; b &gt; c"


def test_render_oracle_body_splits_paragraphs_and_italicizes_reminder() -> None:
    text = "Flying\nLandfall — Draw a card. (You may play a land.)"
    out = render_oracle_body(text, _no_png)
    assert "<p>Flying</p>" in out
    assert "<i>(You may play a land.)</i>" in out


def test_build_card_html_empty_meta_renders_placeholder() -> None:
    html = build_card_html(None, None, _no_png, empty_text="Pick a card")
    assert "Pick a card" in html


def test_build_card_html_renders_card_and_printing_fields() -> None:
    meta = {
        "name": "Lightning Bolt",
        "mana_cost": "{R}",
        "type_line": "Instant",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        "power": None,
        "toughness": None,
    }
    printing = {
        "set": "lea",
        "set_name": "Limited Edition Alpha",
        "collector_number": "161",
        "flavor_text": "The sparkmage shrieked.",
        "artist": "Christopher Rush",
    }
    html = build_card_html(meta, printing, _no_png)
    assert "Lightning Bolt" in html
    assert "Instant" in html
    assert "Limited Edition Alpha (LEA)" in html
    assert "161" in html
    assert "Christopher Rush" in html
    assert "<i>The sparkmage shrieked." in html


def test_build_card_html_creature_includes_pt() -> None:
    meta = {
        "name": "Grizzly Bears",
        "mana_cost": "{1}{G}",
        "type_line": "Creature — Bear",
        "oracle_text": "",
        "power": "2",
        "toughness": "2",
    }
    html = build_card_html(meta, None, _no_png)
    assert ">2/2<" in html


def test_build_card_html_planeswalker_includes_loyalty() -> None:
    meta = {
        "name": "Jace, the Mind Sculptor",
        "mana_cost": "{2}{U}{U}",
        "type_line": "Legendary Planeswalker — Jace",
        "oracle_text": "",
        "loyalty": "3",
    }
    html = build_card_html(meta, None, _no_png)
    assert ">3<" in html


def test_build_card_html_works_with_dict_like_struct() -> None:
    """The renderer should accept any object exposing ``.get(key)``."""

    class FakeMeta:
        def get(self, key, default=None):
            return {
                "name": "Mox Pearl",
                "mana_cost": "{0}",
                "type_line": "Artifact",
                "oracle_text": "{T}: Add {W}.",
            }.get(key, default)

    html = build_card_html(FakeMeta(), None, _no_png)
    assert "Mox Pearl" in html
    assert "Artifact" in html


def test_build_card_html_renders_back_face_when_present() -> None:
    meta = {
        "name": "Ajani, Nacatl Pariah // Ajani, Nacatl Avenger",
        "mana_cost": "{1}{W}",
        "type_line": "Legendary Creature — Cat Warrior",
        "oracle_text": "{T}: Draw a card.",
        "power": "1",
        "toughness": "3",
        "back_name": "Ajani, Nacatl Avenger",
        "back_mana_cost": "",
        "back_type_line": "Legendary Planeswalker — Ajani",
        "back_oracle_text": "+1: target creature gets +1/+1 until end of turn.",
        "back_loyalty": "4",
    }
    html = build_card_html(meta, None, _no_png)
    assert "Ajani, Nacatl Pariah" in html
    assert "Ajani, Nacatl Avenger" in html
    assert "Legendary Planeswalker" in html
    assert "Draw a card" in html
    assert "target creature gets +1/+1" in html
    # Front face P/T and back-face loyalty both present.
    assert ">1/3<" in html
    assert ">4<" in html


def test_build_card_html_back_face_falls_back_to_canonical_split() -> None:
    """If ``back_name`` is missing but the canonical name has ``//``, derive it."""
    meta = {
        "name": "Fire // Ice",
        "mana_cost": "{1}{R}",
        "type_line": "Instant",
        "oracle_text": "Fire deals 2 damage divided as you choose.",
        "back_type_line": "Instant",
        "back_oracle_text": "Tap target permanent. Draw a card.",
        "back_mana_cost": "{1}{U}",
    }
    html = build_card_html(meta, None, _no_png)
    assert ">Fire<" in html
    assert ">Ice<" in html
    assert "Tap target permanent" in html


def test_build_card_html_single_face_card_does_not_render_back_block() -> None:
    meta = {
        "name": "Lightning Bolt",
        "mana_cost": "{R}",
        "type_line": "Instant",
        "oracle_text": "Deal 3 damage.",
    }
    html = build_card_html(meta, None, _no_png)
    # Two <table> blocks: one for the front face, one for the footer.
    assert html.count("<table") == 2


def test_build_card_html_escapes_user_text() -> None:
    meta = {
        "name": "Evil <script>",
        "mana_cost": "",
        "type_line": "Sorcery",
        "oracle_text": "Cast & destroy.",
    }
    html = build_card_html(meta, None, _no_png)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp; destroy" in html


# ============================ keyword linkifier ============================


def test_linkify_keywords_wraps_keyword_in_anchor_with_rule_href() -> None:
    lookup = _kw_lookup(("Flying", "702.9"))
    out = linkify_keywords("<p>Flying</p>", lookup)
    assert '<a href="rule:702.9">' in out
    assert ">Flying</font></a>" in out


def test_linkify_keywords_is_case_insensitive() -> None:
    lookup = _kw_lookup(("Flying", "702.9"))
    out = linkify_keywords("<p>flying</p>", lookup)
    assert '<a href="rule:702.9">' in out
    # Original casing of the matched token is preserved.
    assert "flying</font></a>" in out


def test_linkify_keywords_picks_longest_match_first() -> None:
    lookup = _kw_lookup(("Strike", "999.1"), ("Double Strike", "702.4"))
    out = linkify_keywords("<p>Double Strike</p>", lookup)
    # "Double Strike" should resolve to the multi-word entry, not "Strike".
    assert '<a href="rule:702.4">' in out
    assert "rule:999.1" not in out


def test_linkify_keywords_skips_inside_reminder_italics() -> None:
    """Keywords inside ``<i>...</i>`` (reminder text) must NOT be linked."""
    lookup = _kw_lookup(("Flying", "702.9"))
    out = linkify_keywords(
        "<p>Flying <i>(Flying creatures cant be blocked.)</i></p>",
        lookup,
    )
    # The leading "Flying" outside the italics gets linked.
    assert out.count('<a href="rule:702.9">') == 1


def test_linkify_keywords_does_not_nest_anchors() -> None:
    lookup = _kw_lookup(("Flying", "702.9"))
    pre_linked = '<p><a href="rule:702.9">Flying</a></p>'
    out = linkify_keywords(pre_linked, lookup)
    # Pass should be a no-op — already-linked text must not get a second anchor.
    assert out == pre_linked


def test_linkify_keywords_respects_word_boundaries() -> None:
    lookup = _kw_lookup(("Trample", "702.19"))
    out = linkify_keywords("<p>The trampled grass.</p>", lookup)
    # ``trampled`` must not be linked.
    assert '<a href="rule:702.19">' not in out


def test_linkify_keywords_no_lookup_returns_input_unchanged() -> None:
    html = "<p>Flying</p>"
    assert linkify_keywords(html, {}) == html


def test_render_oracle_body_links_keywords_when_lookup_present() -> None:
    lookup = _kw_lookup(("Flying", "702.9"), ("Trample", "702.19"))
    out = render_oracle_body("Flying, trample", _no_png, keyword_lookup=lookup)
    assert '<a href="rule:702.9">' in out
    assert '<a href="rule:702.19">' in out


def test_render_oracle_body_without_lookup_renders_no_anchors() -> None:
    out = render_oracle_body("Flying", _no_png, keyword_lookup=None)
    assert "<a " not in out


def test_build_card_html_threads_keyword_lookup_through() -> None:
    lookup = _kw_lookup(("Flying", "702.9"))
    meta = {
        "name": "Serra Angel",
        "mana_cost": "{3}{W}{W}",
        "type_line": "Creature — Angel",
        "oracle_text": "Flying, vigilance",
        "power": "4",
        "toughness": "4",
    }
    html = build_card_html(meta, None, _no_png, keyword_lookup=lookup)
    assert '<a href="rule:702.9">' in html
