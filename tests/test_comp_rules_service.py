"""Unit tests for the Comprehensive Rules cache + parser.

The parser tests run against an inline fixture that mirrors the sectional
structure of the real CompRules ``.txt`` (TOC up top, then sections 700/701/702
with a few representative keywords, then 703 marking the end). No network is
exercised here — the freshness/download path is tested with a stubbed HTTP
shim that the service injects via constructor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services.comp_rules_service import (
    CompRulesService,
    find_latest_rules_url,
    linkify_cross_refs,
    parse_keywords,
    parse_outline,
)

# A minimal-but-faithful fixture: TOC at top (which must be skipped), then the
# real section markers, then 703 closing the parsed range.
_FIXTURE_TXT = """\
﻿Magic: The Gathering Comprehensive Rules

Contents

1. Game Concepts
2. Parts of a Card
700. General
701. Keyword Actions
702. Keyword Abilities
703. Turn-Based Actions

Glossary

Credits

1. Game Concepts

100. General

100.1. These rules apply to any Magic game.

100.1a A two-player game has only two players.

101. The Magic Golden Rules

101.1. Whenever a card's text contradicts these rules, the card takes precedence.

2. Parts of a Card

200. General

200.1. The parts of a card are name, mana cost, illustration, color indicator, type line, expansion symbol, text box, power and toughness, loyalty, defense, hand modifier, life modifier, illustration credit, legal text, and collector number.

700. General

700.1. Anything that happens in a game is an event.

701. Keyword Actions

701.1. Most actions described in a card's rules text use the standard English definitions of the verbs within.

701.2. Activate

701.2a To activate an activated ability is to put it onto the stack and pay its cost.

701.2b Some object's ability may be activated only at certain times.

701.5. Cast

701.5a To cast a spell is to take it from where it is and put it on the stack.

702. Keyword Abilities

702.1. Most abilities describe exactly what they do in the card's rules text.

702.2. Deathtouch

702.2a Deathtouch is a static ability.

702.2b A creature with toughness greater than 0 that has been dealt damage by a source with deathtouch is destroyed as a state-based action.

702.4. Double Strike

702.4a Double strike is a static ability that modifies the rules for the combat damage step.

702.9. Flying

702.9a Flying is an evasion ability.

702.9b A creature with flying can't be blocked except by creatures with flying or reach.

702.19. Trample

702.19a Trample is a static ability that modifies the rules for assigning an attacking creature's combat damage.

703. Turn-Based Actions

703.1. Turn-based actions are game actions that happen automatically when certain steps or phases begin.

Glossary

Flying
A keyword ability that restricts which creatures can block a creature. See rule 702.9, "Flying."

Trample
A keyword ability that allows excess combat damage to be dealt to defending player.

Credits

Magic: The Gathering was designed by Richard Garfield, with contributions from many others.
"""


def test_parse_keywords_extracts_section_701_keyword_actions() -> None:
    kws = parse_keywords(_FIXTURE_TXT)
    assert "activate" in kws
    assert "cast" in kws
    assert kws["activate"].rule_id == "701.2"
    assert kws["activate"].title == "Activate"
    assert kws["cast"].rule_id == "701.5"


def test_parse_keywords_extracts_section_702_keyword_abilities() -> None:
    kws = parse_keywords(_FIXTURE_TXT)
    assert kws["flying"].rule_id == "702.9"
    assert kws["deathtouch"].rule_id == "702.2"
    assert kws["double strike"].rule_id == "702.4"
    assert kws["trample"].rule_id == "702.19"


def test_parse_keywords_skips_section_preambles_701_1_and_702_1() -> None:
    """Rules 701.1 / 702.1 are intro paragraphs without lettered subrules."""
    kws = parse_keywords(_FIXTURE_TXT)
    # No keyword should claim those rule IDs.
    rule_ids = {entry.rule_id for entry in kws.values()}
    assert "701.1" not in rule_ids
    assert "702.1" not in rule_ids


def test_parse_keywords_skips_toc_entries() -> None:
    """The TOC lists ``701. Keyword Actions`` etc. — the parser must not
    treat the TOC as the section, which would dump every later rule into the
    wrong bucket."""
    kws = parse_keywords(_FIXTURE_TXT)
    # No keyword titled "Keyword Actions" or "Keyword Abilities" — those are
    # section headers, not keywords. Their absence proves the TOC was skipped.
    assert "keyword actions" not in kws
    assert "keyword abilities" not in kws


def test_parse_keywords_body_includes_subrules() -> None:
    flying = parse_keywords(_FIXTURE_TXT)["flying"]
    assert "702.9. Flying" in flying.body
    assert "702.9a" in flying.body
    assert "evasion ability" in flying.body
    # Body must stop before the next keyword's subrules.
    assert "Trample" not in flying.body


def test_parse_keywords_handles_crlf_and_bom() -> None:
    crlf = _FIXTURE_TXT.replace("\n", "\r\n")
    kws = parse_keywords(crlf)
    assert "flying" in kws
    assert "deathtouch" in kws


def test_parse_keywords_returns_empty_when_sections_missing() -> None:
    assert parse_keywords("") == {}
    assert parse_keywords("just some unrelated text") == {}


def test_find_latest_rules_url_extracts_dated_txt() -> None:
    html = """
    <html><body>
      <a href="https://media.wizards.com/2026/downloads/MagicCompRules%2020260227.txt">Comprehensive Rules (TXT)</a>
      <a href="https://media.wizards.com/2026/downloads/MagicCompRules%2020260227.pdf">PDF</a>
    </body></html>
    """
    url = find_latest_rules_url(html)
    assert url == "https://media.wizards.com/2026/downloads/MagicCompRules%2020260227.txt"


def test_find_latest_rules_url_normalizes_space_to_percent20() -> None:
    html = '<a href="https://media.wizards.com/2026/downloads/MagicCompRules 20260227.txt">link</a>'
    url = find_latest_rules_url(html)
    assert url == "https://media.wizards.com/2026/downloads/MagicCompRules%2020260227.txt"


def test_find_latest_rules_url_returns_none_when_missing() -> None:
    assert find_latest_rules_url("<p>no rules link here</p>") is None


def test_get_keyword_lookup_returns_empty_when_no_cache(tmp_path: Path) -> None:
    svc = CompRulesService(
        cache_path=tmp_path / "comp_rules.txt",
        stamp_path=tmp_path / "stamp.json",
    )
    assert svc.get_keyword_lookup() == {}


def test_get_keyword_lookup_parses_cached_file(tmp_path: Path) -> None:
    cache = tmp_path / "comp_rules.txt"
    cache.write_text(_FIXTURE_TXT, encoding="utf-8")
    svc = CompRulesService(cache_path=cache, stamp_path=tmp_path / "stamp.json")
    kws = svc.get_keyword_lookup()
    assert "flying" in kws
    assert kws["flying"].rule_id == "702.9"


def test_get_keyword_lookup_memoizes_until_mtime_changes(tmp_path: Path) -> None:
    import time

    cache = tmp_path / "comp_rules.txt"
    cache.write_text(_FIXTURE_TXT, encoding="utf-8")
    svc = CompRulesService(cache_path=cache, stamp_path=tmp_path / "stamp.json")
    first = svc.get_keyword_lookup()
    second = svc.get_keyword_lookup()
    # Same dict object — memoized.
    assert first is second
    # Touch the file with a newer mtime. Rename Flying → Soaring throughout
    # so the rule is still well-formed (subrule prefixes must match).
    time.sleep(0.01)
    cache.write_text(
        _FIXTURE_TXT.replace("Flying", "Soaring").replace("flying", "soaring"),
        encoding="utf-8",
    )
    third = svc.get_keyword_lookup()
    assert third is not first
    assert "soaring" in third
    assert "flying" not in third


def _make_service_with_stub_http(
    tmp_path: Path,
    landing_html: str | None,
    txt_bytes: bytes | None,
) -> CompRulesService:
    svc = CompRulesService(
        cache_path=tmp_path / "comp_rules.txt",
        stamp_path=tmp_path / "stamp.json",
        landing_url="https://example.invalid/rules",
    )

    # Monkey-patch the module-level fetchers via the service instance — but the
    # service calls ``_http_get_text`` and ``_http_get_bytes`` from module scope,
    # so we patch via ``services.comp_rules_service``.
    import services.comp_rules_service as crs

    def _stub_text(url: str, *, timeout: int) -> str | None:  # noqa: ARG001
        return landing_html

    def _stub_bytes(url: str, *, timeout: int) -> bytes | None:  # noqa: ARG001
        return txt_bytes

    crs._http_get_text = _stub_text  # type: ignore[assignment]
    crs._http_get_bytes = _stub_bytes  # type: ignore[assignment]
    return svc


def test_refresh_downloads_when_stamp_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    landing = (
        '<a href="https://media.wizards.com/2026/downloads/'
        'MagicCompRules%2020260227.txt">link</a>'
    )
    svc = _make_service_with_stub_http(tmp_path, landing, _FIXTURE_TXT.encode("utf-8"))
    assert svc.refresh() is True
    assert (tmp_path / "comp_rules.txt").is_file()
    assert (tmp_path / "stamp.json").is_file()


def test_refresh_skips_download_when_stamp_matches(tmp_path: Path) -> None:
    url = "https://media.wizards.com/2026/downloads/MagicCompRules%2020260227.txt"
    landing = f'<a href="{url}">link</a>'
    svc = _make_service_with_stub_http(tmp_path, landing, b"WHATEVER")
    # Pre-populate cache and stamp so the freshness check trips.
    (tmp_path / "comp_rules.txt").write_bytes(b"existing")
    (tmp_path / "stamp.json").write_text(f'{{"source_url":"{url}"}}', encoding="utf-8")
    assert svc.refresh() is False
    # Cache not overwritten.
    assert (tmp_path / "comp_rules.txt").read_bytes() == b"existing"


def test_refresh_returns_false_when_landing_unreachable(tmp_path: Path) -> None:
    svc = _make_service_with_stub_http(tmp_path, landing_html=None, txt_bytes=None)
    assert svc.refresh() is False


def test_refresh_returns_false_when_no_url_on_landing(tmp_path: Path) -> None:
    svc = _make_service_with_stub_http(tmp_path, "<p>no link</p>", b"unused")
    assert svc.refresh() is False


# ============================== parse_outline ==============================


def test_parse_outline_returns_a_section_per_top_level_heading() -> None:
    outline = parse_outline(_FIXTURE_TXT)
    numbers = [s.number for s in outline]
    # Section 1 + section 2 + section 7 (via "700. General") — but the fixture
    # only has "1. Game Concepts" and "2. Parts of a Card" as top-level headers.
    # Section 7 doesn't have a "7. Additional Rules" header in the fixture so
    # it's skipped — that's the expected behaviour.
    assert 1 in numbers
    assert 2 in numbers
    # Glossary always appears as the synthetic number=0 section when present.
    assert 0 in numbers


def test_parse_outline_subsections_under_their_section() -> None:
    outline = parse_outline(_FIXTURE_TXT)
    by_num = {s.number: s for s in outline}
    sec1_subs = {sub.rule_id: sub for sub in by_num[1].subsections}
    assert "100" in sec1_subs
    assert "101" in sec1_subs
    assert sec1_subs["100"].title == "General"
    assert sec1_subs["101"].title == "The Magic Golden Rules"


def test_parse_outline_subsection_body_includes_lettered_subrules() -> None:
    outline = parse_outline(_FIXTURE_TXT)
    by_num = {s.number: s for s in outline}
    sec1 = by_num[1]
    rule_100 = next(sub for sub in sec1.subsections if sub.rule_id == "100")
    assert "100.1." in rule_100.body
    assert "100.1a" in rule_100.body
    # Body must stop before the next subsection.
    assert "Magic Golden Rules" not in rule_100.body


def test_parse_outline_glossary_appended_as_section_zero() -> None:
    outline = parse_outline(_FIXTURE_TXT)
    glossary = next(s for s in outline if s.number == 0)
    assert glossary.title == "Glossary"
    assert len(glossary.subsections) == 1
    body = glossary.subsections[0].body
    assert "Flying" in body
    assert "Trample" in body
    # Glossary body must stop at "Credits".
    assert "Richard Garfield" not in body


def test_parse_outline_skips_toc_section_headers() -> None:
    """``1. Game Concepts`` appears in the TOC at the top of the fixture and
    again as the body header. The parser must use the latter."""
    outline = parse_outline(_FIXTURE_TXT)
    # If we accidentally took the TOC occurrence, "1. Game Concepts"'s body
    # would include "2. Parts of a Card" and beyond, swallowing 200.x rules.
    by_num = {s.number: s for s in outline}
    sec1 = by_num[1]
    sec1_rule_ids = {sub.rule_id for sub in sec1.subsections}
    assert "200" not in sec1_rule_ids


def test_get_outline_memoizes_until_mtime_changes(tmp_path: Path) -> None:
    import time

    cache = tmp_path / "comp_rules.txt"
    cache.write_text(_FIXTURE_TXT, encoding="utf-8")
    svc = CompRulesService(cache_path=cache, stamp_path=tmp_path / "stamp.json")
    first = svc.get_outline()
    second = svc.get_outline()
    assert first is second  # memoized
    time.sleep(0.01)
    cache.write_text(
        _FIXTURE_TXT.replace("100. General", "100. Modified Title"),
        encoding="utf-8",
    )
    third = svc.get_outline()
    assert third is not first
    rule_100_titles = {sub.title for s in third for sub in s.subsections if sub.rule_id == "100"}
    assert "Modified Title" in rule_100_titles


# ============================ linkify_cross_refs ==========================


def test_linkify_cross_refs_wraps_rule_with_subsection_anchor() -> None:
    out = linkify_cross_refs("See rule 702.9 for details.")
    assert out == 'See rule <a href="#702">702.9</a> for details.'


def test_linkify_cross_refs_handles_lettered_subrule() -> None:
    out = linkify_cross_refs("As described in rule 100.1b.")
    assert '<a href="#100">100.1b</a>' in out


def test_linkify_cross_refs_handles_plural_rules_keyword() -> None:
    out = linkify_cross_refs("See rules 702.9 and rule 702.18.")
    # First "rules 702.9" gets linkified; the trailing "rule 702.18" gets its
    # own link too.
    assert '<a href="#702">702.9</a>' in out
    assert '<a href="#702">702.18</a>' in out


def test_linkify_cross_refs_does_not_match_bare_numbers() -> None:
    """``702.9`` without the ``rule`` prefix shouldn't link — too many false
    positives from collector numbers, dates, and version strings."""
    out = linkify_cross_refs("Score is 702.9 right now.")
    assert "<a href=" not in out


def test_linkify_cross_refs_is_case_insensitive() -> None:
    assert '<a href="#702">' in linkify_cross_refs("See Rule 702.9.")
    assert '<a href="#702">' in linkify_cross_refs("RULES 702.9 apply.")
