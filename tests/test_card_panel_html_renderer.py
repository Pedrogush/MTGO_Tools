"""Unit tests for the pure HTML helpers powering the Card panel's Oracle tab.

These exercise rendering without a wx dependency, so they run under WSL Python.
"""

from __future__ import annotations

from widgets.panels.card_panel.html_renderer import (
    build_card_html,
    render_oracle_body,
    replace_mana_symbols,
)


def _no_png(token: str):  # noqa: ARG001
    return None


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
