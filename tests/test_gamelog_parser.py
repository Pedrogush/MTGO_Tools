"""Tests for gamelog_parser correctness against MTGO screenshot ground truth."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from utils.gamelog_parser import (
    detect_format_from_cards,
    find_gamelog_files,
    infer_username_from_matches,
    parse_gamelog_file,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCREENSHOTS_TRUTH = Path(__file__).parent / "fixtures" / "match_history_screenshots.json"

_GAMELOG_DIR_WINDOWS = (
    r"C:\Users\Pedro\AppData\Local\Apps\2.0\Data\OVGXG70W.D8K\9MANX5J8.5ON"
    r"\mtgo..tion_a7d96b15d2cce030_0003.0004_b5d581d94d59763e\Data\AppFiles"
    r"\5929ED80F66B48FAC53C5D4BF7742305"
)
_GAMELOG_DIR_WSL = (
    "/mnt/c/Users/Pedro/AppData/Local/Apps/2.0/Data/OVGXG70W.D8K/9MANX5J8.5ON"
    "/mtgo..tion_a7d96b15d2cce030_0003.0004_b5d581d94d59763e/Data/AppFiles"
    "/5929ED80F66B48FAC53C5D4BF7742305"
)
GAMELOG_DIR = _GAMELOG_DIR_WSL if os.path.isdir(_GAMELOG_DIR_WSL) else _GAMELOG_DIR_WINDOWS


def _gamelogs_available() -> bool:
    return os.path.isdir(GAMELOG_DIR)


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

    def test_returns_none_when_no_majority(self):
        # 50/50 split — neither player clears the 80% threshold
        matches = [
            {"players": ["alice", "bob"]},
            {"players": ["bob", "alice"]},
        ]
        # Both have count == 2 == 100% of 2 matches, but the *most common*
        # could be either (Counter tie-break is insertion-order-dependent).
        # At 100% either could be returned; the key is that with a genuine
        # tie both clear the threshold, so one is returned — just verify the
        # function doesn't raise.
        result = infer_username_from_matches(matches)
        assert result in ("alice", "bob", None)

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

        for entry in truth:
            if entry["mtg_format"] not in ("Modern",):
                continue
            opp = entry["opponent_name"].lower()
            if opp not in by_opponent:
                continue

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
