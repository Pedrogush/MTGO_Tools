"""Tests for gamelog_parser correctness against MTGO screenshot ground truth."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.gamelog_service import (
    detect_format_from_cards,
    extract_cards_played,
    extract_players,
    find_all_gamelog_dirs,
    find_gamelog_files,
    infer_username_from_matches,
    normalize_player_name,
    parse_game_results,
    parse_gamelog_file,
    parse_match_score,
    parse_mulligan_data,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCREENSHOTS_TRUTH = Path(__file__).parent / "fixtures" / "match_history_screenshots.json"

# Discover the MTGO GameLog directory dynamically rather than hard-coding a
# ClickOnce install-hash path (which goes stale on every MTGO update). This
# reuses the production filesystem scan, which auto-detects Windows and WSL
# AppData bases and returns dirs newest-first.
_GAMELOG_DIRS = find_all_gamelog_dirs()
GAMELOG_DIR = _GAMELOG_DIRS[0] if _GAMELOG_DIRS else None


def _gamelogs_available() -> bool:
    return GAMELOG_DIR is not None and os.path.isdir(GAMELOG_DIR)


def _load_truth() -> list[dict]:
    with open(SCREENSHOTS_TRUTH) as f:
        return json.load(f)


def _result_to_score(result: str) -> tuple[int, int]:
    """Convert 'W-L-D' screenshot result to (wins, losses) tuple."""
    parts = result.split("-")
    return int(parts[0]), int(parts[1])


# ---------------------------------------------------------------------------
# Unit tests (no files required)
# ---------------------------------------------------------------------------


class TestInferUsername:
    def test_infers_from_majority_player(self):
        matches = [
            {"players": ["alice", "bob"]},
            {"players": ["alice", "charlie"]},
            {"players": ["alice", "dave"]},
        ]
        assert infer_username_from_matches(matches) == "alice"

    def test_returns_none_on_empty(self):
        assert infer_username_from_matches([]) is None

    def test_tie_at_full_attendance_returns_most_common_insertion_order(self):
        # Both players appear in every match (100% attendance), so both clear
        # the 80% threshold. Counter.most_common breaks ties by first-seen
        # insertion order, so the player encountered first ("alice") is returned.
        matches = [
            {"players": ["alice", "bob"]},
            {"players": ["bob", "alice"]},
        ]
        assert infer_username_from_matches(matches) == "alice"

    def test_requires_80_percent_threshold(self):
        # alice in 3/5 = 60% — below threshold
        matches = [
            {"players": ["alice", "bob"]},
            {"players": ["alice", "charlie"]},
            {"players": ["alice", "dave"]},
            {"players": ["eve", "frank"]},
            {"players": ["eve", "grace"]},
        ]
        result = infer_username_from_matches(matches)
        # alice: 3/5 = 60%, eve: 2/5 = 40% — neither reaches 80%
        assert result is None

    def test_all_same_player(self):
        username = os.environ.get("MTGO_USERNAME", "testplayer")
        matches = [{"players": [username, f"opp{i}"]} for i in range(100)]
        assert infer_username_from_matches(matches) == username


# ---------------------------------------------------------------------------
# Unit tests for normalize_player_name (storage <-> display encoding)
# ---------------------------------------------------------------------------


class TestNormalizePlayerName:
    def test_to_storage_substitutes_space_and_period(self):
        assert normalize_player_name("a b.c", True) == "a+b*c"

    def test_from_storage_inverts_substitution(self):
        assert normalize_player_name("a+b*c", False) == "a b.c"

    def test_round_trip_simple_name(self):
        original = "Player One"
        assert normalize_player_name(normalize_player_name(original, True), False) == original

    def test_plain_name_is_unchanged(self):
        assert normalize_player_name("alice", True) == "alice"
        assert normalize_player_name("alice", False) == "alice"

    def test_name_containing_literal_plus_does_not_round_trip(self):
        # Documents a known limitation: a name that already contains '+' or '*'
        # cannot round-trip, because the display->storage->display path is lossy.
        # storage form of "a+b" is "a+b" (no spaces/periods to encode), and
        # decoding it turns the literal '+' into a space.
        assert normalize_player_name("a+b", True) == "a+b"
        assert normalize_player_name("a+b", False) == "a b"


# ---------------------------------------------------------------------------
# Unit tests for the binary-log text parser (synthetic content, no MTGO needed)
# ---------------------------------------------------------------------------


def _card_ref(name: str) -> str:
    """Render a card reference in the GameLog binary text format."""
    return f"@[{name}@:0,0:@]"


def _synthetic_match(*, include_match_line: bool = True) -> str:
    """Build a minimal but realistic GameLog text body for two players.

    Alice plays Lightning Bolt and wins both games; Bob mulligans once in game 2.
    """
    lines = [
        "Wed Dec 04 14:23:10 PST 2024",
        "@PAlice joined the game",
        "@PBob joined the game",
        "@PAlice chooses to play first",
        f"@PAlice plays {_card_ref('Lightning Bolt')}",
        f"@PBob casts {_card_ref('Counterspell')}",
        "@PAlice wins the game",
        "@PBob chooses to play first",
        "@PBob mulligans to six cards",
        f"@PAlice casts {_card_ref('Snapcaster Mage')}",
        "@PAlice wins the game",
    ]
    if include_match_line:
        lines.append("@PAlice wins the match 2-0")
    return "\n".join(lines)


class TestExtractPlayers:
    def test_extracts_both_players(self):
        players = extract_players(_synthetic_match())
        assert sorted(players) == ["Alice", "Bob"]

    def test_returns_empty_when_no_join_lines(self):
        assert extract_players("Wed Dec 04 14:23:10 PST 2024\nrandom content") == []

    def test_deduplicates_repeated_joins(self):
        content = "@PAlice joined the game\n@PAlice joined the game\n@PBob joined the game"
        assert sorted(extract_players(content)) == ["Alice", "Bob"]


class TestExtractCardsPlayed:
    def test_attributes_cards_to_correct_player(self):
        content = _synthetic_match()
        assert extract_cards_played(content, "Alice") == ["Lightning Bolt", "Snapcaster Mage"]
        assert extract_cards_played(content, "Bob") == ["Counterspell"]

    def test_ignores_non_own_verbs(self):
        # A card referenced as the target of an attack must not be attributed.
        content = f"@PAlice is being attacked by {_card_ref('Goblin Guide')}"
        assert extract_cards_played(content, "Alice") == []

    def test_extracts_discard_and_reveal_verbs(self):
        content = (
            f"@PAlice discards {_card_ref('Faithless Looting')}\n"
            f"@PAlice reveals {_card_ref('Tarmogoyf')}"
        )
        assert extract_cards_played(content, "Alice") == ["Faithless Looting", "Tarmogoyf"]


class TestParseMatchScore:
    def test_parses_wins_the_match(self):
        assert parse_match_score("@PAlice wins the match 2-1") == ("Alice", 2, 1)

    def test_parses_leads_the_match(self):
        assert parse_match_score("@PBob leads the match 1-0") == ("Bob", 1, 0)

    def test_prefers_last_match_line(self):
        # parse_match_score scans from the end, so the final result wins.
        content = "@PAlice leads the match 1-0\n@PAlice wins the match 2-1"
        assert parse_match_score(content) == ("Alice", 2, 1)

    def test_returns_none_when_absent(self):
        assert parse_match_score("@PAlice plays a land") is None


class TestParseGameResults:
    def test_records_one_result_per_game(self):
        content = _synthetic_match()
        results = parse_game_results(content)
        assert [g["game_num"] for g in results] == [1, 2]
        assert results[0] == {"game_num": 1, "winner": "Alice", "method": "win"}

    def test_records_concession(self):
        content = "@PAlice chooses to play first\n@PBob has conceded from the game"
        results = parse_game_results(content)
        assert results == [{"game_num": 1, "loser": "Bob", "method": "concession"}]

    def test_only_first_result_per_game_is_kept(self):
        # Two "wins the game" lines in the same game must collapse to one record.
        content = "@PAlice chooses to play first\n" "@PAlice wins the game\n" "@PBob wins the game"
        results = parse_game_results(content)
        assert len(results) == 1
        assert results[0]["winner"] == "Alice"


class TestParseMulliganData:
    def test_maps_word_count_to_cards_kept(self):
        # "mulligans to six cards" in game 2 => 7 - 6 = 1 mulligan for game 2.
        results = parse_mulligan_data(_synthetic_match())
        assert results["Bob"] == [0, 1]

    def test_no_mulligans_returns_empty_dict(self):
        content = "@PAlice chooses to play first\n@PAlice wins the game"
        assert parse_mulligan_data(content) == {}


class TestParseGamelogFileSynthetic:
    """Drive parse_gamelog_file with temp files of synthetic content.

    These cover the orchestrator branches (match-score path, game-results
    fallback, <2-players early return, malformed-file exception swallowing)
    portably, without a live MTGO GameLog directory.
    """

    def _write(self, tmp_path, content: str, name: str = "Match_GameLog_123.dat") -> str:
        p = tmp_path / name
        p.write_text(content, encoding="latin1")
        return str(p)

    def test_parses_normal_match_via_match_score(self, tmp_path):
        path = self._write(tmp_path, _synthetic_match())
        result = parse_gamelog_file(path)
        assert result is not None
        assert sorted(result["players"]) == ["Alice", "Bob"]
        assert result["winner"] == "Alice"
        assert result["match_score"] == "2-0"
        assert result["match_id"] == "123"
        assert "Lightning Bolt" in (result["player1_deck"] + result["player2_deck"])

    def test_falls_back_to_game_results_without_match_line(self, tmp_path):
        # Omitting the "wins the match" line forces the game-results count path.
        path = self._write(tmp_path, _synthetic_match(include_match_line=False))
        result = parse_gamelog_file(path)
        assert result is not None
        # Alice won both games; player order is length-sorted (both len 5 -> stable).
        assert result["winner"] in ("Alice", "Bob")
        # Alice won 2 games, Bob 0, so Alice must be the winner regardless of order.
        assert result["winner"] == "Alice"
        assert result["match_score"] in ("2-0", "0-2")

    def test_returns_none_for_single_player(self, tmp_path):
        path = self._write(tmp_path, "Wed Dec 04 14:23:10 PST 2024\n@PAlice joined the game")
        assert parse_gamelog_file(path) is None

    def test_returns_none_for_missing_file(self, tmp_path):
        # A path that doesn't exist must be swallowed and return None, not raise.
        assert parse_gamelog_file(str(tmp_path / "does_not_exist.dat")) is None


# ---------------------------------------------------------------------------
# Unit tests for detect_format_from_cards
# ---------------------------------------------------------------------------


def _make_manager(card_legalities: dict[str, dict[str, str]]) -> MagicMock:
    """Build a mock CardDataManager where each card name maps to given legalities."""
    manager = MagicMock()
    manager.is_loaded = True

    def get_card(name: str):
        legalities = card_legalities.get(name.lower())
        if legalities is None:
            return None
        entry = MagicMock()
        entry.legalities = legalities
        return entry

    manager.get_card.side_effect = get_card
    return manager


class TestDetectFormatFromCards:
    def _modern_card(self) -> dict[str, str]:
        return {"modern": "Legal", "legacy": "Legal", "vintage": "Legal"}

    def _legacy_only_card(self) -> dict[str, str]:
        return {"legacy": "Legal", "vintage": "Legal"}

    def _vintage_only_card(self) -> dict[str, str]:
        return {"vintage": "Legal"}

    def _pioneer_card(self) -> dict[str, str]:
        return {"pioneer": "Legal", "modern": "Legal", "legacy": "Legal", "vintage": "Legal"}

    def _standard_card(self) -> dict[str, str]:
        return {
            "standard": "Legal",
            "pioneer": "Legal",
            "modern": "Legal",
            "legacy": "Legal",
            "vintage": "Legal",
        }

    def _build_deck(self, legalities: dict[str, str], count: int = 10) -> dict[str, dict[str, str]]:
        return {f"card{i}": legalities for i in range(count)}

    def test_returns_unknown_without_card_manager(self):
        assert detect_format_from_cards(["Force of Will"] * 10) == "Unknown"

    def test_returns_last_parsed_format_without_card_manager(self):
        assert (
            detect_format_from_cards(["Force of Will"] * 10, last_parsed_format="Modern")
            == "Modern"
        )

    def test_returns_unknown_when_manager_not_loaded(self):
        manager = MagicMock()
        manager.is_loaded = False
        assert detect_format_from_cards(["Force of Will"] * 10, manager) == "Unknown"

    def test_returns_last_parsed_format_when_manager_not_loaded(self):
        manager = MagicMock()
        manager.is_loaded = False
        assert (
            detect_format_from_cards(["Force of Will"] * 10, manager, last_parsed_format="Legacy")
            == "Legacy"
        )

    def test_detects_format_with_few_cards(self):
        # No minimum card count — even a single recognised card is enough
        manager = _make_manager({"card0": self._modern_card()})
        assert detect_format_from_cards(["card0"] * 3, manager) == "Modern"

    def test_returns_last_parsed_format_when_no_legality_data(self):
        # All cards unknown to the index → fall back to last_parsed_format
        manager = _make_manager({})
        assert (
            detect_format_from_cards(["token1", "token2"], manager, last_parsed_format="Modern")
            == "Modern"
        )

    def test_detects_modern(self):
        deck = self._build_deck(self._modern_card())
        manager = _make_manager(deck)
        result = detect_format_from_cards(list(deck.keys()), manager)
        assert result == "Modern"

    def test_detects_legacy_when_non_modern_card_present(self):
        deck = {
            **self._build_deck(self._modern_card(), 9),
            "force_of_will": self._legacy_only_card(),
        }
        manager = _make_manager(deck)
        result = detect_format_from_cards(list(deck.keys()), manager)
        assert result == "Legacy"

    def test_detects_vintage_when_power_card_present(self):
        deck = {
            **self._build_deck(self._modern_card(), 9),
            "black_lotus": self._vintage_only_card(),
        }
        manager = _make_manager(deck)
        result = detect_format_from_cards(list(deck.keys()), manager)
        assert result == "Vintage"

    def test_detects_standard_when_all_standard_legal(self):
        deck = self._build_deck(self._standard_card())
        manager = _make_manager(deck)
        result = detect_format_from_cards(list(deck.keys()), manager)
        assert result == "Standard"

    def test_skips_cards_not_found_in_index(self):
        # 10 modern-legal + 5 unknown (tokens, etc.) — should still detect Modern
        deck = self._build_deck(self._modern_card())
        manager = _make_manager(deck)
        cards = list(deck.keys()) + ["token1", "token2", "token3", "token4", "token5"]
        result = detect_format_from_cards(cards, manager)
        assert result == "Modern"

    def test_skips_cards_with_empty_legalities(self):
        # Cards with {} legalities (e.g. MDFCs with alias collision) are ignored
        deck = {**self._build_deck(self._modern_card()), "mdfc_alias": {}}
        manager = _make_manager(deck)
        result = detect_format_from_cards(list(deck.keys()), manager)
        assert result == "Modern"

    def test_returns_last_parsed_format_when_no_common_format(self):
        # Two cards each legal in mutually exclusive formats — intersection is empty,
        # falls back to last_parsed_format (default "Unknown")
        deck = {
            **{f"vintage_only_{i}": {"vintage": "Legal"} for i in range(5)},
            **{f"standard_only_{i}": {"standard": "Legal"} for i in range(5)},
        }
        manager = _make_manager(deck)
        assert detect_format_from_cards(list(deck.keys()), manager) == "Unknown"
        assert (
            detect_format_from_cards(list(deck.keys()), manager, last_parsed_format="Modern")
            == "Modern"
        )


# ---------------------------------------------------------------------------
# Integration tests (require actual GameLog files)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _gamelogs_available(),
    reason="MTGO GameLog directory not available on this machine",
)
class TestGamelogParserVsScreenshots:
    """Compare gamelog parser output against MTGO UI screenshot ground truth.

    The parser uses file modification time as the match timestamp (the binary
    log format doesn't expose the start time), so timestamps are expected to
    differ from the MTGO UI by roughly the match duration (typically 20–40 min).
    We match records by opponent name only.
    """

    @pytest.fixture(scope="class")
    def parsed_matches(self):
        files = find_gamelog_files(GAMELOG_DIR)
        return [r for f in files if (r := parse_gamelog_file(f))]

    @pytest.fixture(scope="class")
    def inferred_username(self, parsed_matches):
        return infer_username_from_matches(parsed_matches)

    @pytest.fixture(scope="class")
    def truth(self):
        return _load_truth()

    # ------------------------------------------------------------------

    def test_infers_username_as_local_username(self, inferred_username, monkeypatch):
        local_username = os.environ.get("MTGO_USERNAME")
        if local_username is None:
            monkeypatch.setenv("MTGO_USERNAME", "test_player")
            assert inferred_username is not None and inferred_username != ""
        else:
            assert inferred_username == local_username

    def test_parsed_count_in_expected_range(self, parsed_matches, truth):
        """Total parsed matches should be at least as many as Modern entries in truth.

        The screenshots only cover a partial view of the history; gamelogs may also
        include matches not visible in any screenshot (different session dates).
        We just verify the parser isn't dramatically under-counting.
        """
        modern_truth = [t for t in truth if t["mtg_format"] in ("Modern", "Unknown")]
        # Gamelogs ≥ Modern truth entries (screenshots may omit some periods)
        assert len(parsed_matches) >= len(modern_truth)

    def _build_parsed_by_opponent(self, parsed_matches, username):
        """Index parsed matches by opponent name (lower-case)."""
        by_opponent: dict[str, list[dict]] = {}
        for m in parsed_matches:
            players = m.get("players", [])
            opp = None
            if players[0].lower() == username.lower() and len(players) > 1:
                opp = players[1]
            elif len(players) > 1 and players[1].lower() == username.lower():
                opp = players[0]
            if opp:
                by_opponent.setdefault(opp.lower(), []).append(m)
        return by_opponent

    def test_match_results_correct_for_modern_sample(
        self, parsed_matches, inferred_username, truth
    ):
        """Spot-check Modern matches: verify win/loss agrees with screenshots.

        Matching is done by (opponent, date window) because the same opponent can
        appear multiple times.  The parser timestamp is the file mtime (match-end),
        while the screenshot timestamp is the match-start.  A typical match runs
        20–90 min, so we allow a 3-hour tolerance window.
        """
        from datetime import datetime, timedelta

        by_opponent = self._build_parsed_by_opponent(parsed_matches, inferred_username)
        WINDOW = timedelta(minutes=60)  # 25 min clock per player = 50 min max match

        mismatches = []
        checked = 0
        in_window_candidates = 0

        for entry in truth:
            if entry["mtg_format"] not in ("Modern",):
                continue
            opp = entry["opponent_name"].lower()
            if opp not in by_opponent:
                continue

            in_window_candidates += 1

            # Parse screenshot timestamp (match start time)
            try:
                sc_dt = datetime.strptime(entry["match_datetime"], "%m/%d/%Y %I:%M:%S %p")
            except ValueError:
                continue

            our_wins, our_losses = _result_to_score(entry["match_result"])
            expected_win = our_wins > our_losses

            # Find the closest gamelog entry by timestamp
            best = min(
                by_opponent[opp],
                key=lambda m: abs((m["timestamp"] - sc_dt).total_seconds()),
            )
            delta = abs((best["timestamp"] - sc_dt).total_seconds())
            if delta > WINDOW.total_seconds():
                # No gamelog within the window — probably a different-computer match
                continue

            players = best["players"]
            winner = best["winner"]
            score_str = best["match_score"]
            try:
                p1w, p2w = map(int, score_str.split("-"))
            except ValueError:
                continue

            if players[0].lower() == inferred_username.lower():
                our_score, opp_score = p1w, p2w
            else:
                our_score, opp_score = p2w, p1w

            parser_win = our_score > opp_score
            if parser_win != expected_win:
                mismatches.append(
                    {
                        "opponent": entry["opponent_name"],
                        "screenshot_dt": entry["match_datetime"],
                        "screenshot_result": entry["match_result"],
                        "parser_dt": best["timestamp"].strftime("%m/%d/%Y %I:%M:%S %p"),
                        "parser_score": score_str,
                        "parser_winner": winner,
                    }
                )
            checked += 1

        assert checked > 0, "No Modern matches were cross-referenced within the time window"
        # Guard against silent under-matching: if a parser/timestamp regression
        # caused most candidates to fall outside the window (or fail to parse),
        # `checked` would collapse to 1 while still passing `checked > 0`. Require
        # the majority of opponent-matched Modern candidates to actually line up.
        if in_window_candidates:
            assert checked >= max(1, in_window_candidates // 2), (
                f"only {checked}/{in_window_candidates} opponent-matched Modern truth "
                "entries cross-referenced within the time window"
            )
        assert mismatches == [], f"{len(mismatches)} result mismatches found:\n" + "\n".join(
            str(m) for m in mismatches
        )

    def test_winner_never_none(self, parsed_matches):
        """Every parsed match should have a determinable winner."""
        no_winner = [m for m in parsed_matches if m.get("winner") is None]
        assert no_winner == [], f"{len(no_winner)} matches have winner=None"

    def test_all_matches_contain_local_username(self, parsed_matches, inferred_username):
        """Every gamelog on this machine should involve the local user."""
        missing = [m for m in parsed_matches if inferred_username not in m.get("players", [])]
        assert missing == [], f"{len(missing)} matches don't include {inferred_username}"
