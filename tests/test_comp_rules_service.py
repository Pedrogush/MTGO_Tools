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
    parse_keywords,
)

# A minimal-but-faithful fixture: TOC at top (which must be skipped), then the
# real section markers, then 703 closing the parsed range.
_FIXTURE_TXT = """\
﻿Magic: The Gathering Comprehensive Rules

Contents

1. Game Concepts
700. General
701. Keyword Actions
702. Keyword Abilities
703. Turn-Based Actions

700. General

700.1. Some preamble text.

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
