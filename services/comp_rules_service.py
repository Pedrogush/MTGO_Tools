"""Comprehensive Rules cache + keyword parser.

Wizards publishes the MTG Comprehensive Rules as a dated plain-text file at
``media.wizards.com``.  The filename embeds the publication date
(``MagicCompRules 20260227.txt``), so freshness is checked by reading the
rules landing page, comparing the latest ``.txt`` URL against the URL stored
in our local stamp, and re-downloading only when it differs.

Public API:

- :func:`get_comp_rules_service` — module-level singleton accessor.
- :class:`CompRulesService.refresh` — perform the freshness check + download.
- :class:`CompRulesService.get_keyword_lookup` — return ``{keyword → entry}``
  parsed from the locally cached ``.txt`` (no network access).

Only keyword rules from sections 701 (Keyword Actions) and 702 (Keyword
Abilities) are extracted; rule 701.1 / 702.1 (the section preambles) are
filtered out because they have no lettered subrules.
"""

from __future__ import annotations

import re
from pathlib import Path

import msgspec
from loguru import logger

from utils.atomic_io import atomic_write_bytes, atomic_write_json
from utils.constants import COMP_RULES_STAMP_FILE, COMP_RULES_TXT_FILE

RULES_LANDING_URL = "https://magic.wizards.com/en/rules"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30

# Top-level sections in the comp rules — titles are stable and have been
# the same for many years. Used to slice the body and skip the TOC at the top
# of the file.
_OUTLINE_SECTIONS: tuple[tuple[int, str], ...] = (
    (1, "Game Concepts"),
    (2, "Parts of a Card"),
    (3, "Card Types"),
    (4, "Zones"),
    (5, "Turn Structure"),
    (6, "Spells, Abilities, and Effects"),
    (7, "Additional Rules"),
    (8, "Multiplayer Rules"),
    (9, "Casual Variants"),
)
# Cross-reference like ``rule 702.9`` or ``rules 100.1b`` — captures the
# leading ``rule(s)`` prefix and the rule_id separately so the linkifier can
# anchor to the subsection (``702``) while preserving the printed text.
_CROSS_REF_RE = re.compile(
    r"\b(rules?\s+)(\d{3}(?:\.\d+[a-z]?)?)",
    re.IGNORECASE,
)
_SUBSECTION_RE = re.compile(r"^(\d{3})\.\s+(.+?)\s*$", re.MULTILINE)
_GLOSSARY_HEADER_RE = re.compile(r"^Glossary\s*$", re.MULTILINE)
_CREDITS_HEADER_RE = re.compile(r"^Credits\s*$", re.MULTILINE)

# Match the latest CompRules .txt URL on the rules landing page. Wizards'
# canonical URL pattern is ``media.wizards.com/<year>/downloads/MagicCompRules <YYYYMMDD>.txt``.
# The space is written either as ``%20`` (escaped, in href attributes) or as a
# literal space; the ``YYYYMMDD`` segment is exactly 8 digits.
_RULES_TXT_URL_RE = re.compile(
    r"https?://media\.wizards\.com/\d{4}/downloads/MagicCompRules(?:%20|\s)\d{8}\.txt",
    re.IGNORECASE,
)

# Top-level keyword rule line: ``702.9. Flying``. Captures rule_id and title.
_RULE_LINE_RE = re.compile(r"^(\d+\.\d+)\.\s+(.+?)\s*$", re.MULTILINE)
# Section markers occur twice in the file: once in the table of contents,
# once at the section itself. We use the *last* occurrence to skip the TOC.
_SECTION_HEADER_701 = re.compile(r"^701\.\s+Keyword Actions\s*$", re.MULTILINE)
_SECTION_HEADER_702 = re.compile(r"^702\.\s+Keyword Abilities\s*$", re.MULTILINE)
_SECTION_HEADER_703 = re.compile(r"^703\.\s+", re.MULTILINE)


class KeywordEntry(msgspec.Struct, frozen=True):
    """A single keyword's rule extracted from sections 701/702."""

    keyword: str  # canonical lowercase form, used as lookup key
    title: str  # display title, e.g. "Flying" or "Double Strike"
    rule_id: str  # e.g. "702.9"
    body: str  # rule body including all lettered subrules


class Subsection(msgspec.Struct, frozen=True):
    """A 3-digit subsection of the comp rules (e.g. ``701. Keyword Actions``).

    The body is the raw text from the rules document — rule paragraphs and
    lettered subrules — without further parsing.  The browser frame renders
    this verbatim with anchors so cross-references can navigate within the
    document.
    """

    rule_id: str  # e.g. "100", "701", or "glossary"
    title: str  # e.g. "General", "Keyword Actions", "Glossary"
    body: str


class Section(msgspec.Struct, frozen=True):
    """A top-level section (1–9, plus a synthetic Glossary section)."""

    number: int  # 1..9, or 0 for the Glossary
    title: str
    subsections: list[Subsection]


class _Stamp(msgspec.Struct):
    """Records the upstream URL of the locally cached comp rules .txt."""

    source_url: str


def _last_match(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    last: re.Match[str] | None = None
    for m in pattern.finditer(text):
        last = m
    return last


def _http_get_text(url: str, *, timeout: int) -> str | None:
    """Fetch ``url`` and decode as UTF-8 text. Returns None on any failure."""
    try:
        import curl_cffi.requests as requests  # type: ignore[import-untyped]

        response = requests.get(url, impersonate="chrome", timeout=timeout)
        response.raise_for_status()
        return response.content.decode("utf-8", errors="replace")
    except ImportError:
        pass
    except Exception as exc:
        logger.debug(f"comp rules fetch (curl_cffi) failed for {url!r}: {exc}")

    try:
        from urllib.parse import urlparse
        from urllib.request import urlopen

        parsed = urlparse(url)
        if parsed.scheme not in ("https", "http"):
            return None
        with urlopen(url, timeout=timeout) as resp:  # nosec B310
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.debug(f"comp rules fetch (urllib) failed for {url!r}: {exc}")
        return None


def _http_get_bytes(url: str, *, timeout: int) -> bytes | None:
    try:
        import curl_cffi.requests as requests  # type: ignore[import-untyped]

        response = requests.get(url, impersonate="chrome", timeout=timeout)
        response.raise_for_status()
        return response.content
    except ImportError:
        pass
    except Exception as exc:
        logger.debug(f"comp rules download (curl_cffi) failed for {url!r}: {exc}")

    try:
        from urllib.parse import urlparse
        from urllib.request import urlopen

        parsed = urlparse(url)
        if parsed.scheme not in ("https", "http"):
            return None
        with urlopen(url, timeout=timeout) as resp:  # nosec B310
            return resp.read()
    except Exception as exc:
        logger.debug(f"comp rules download (urllib) failed for {url!r}: {exc}")
        return None


def find_latest_rules_url(landing_html: str) -> str | None:
    """Return the first ``MagicCompRules <date>.txt`` URL found on the page."""
    match = _RULES_TXT_URL_RE.search(landing_html)
    if match is None:
        return None
    # Normalize ``%20`` so stamp comparison is stable regardless of encoding.
    return match.group(0).replace(" ", "%20")


def parse_keywords(text: str) -> dict[str, KeywordEntry]:
    """Parse keyword abilities from a Comprehensive Rules ``.txt``.

    The returned mapping is keyed on the lowercased keyword title (e.g.
    ``"flying"``, ``"double strike"``). Rule 701.1 / 702.1 (section preambles)
    are skipped because they have no lettered subrules.
    """
    text = _normalize(text)

    section_701 = _last_match(_SECTION_HEADER_701, text)
    section_702 = _last_match(_SECTION_HEADER_702, text)
    section_703 = _last_match(_SECTION_HEADER_703, text)
    if section_701 is None or section_702 is None or section_703 is None:
        logger.warning("comp rules: section markers 701/702/703 not all found")
        return {}

    ranges = [
        (section_701.end(), section_702.start()),
        (section_702.end(), section_703.start()),
    ]

    entries: dict[str, KeywordEntry] = {}
    for start, end in ranges:
        section_text = text[start:end]
        matches = list(_RULE_LINE_RE.finditer(section_text))
        for i, m in enumerate(matches):
            rule_id = m.group(1)
            title = m.group(2).strip()
            body_start = m.end()
            body_end = matches[i + 1].start() if i + 1 < len(matches) else len(section_text)
            body = section_text[body_start:body_end].strip()
            # Skip preambles like 701.1/702.1 — those start with prose, not
            # lettered subrules. Real keyword rules always have at least one
            # ``702.9a``-style subrule.
            sub_re = re.compile(rf"^{re.escape(rule_id)}[a-z]\b", re.MULTILINE)
            if not sub_re.search(body):
                continue
            full_body = f"{rule_id}. {title}\n\n{body}"
            entries[title.lower()] = KeywordEntry(
                keyword=title.lower(),
                title=title,
                rule_id=rule_id,
                body=full_body,
            )
    return entries


def _normalize(text: str) -> str:
    """Strip BOM + normalize line endings to LF — common pre-processing."""
    return text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")


def parse_outline(text: str) -> list[Section]:
    """Parse the full comp rules into a section → subsection tree.

    Skips the table of contents at the top of the file by selecting the *last*
    occurrence of each known section header. The Glossary is appended as a
    synthetic section (``number=0``) with a single subsection holding the full
    glossary body.
    """
    text = _normalize(text)

    # Locate each canonical section's body header (last match wins to skip TOC).
    section_starts: list[tuple[int, str, int]] = []
    for num, title in _OUTLINE_SECTIONS:
        pattern = re.compile(rf"^{num}\.\s+{re.escape(title)}\s*$", re.MULTILINE)
        last = _last_match(pattern, text)
        if last is not None:
            section_starts.append((num, title, last.start()))

    glossary = _last_match(_GLOSSARY_HEADER_RE, text)
    credits_marker = _last_match(_CREDITS_HEADER_RE, text)

    # Determine the cut points that bound each section's body.
    bounds: list[int] = [start for _num, _title, start in section_starts]
    if glossary is not None:
        bounds.append(glossary.start())
    elif credits_marker is not None:
        bounds.append(credits_marker.start())
    else:
        bounds.append(len(text))

    sections: list[Section] = []
    for idx, (num, title, start) in enumerate(section_starts):
        end = bounds[idx + 1] if idx + 1 < len(bounds) else len(text)
        section_text = text[start:end]
        # Drop the section header line itself from the slice we hand to the
        # subsection parser so it doesn't trip on anything but ``NNN.`` headers.
        first_newline = section_text.find("\n")
        body_start = first_newline + 1 if first_newline >= 0 else len(section_text)
        sections.append(
            Section(
                number=num,
                title=title,
                subsections=_parse_subsections(section_text[body_start:]),
            )
        )

    if glossary is not None:
        glossary_end = credits_marker.start() if credits_marker is not None else len(text)
        glossary_body = text[glossary.end() : glossary_end].strip()
        sections.append(
            Section(
                number=0,
                title="Glossary",
                subsections=[Subsection(rule_id="glossary", title="Glossary", body=glossary_body)],
            )
        )

    return sections


def _parse_subsections(section_text: str) -> list[Subsection]:
    matches = list(_SUBSECTION_RE.finditer(section_text))
    subsections: list[Subsection] = []
    for i, m in enumerate(matches):
        rule_id = m.group(1)
        title = m.group(2).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(section_text)
        body = section_text[body_start:body_end].strip("\n")
        subsections.append(Subsection(rule_id=rule_id, title=title, body=body))
    return subsections


def linkify_cross_refs(escaped_text: str) -> str:
    """Wrap ``rule 702.9``-style mentions with ``<a href="#702">`` anchors.

    Operates on already-HTML-escaped text so it can be inserted into a
    wx.html document without re-escaping.  The link target is the *subsection*
    (``702``) since that is the granularity the browser frame anchors at;
    the matched text (``702.9``) is preserved as the link label.
    """

    def _repl(match: re.Match[str]) -> str:
        prefix = match.group(1)
        rule_id = match.group(2)
        subsection_id = rule_id.split(".")[0]
        return f'{prefix}<a href="#{subsection_id}">{rule_id}</a>'

    return _CROSS_REF_RE.sub(_repl, escaped_text)


class CompRulesService:
    """Local cache + parser for the MTG Comprehensive Rules.

    Network calls happen only inside :meth:`refresh`; :meth:`get_keyword_lookup`
    is pure-disk so it can be called from the UI thread without I/O concerns.
    """

    def __init__(
        self,
        cache_path: Path = COMP_RULES_TXT_FILE,
        stamp_path: Path = COMP_RULES_STAMP_FILE,
        landing_url: str = RULES_LANDING_URL,
        request_timeout: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.stamp_path = Path(stamp_path)
        self.landing_url = landing_url
        self.request_timeout = request_timeout
        self._cached_lookup: dict[str, KeywordEntry] | None = None
        self._cached_outline: list[Section] | None = None
        self._cached_mtime: float | None = None

    def refresh(self) -> bool:
        """Check for a newer comp rules .txt and download it if found.

        Returns True when a download happened, False when the cache was already
        current or the network was unreachable.
        """
        landing = _http_get_text(self.landing_url, timeout=self.request_timeout)
        if landing is None:
            logger.info("comp rules: landing page unreachable; using cached copy")
            return False

        latest_url = find_latest_rules_url(landing)
        if latest_url is None:
            logger.warning("comp rules: no .txt URL found on landing page")
            return False

        current_url = self._read_stamp_url()
        if current_url == latest_url and self.cache_path.is_file():
            logger.debug(f"comp rules: cache up-to-date ({latest_url})")
            return False

        data = _http_get_bytes(latest_url, timeout=self.request_timeout)
        if data is None:
            logger.warning(f"comp rules: failed to download {latest_url}")
            return False

        atomic_write_bytes(self.cache_path, data)
        atomic_write_json(self.stamp_path, {"source_url": latest_url})
        # Invalidate parsed caches so the next lookup re-reads from disk.
        self._cached_lookup = None
        self._cached_outline = None
        self._cached_mtime = None
        logger.info(f"comp rules: downloaded {latest_url} ({len(data)} bytes)")
        return True

    def get_keyword_lookup(self) -> dict[str, KeywordEntry]:
        """Return ``{lowercased_keyword → KeywordEntry}`` parsed from the cache.

        Returns an empty dict if no cached copy exists yet. The parsed result
        is memoized; the cache invalidates when the .txt's mtime changes.
        """
        raw = self._read_fresh_cache()
        if raw is None:
            return {}
        if self._cached_lookup is None:
            self._cached_lookup = parse_keywords(raw)
            logger.debug(f"comp rules: parsed {len(self._cached_lookup)} keyword entries")
        return self._cached_lookup

    def get_outline(self) -> list[Section]:
        """Return the section/subsection outline parsed from the cache.

        Returns an empty list if no cached copy exists yet. Memoized like
        :meth:`get_keyword_lookup`.
        """
        raw = self._read_fresh_cache()
        if raw is None:
            return []
        if self._cached_outline is None:
            self._cached_outline = parse_outline(raw)
            sub_count = sum(len(s.subsections) for s in self._cached_outline)
            logger.debug(
                f"comp rules: parsed outline — "
                f"{len(self._cached_outline)} sections, {sub_count} subsections"
            )
        return self._cached_outline

    def _read_fresh_cache(self) -> str | None:
        """Read the cached .txt, invalidating memoized parses on mtime change."""
        if not self.cache_path.is_file():
            return None
        try:
            mtime = self.cache_path.stat().st_mtime
        except OSError:
            return None
        if self._cached_mtime != mtime:
            self._cached_lookup = None
            self._cached_outline = None
            self._cached_mtime = mtime
        try:
            return self.cache_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning(f"comp rules: failed to read cache: {exc}")
            return None

    def _read_stamp_url(self) -> str | None:
        if not self.stamp_path.is_file():
            return None
        try:
            raw = self.stamp_path.read_bytes()
            stamp = msgspec.json.decode(raw, type=_Stamp)
        except (OSError, msgspec.DecodeError) as exc:
            logger.debug(f"comp rules: failed to read stamp: {exc}")
            return None
        return stamp.source_url


_default_service: CompRulesService | None = None


def get_comp_rules_service() -> CompRulesService:
    """Return the module-level :class:`CompRulesService` singleton."""
    global _default_service
    if _default_service is None:
        _default_service = CompRulesService()
    return _default_service


def reset_comp_rules_service() -> None:
    """Reset the singleton — primarily for test isolation."""
    global _default_service
    _default_service = None


__all__ = [
    "CompRulesService",
    "KeywordEntry",
    "Section",
    "Subsection",
    "find_latest_rules_url",
    "get_comp_rules_service",
    "linkify_cross_refs",
    "parse_keywords",
    "parse_outline",
    "reset_comp_rules_service",
]
