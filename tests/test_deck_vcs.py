"""Tests for git-backed deck version control.

Everything here runs against a real :class:`DeckVcsRepository` pointed at a temp
directory and a real dulwich repo, per ``tests/README.md`` §1 — the point of the
feature is that git's own semantics hold, which a fake could not demonstrate.

The invariants under test are the ones the design rests on:

- normalization makes line order a function of content, so a reorder is not a diff;
- ``HEAD`` is never detached, so no commit the user makes can become unreachable;
- the user's ``.txt`` receives a decklist and nothing else;
- an externally edited file is recognised by content, since it carries no metadata.
"""

from __future__ import annotations

import pytest

from repositories.deck_vcs_repository import DeckVcsRepository
from repositories.deck_vcs_repository.branches import sanitize_branch_name
from repositories.deck_vcs_repository.diffs import diff_decklists
from repositories.deck_vcs_repository.normalize import (
    decklist_fingerprint,
    normalize_decklist,
)
from services.deck_vcs_service import (
    DeckVcsService,
    ExternalEditStatus,
    deck_key_for,
)
from widgets.panels.deck_history_panel.layout import build_layout

DECK_V1 = "4 Lightning Bolt\n2 Consider\n\nSideboard\n2 Abrade\n"
DECK_V2 = "4 Lightning Bolt\n4 Consider\n\nSideboard\n2 Abrade\n"
DECK_V3 = "4 Lightning Bolt\n4 Consider\n2 Fable of the Mirror-Breaker\n\nSideboard\n2 Abrade\n"


@pytest.fixture
def vcs(tmp_path):
    return DeckVcsRepository(tmp_path / "deck_vcs")


@pytest.fixture
def service(vcs):
    return DeckVcsService(vcs_repo=vcs)


# --------------------------------------------------------------------------- normalization
class TestNormalization:
    """The canonical form is what keeps a diff about cards, not about order."""

    def test_reordering_cards_normalizes_identically(self):
        shuffled = "2 Consider\n4 Lightning Bolt\n\nSideboard\n2 Abrade\n"
        assert normalize_decklist(DECK_V1) == normalize_decklist(shuffled)

    def test_duplicate_lines_are_summed(self):
        split = "4 Lightning Bolt\n1 Consider\n1 Consider\n\nSideboard\n2 Abrade\n"
        assert normalize_decklist(split) == normalize_decklist(DECK_V1)

    def test_blank_line_and_marker_are_the_same_separator(self):
        with_marker = "4 Lightning Bolt\n2 Consider\n\nSideboard\n2 Abrade\n"
        bare_blank = "4 Lightning Bolt\n2 Consider\n\n2 Abrade\n"
        assert normalize_decklist(with_marker) == normalize_decklist(bare_blank)

    def test_output_is_stable_under_renormalization(self):
        once = normalize_decklist(DECK_V1)
        assert normalize_decklist(once) == once

    def test_mainboard_precedes_sideboard_and_each_is_sorted(self):
        text = normalize_decklist("2 Zealot\n4 Alpha\n\nSideboard\n1 Zebra\n1 Aardvark\n")
        assert text == "4 Alpha\n2 Zealot\n\nSideboard\n1 Aardvark\n1 Zebra\n"

    def test_printing_pointer_survives_normalization(self):
        """A trailing Scryfall id is the user's chosen art, not noise."""
        pointer = "4 Lightning Bolt 12345678-1234-1234-1234-123456789abc\n"
        assert "12345678-1234-1234-1234-123456789abc" in normalize_decklist(pointer)

    def test_non_card_lines_are_dropped(self):
        assert normalize_decklist("# my notes\n4 Lightning Bolt\n") == "4 Lightning Bolt\n"

    def test_fractional_counts_survive(self):
        """Averaged decks carry fractional counts; they must not be truncated."""
        assert normalize_decklist("2.5 Consider\n") == "2.5 Consider\n"

    def test_empty_decklist_normalizes_to_empty(self):
        assert normalize_decklist("\n \n") == ""

    def test_fingerprint_ignores_order_but_not_content(self):
        assert decklist_fingerprint(DECK_V1) == decklist_fingerprint(
            "2 Consider\n4 Lightning Bolt\n\nSideboard\n2 Abrade\n"
        )
        assert decklist_fingerprint(DECK_V1) != decklist_fingerprint(DECK_V2)

    def test_same_card_in_both_zones_stays_separate(self):
        text = normalize_decklist("2 Abrade\n\nSideboard\n1 Abrade\n")
        assert text == "2 Abrade\n\nSideboard\n1 Abrade\n"


# --------------------------------------------------------------------------- commits
class TestCommits:
    def test_first_commit_lands_on_the_default_branch(self, vcs):
        vcs.commit_deck("burn", DECK_V1, "v1")
        assert vcs.current_branch("burn") == "main"
        assert vcs.list_branches("burn") == ["main"]

    def test_committed_text_reads_back_normalized(self, vcs):
        """What goes into a commit is the canonical form, not what was handed in."""
        sha = vcs.commit_deck("burn", "2 Consider\n4 Lightning Bolt\n", "v1")
        assert vcs.read_commit_text("burn", sha) == "2 Consider\n4 Lightning Bolt\n"

    def test_history_is_newest_first_and_linked(self, vcs):
        first = vcs.commit_deck("burn", DECK_V1, "v1")
        second = vcs.commit_deck("burn", DECK_V2, "v2")
        commits = vcs.list_commits("burn")
        assert [c.sha for c in commits] == [second, first]
        assert commits[0].parents == (first,)
        assert commits[1].parents == ()

    def test_head_marks_exactly_one_commit(self, vcs):
        vcs.commit_deck("burn", DECK_V1, "v1")
        vcs.commit_deck("burn", DECK_V2, "v2")
        assert sum(1 for c in vcs.list_commits("burn") if c.is_head) == 1

    def test_no_history_reads_as_empty_rather_than_raising(self, vcs):
        assert vcs.list_commits("never-saved") == []
        assert vcs.list_branches("never-saved") == []
        assert vcs.current_branch("never-saved") is None

    def test_deck_key_with_path_separators_is_one_directory(self, vcs):
        """A scraped deck's href looks like a URL fragment, not a path segment."""
        vcs.commit_deck("archetype/modern-burn", DECK_V1, "v1")
        assert vcs.repo_path("archetype/modern-burn").parent == vcs._vcs_root


# --------------------------------------------------------------------------- branching
class TestBranching:
    def test_checkout_of_a_non_tip_creates_a_branch(self, vcs):
        """The detached-HEAD hole: a commit made here must stay reachable."""
        first = vcs.commit_deck("burn", DECK_V1, "v1")
        vcs.commit_deck("burn", DECK_V2, "v2")

        branch, text = vcs.checkout("burn", first)

        assert branch == f"branch-from-{first[:7]}"
        assert vcs.current_branch("burn") == branch
        assert text == vcs.read_commit_text("burn", first)

    def test_commit_after_checking_out_a_non_tip_is_reachable(self, vcs):
        first = vcs.commit_deck("burn", DECK_V1, "v1")
        vcs.commit_deck("burn", DECK_V2, "v2")
        vcs.checkout("burn", first)

        forked = vcs.commit_deck("burn", DECK_V3, "forked")

        # Reachable from a named ref -- the property git GC would otherwise break.
        assert forked in set(vcs.branch_tips("burn").values())
        assert forked in {c.sha for c in vcs.list_commits("burn")}

    def test_checkout_of_an_existing_tip_reuses_that_branch(self, vcs):
        first = vcs.commit_deck("burn", DECK_V1, "v1")
        branch, _ = vcs.checkout("burn", first)
        assert branch == "main"
        assert vcs.list_branches("burn") == ["main"]

    def test_branches_diverge_and_stay_independent(self, vcs):
        first = vcs.commit_deck("burn", DECK_V1, "v1")
        main_tip = vcs.commit_deck("burn", DECK_V2, "v2")
        vcs.checkout("burn", first)
        fork_tip = vcs.commit_deck("burn", DECK_V3, "forked")

        tips = vcs.branch_tips("burn")
        assert tips["main"] == main_tip
        assert tips[f"branch-from-{first[:7]}"] == fork_tip

    def test_switching_branches_restores_that_branchs_decklist(self, vcs):
        first = vcs.commit_deck("burn", DECK_V1, "v1")
        vcs.commit_deck("burn", DECK_V2, "v2")
        vcs.checkout("burn", first)
        vcs.commit_deck("burn", DECK_V3, "forked")

        assert vcs.switch_branch("burn", "main") == vcs.read_commit_text(
            "burn", vcs.branch_tips("burn")["main"]
        )

    def test_commit_after_switching_parents_onto_that_branch(self, vcs):
        first = vcs.commit_deck("burn", DECK_V1, "v1")
        vcs.commit_deck("burn", DECK_V2, "v2")
        vcs.checkout("burn", first)
        vcs.commit_deck("burn", DECK_V3, "forked")
        main_tip = vcs.branch_tips("burn")["main"]

        vcs.switch_branch("burn", "main")
        extended = vcs.commit_deck("burn", "4 Lightning Bolt\n", "back on main")

        commit = next(c for c in vcs.list_commits("burn") if c.sha == extended)
        assert commit.parents == (main_tip,)

    def test_duplicate_branch_names_are_suffixed(self, vcs):
        first = vcs.commit_deck("burn", DECK_V1, "v1")
        assert vcs.create_branch("burn", "testing", first) == "testing"
        assert vcs.create_branch("burn", "testing", first) == "testing-2"
        assert vcs.create_branch("burn", "testing", first) == "testing-3"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("feat: new plan", "feat-new-plan"),
            ("a..b", "a-b"),
            ("  spaced  ", "spaced"),
            ("~^:?*[]", "branch"),
            ("", "branch"),
        ],
    )
    def test_branch_names_are_reduced_to_legal_refs(self, raw, expected):
        assert sanitize_branch_name(raw) == expected


# --------------------------------------------------------------------------- diffs
class TestDiffs:
    def test_diff_reports_added_removed_and_changed(self):
        diff = diff_decklists(DECK_V1, DECK_V3)
        assert [d.name for d in diff.added] == ["Fable of the Mirror-Breaker"]
        assert [(d.name, d.before, d.after) for d in diff.changed] == [("Consider", 2.0, 4.0)]
        assert diff.removed == ()

    def test_removal_is_reported_as_removed(self):
        diff = diff_decklists(DECK_V3, DECK_V1)
        assert [d.name for d in diff.removed] == ["Fable of the Mirror-Breaker"]

    def test_reordering_produces_no_diff(self):
        assert diff_decklists(
            DECK_V1, "2 Consider\n4 Lightning Bolt\n\nSideboard\n2 Abrade\n"
        ).is_empty

    def test_summary_reads_as_card_changes(self):
        assert diff_decklists(DECK_V1, DECK_V3).summary() == (
            "+2 Fable of the Mirror-Breaker, +2 Consider"
        )

    def test_summary_truncates_rather_than_becoming_a_decklist(self):
        big = "".join(f"1 Card {i}\n" for i in range(10))
        summary = diff_decklists("", big).summary(limit=3)
        assert summary.endswith("+7 more")

    def test_diff_between_arbitrary_commits(self, vcs):
        first = vcs.commit_deck("burn", DECK_V1, "v1")
        vcs.commit_deck("burn", DECK_V2, "v2")
        third = vcs.commit_deck("burn", DECK_V3, "v3")

        diff = vcs.diff_commits("burn", first, third)
        assert [d.name for d in diff.added] == ["Fable of the Mirror-Breaker"]

    def test_sideboard_changes_are_kept_apart_from_mainboard(self):
        diff = diff_decklists("2 Abrade\n", "2 Abrade\n\nSideboard\n2 Abrade\n")
        assert [(d.name, d.is_sideboard) for d in diff.added] == [("Abrade", True)]

    def test_unified_diff_covers_the_changed_lines(self, vcs):
        first = vcs.commit_deck("burn", DECK_V1, "v1")
        third = vcs.commit_deck("burn", DECK_V3, "v3")
        body = "\n".join(vcs.unified_diff("burn", first, third))
        assert "+2 Fable of the Mirror-Breaker" in body


# --------------------------------------------------------------------------- service
class TestService:
    def test_unchanged_save_records_no_version(self, service):
        service.record_save("burn", DECK_V1)
        assert service.record_save("burn", DECK_V1) is None

    def test_reordered_save_records_no_version(self, service):
        service.record_save("burn", DECK_V1)
        reordered = "2 Consider\n4 Lightning Bolt\n\nSideboard\n2 Abrade\n"
        assert service.record_save("burn", reordered) is None

    def test_empty_save_records_no_version(self, service):
        assert service.record_save("burn", "   \n") is None

    def test_messages_default_to_the_change_summary(self, service):
        service.record_save("burn", DECK_V1)
        service.record_save("burn", DECK_V3)
        assert service.build_graph("burn")[0].commit.message == (
            "+2 Fable of the Mirror-Breaker, +2 Consider"
        )

    def test_first_version_is_named_rather_than_diffed(self, service):
        service.record_save("burn", DECK_V1)
        assert service.build_graph("burn")[0].commit.message == "Initial version"

    def test_checkout_writes_only_the_decklist_to_the_users_file(self, service, tmp_path):
        """The constraint the whole feature lives under: no metadata in the .txt."""
        deck_file = tmp_path / "Mono Red.txt"
        first = service.record_save("burn", DECK_V1)
        service.record_save("burn", DECK_V3)

        service.checkout("burn", first, deck_file=deck_file)

        written = deck_file.read_text(encoding="utf-8")
        assert written == normalize_decklist(DECK_V1)
        # Nothing git-shaped leaked in, and the file still parses as a decklist.
        assert "commit" not in written.lower()
        assert all(
            line.split(" ", 1)[0].replace(".", "").isdigit()
            for line in written.splitlines()
            if line and line != "Sideboard"
        )

    def test_checkout_without_a_file_touches_no_file(self, service, tmp_path):
        first = service.record_save("burn", DECK_V1)
        service.record_save("burn", DECK_V3)
        service.checkout("burn", first, deck_file=None)
        assert list(tmp_path.glob("*.txt")) == []

    def test_version_text_does_not_move_head(self, service):
        first = service.record_save("burn", DECK_V1)
        second = service.record_save("burn", DECK_V3)
        service.version_text("burn", first)
        head = next(c for c in service.build_graph("burn") if c.commit.is_head)
        assert head.sha == second


# --------------------------------------------------------------------------- identity
class TestExternalEdits:
    def test_no_history_is_not_an_external_edit(self, service):
        assert service.identify("burn", DECK_V1).status is ExternalEditStatus.NO_HISTORY

    def test_a_committed_decklist_is_recognised(self, service):
        sha = service.record_save("burn", DECK_V1)
        verdict = service.identify("burn", DECK_V1)
        assert verdict.status is ExternalEditStatus.KNOWN
        assert verdict.sha == sha

    def test_recognition_survives_reordering(self, service):
        service.record_save("burn", DECK_V1)
        reordered = "2 Consider\n4 Lightning Bolt\n\nSideboard\n2 Abrade\n"
        assert service.identify("burn", reordered).status is ExternalEditStatus.KNOWN

    def test_an_older_version_is_still_recognised(self, service):
        first = service.record_save("burn", DECK_V1)
        service.record_save("burn", DECK_V3)
        assert service.identify("burn", DECK_V1).sha == first

    def test_an_unseen_decklist_is_unattributed(self, service):
        service.record_save("burn", DECK_V1)
        assert service.identify("burn", "4 Shock\n").status is ExternalEditStatus.UNATTRIBUTED

    def test_attaching_an_external_edit_extends_the_current_branch(self, service):
        first = service.record_save("burn", DECK_V1)
        sha = service.attach_unattributed("burn", "4 Shock\n")
        commit = next(c for c in service.build_graph("burn") if c.sha == sha)
        assert commit.commit.parents == (first,)
        assert service.identify("burn", "4 Shock\n").status is ExternalEditStatus.KNOWN

    def test_attaching_onto_a_new_branch_leaves_the_old_tip_alone(self, service):
        first = service.record_save("burn", DECK_V1)
        service.attach_unattributed("burn", "4 Shock\n", as_branch="rescued")
        assert service.vcs_repo.branch_tips("burn")["main"] == first
        assert service.current_branch("burn") == "rescued"


# --------------------------------------------------------------------------- deck keys
class TestDeckKeys:
    def test_a_file_backed_deck_is_keyed_by_its_stem(self, tmp_path):
        assert deck_key_for({"href": "ignored"}, tmp_path / "Mono Red.txt") == "mono red"

    def test_a_fileless_deck_falls_back_to_its_href(self):
        assert deck_key_for({"href": "Archetype/Burn"}, None) == "archetype/burn"

    def test_an_unknown_deck_is_manual(self):
        assert deck_key_for(None, None) == "manual"


# --------------------------------------------------------------------------- graph layout
class TestGraphLayout:
    def test_a_linear_history_occupies_one_lane(self, service):
        service.record_save("burn", DECK_V1)
        service.record_save("burn", DECK_V2)
        service.record_save("burn", DECK_V3)

        layout = build_layout(service.build_graph("burn"))
        assert layout.lane_count == 1
        assert [n.row for n in sorted(layout.nodes, key=lambda n: n.row)] == [0, 1, 2]
        assert not any(edge.is_fork for edge in layout.edges)

    def test_a_fork_takes_a_second_lane(self, service):
        first = service.record_save("burn", DECK_V1)
        service.record_save("burn", DECK_V2)
        service.checkout("burn", first)
        service.record_save("burn", DECK_V3)

        layout = build_layout(service.build_graph("burn"))
        assert layout.lane_count == 2
        assert sum(1 for edge in layout.edges if edge.is_fork) == 1

    def test_the_fork_edge_lands_on_the_shared_ancestor(self, service):
        first = service.record_save("burn", DECK_V1)
        service.record_save("burn", DECK_V2)
        service.checkout("burn", first)
        service.record_save("burn", DECK_V3)

        layout = build_layout(service.build_graph("burn"))
        fork = next(edge for edge in layout.edges if edge.is_fork)
        assert fork.parent_sha == first

    def test_every_child_is_drawn_above_its_parent(self, service):
        first = service.record_save("burn", DECK_V1)
        service.record_save("burn", DECK_V2)
        service.checkout("burn", first)
        service.record_save("burn", DECK_V3)

        layout = build_layout(service.build_graph("burn"))
        rows = {node.sha: node.row for node in layout.nodes}
        for edge in layout.edges:
            assert rows[edge.child_sha] < rows[edge.parent_sha]

    def test_rows_are_unique(self, service):
        first = service.record_save("burn", DECK_V1)
        service.record_save("burn", DECK_V2)
        service.checkout("burn", first)
        service.record_save("burn", DECK_V3)

        layout = build_layout(service.build_graph("burn"))
        rows = [node.row for node in layout.nodes]
        assert sorted(rows) == list(range(len(rows)))

    def test_an_empty_history_lays_out_to_nothing(self):
        layout = build_layout([])
        assert layout.nodes == () and layout.edges == () and layout.lane_count == 0

    def test_the_root_commit_is_the_last_row(self, service):
        first = service.record_save("burn", DECK_V1)
        service.record_save("burn", DECK_V2)
        service.checkout("burn", first)
        service.record_save("burn", DECK_V3)

        layout = build_layout(service.build_graph("burn"))
        last = max(layout.nodes, key=lambda n: n.row)
        assert last.sha == first


class TestSaveKeyAgreesWithTheHistoryPanel:
    """A save and the History tab must key the same deck the same way (#1053).

    The commit was written under the saved file's stem while the panel, for a
    deck that had no file behind it, still keyed off the scraped record's
    ``href`` -- so a Save As under any name but the deck's own committed to one
    repo and displayed another, which read as "saving creates no history".
    """

    @staticmethod
    def _scraped() -> dict:
        return {
            "href": "andyscwilson, 5-0, 2026-09-19_modern league",
            "name": "AndysCwilson",
            "source": "goldfish",
        }

    def test_scraped_deck_keys_diverge_before_the_record_is_updated(self, tmp_path) -> None:
        from services.deck_vcs_service import deck_key_for

        deck = self._scraped()
        saved = tmp_path / "My Burn Deck.txt"

        # What the save used, versus what the panel would have asked for.
        assert deck_key_for(deck, saved) != deck_key_for(deck, None)

    def test_pointing_the_record_at_the_saved_file_makes_them_agree(self, tmp_path) -> None:
        from pathlib import Path

        from services.deck_vcs_service import deck_key_for

        deck = self._scraped()
        saved = tmp_path / "My Burn Deck.txt"
        save_key = deck_key_for(deck, saved)

        # This is what the save handler now does to the in-memory record.
        deck["path"] = str(saved)
        deck["source"] = "file"

        assert deck_key_for(deck, Path(deck["path"])) == save_key


class TestBaselineRootIsMarked:
    """A baseline root is flagged so the graph can omit its fixed timestamp."""

    def test_baseline_root_is_flagged_and_ordinary_commits_are_not(self, tmp_path) -> None:
        repo = DeckVcsRepository(tmp_path / "deck_vcs")
        deck_key = "flagged"
        repo.seed_baseline_root(
            deck_key, "4 Lightning Bolt\n", archetype="Burn", mtg_format="Modern"
        )
        repo.commit_deck(deck_key, "4 Lightning Bolt\n2 Consider\n", message="a real save")

        commits = {c.message: c for c in repo.list_commits(deck_key)}
        root = next(c for c in commits.values() if not c.parents)
        assert root.is_baseline is True
        assert commits["a real save"].is_baseline is False
