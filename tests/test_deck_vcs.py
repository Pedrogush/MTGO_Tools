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

import itertools
import shutil
from types import SimpleNamespace

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


@pytest.fixture
def pinned_commit_clock(monkeypatch):
    """Give every commit its own second, so history order is topology, not a coin toss.

    dulwich stamps a commit with ``time.time()`` and its walker orders by commit
    date, breaking ties on the commit's sha (``ShaFile.__lt__``). Every test here
    commits well inside one second, so any assertion about which of two *branch
    tips* comes first rests on which decklist happened to hash lower.

    A linear history needs none of this -- a parent is only queued once its child
    has been popped, so topology decides -- but a fork seeds both tips into the
    walker at once, and there the tie-break is the whole answer. The baseline
    root pins its epoch against the same class of accident (``BASELINE_EPOCH``).

    Only dulwich's own names for the module are replaced, so nothing else in the
    process sees a different clock -- and both modules that stamp a commit are
    covered, since dulwich has moved that line between them. A test that uses
    this asserts the stamps came out distinct, so the pinning cannot lapse
    quietly if it moves again.
    """
    import dulwich.repo
    import dulwich.worktree

    ticks = itertools.count(1_600_000_000)
    clock = SimpleNamespace(time=lambda: float(next(ticks)))
    for module in (dulwich.repo, dulwich.worktree):
        monkeypatch.setattr(module, "time", clock)


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
        """What goes into a commit is the canonical form, not what was handed in.

        The text handed in is deliberately *not* already sorted, so removing the
        ``normalize_decklist`` call in ``commit_deck`` fails here rather than
        leaving the invariant's only test green.
        """
        sha = vcs.commit_deck("burn", "4 Lightning Bolt\n2 Consider\n", "v1")
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
        """A scraped deck's href looks like a URL fragment, not a path segment.

        Trusted as one it would put the repo two levels down, under a directory
        the root never expects to hold anything but deck repos -- so the check
        is on what landed on disk, not on what ``repo_path`` says about itself.
        """
        vcs.commit_deck("archetype/modern-burn", DECK_V1, "v1")

        assert [p.name for p in vcs._vcs_root.iterdir()] == ["archetype_modern-burn"]
        assert not (vcs._vcs_root / "archetype").exists()
        # ...and the history is readable through the key it was written with.
        assert [c.message for c in vcs.list_commits("archetype/modern-burn")] == ["v1"]


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
        # Searching for the word "commit" would not do it: *Commit // Memory* is
        # a real card, so a clean file can contain it. The sha of the version
        # being written out cannot.
        assert first not in written
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

    def test_a_fork_takes_a_second_lane(self, service, pinned_commit_clock):
        first = service.record_save("burn", DECK_V1)
        service.record_save("burn", DECK_V2)
        service.checkout("burn", first)
        service.record_save("burn", DECK_V3)

        layout = build_layout(service.build_graph("burn"))
        assert layout.lane_count == 2
        assert sum(1 for edge in layout.edges if edge.is_fork) == 1

    def test_the_fork_edge_lands_on_the_shared_ancestor(self, service, pinned_commit_clock):
        first = service.record_save("burn", DECK_V1)
        service.record_save("burn", DECK_V2)
        service.checkout("burn", first)
        service.record_save("burn", DECK_V3)

        layout = build_layout(service.build_graph("burn"))
        fork = next(edge for edge in layout.edges if edge.is_fork)
        assert fork.parent_sha == first

    def test_every_child_is_drawn_above_its_parent(self, service, pinned_commit_clock):
        first = service.record_save("burn", DECK_V1)
        service.record_save("burn", DECK_V2)
        service.checkout("burn", first)
        service.record_save("burn", DECK_V3)

        layout = build_layout(service.build_graph("burn"))
        rows = {node.sha: node.row for node in layout.nodes}
        for edge in layout.edges:
            assert rows[edge.child_sha] < rows[edge.parent_sha]

    def test_rows_are_unique(self, service, pinned_commit_clock):
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

    def test_the_root_commit_is_the_last_row(self, service, pinned_commit_clock):
        first = service.record_save("burn", DECK_V1)
        service.record_save("burn", DECK_V2)
        service.checkout("burn", first)
        service.record_save("burn", DECK_V3)

        graph = service.build_graph("burn")
        # The premise: both branch tips carry their own second, so the walk that
        # feeds the layout is ordered by the history rather than by whichever
        # decklist happened to hash lower.
        stamps = [g.commit.timestamp for g in graph]
        assert stamps == sorted(stamps, reverse=True)
        assert len(set(stamps)) == len(stamps)

        layout = build_layout(graph)
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


def _decklist(*lines: str) -> str:
    """A decklist built without escape sequences, one card per line."""
    return "".join(line + chr(10) for line in lines)


class TestConsecutiveSavesStayInOneHistory:
    """Saving one deck twice must extend its history, not start a second one.

    The user hit this as "I edited two cards, saved again, and got no new
    node": the two saves wrote two *different* files, so their commits were
    keyed to two different repos and neither branch ever grew a second node.

    What is asserted here is the outcome -- one repo, one branch, a second
    commit carrying the edit -- rather than how the save flow picks its file
    name. That mechanism is being replaced by an explicit, user-set deck name,
    and this property has to hold across that change.
    """

    @staticmethod
    def _scraped() -> dict:
        return {
            "href": "modern-affinity",
            "name": "modern-affinity",
            "source": "mtggoldfish",
            "player": "pedronavaja",
            "result": "17th",
            "date": "2026-09-21",
            "event": "Modern Challenge 32",
        }

    def test_the_second_save_adds_a_node_to_the_same_branch(self, tmp_path) -> None:
        service = DeckVcsService(vcs_repo=DeckVcsRepository(tmp_path / "deck_vcs"))
        deck_key = "pedronavaja, 17th, 2026-09-21_modern challenge 32"

        before = _decklist("4 Mox Opal", "4 Pinnacle Emissary", "4 Urza's Saga")
        after = _decklist("4 Mox Opal", "2 Pinnacle Emissary", "4 Urza's Saga")

        first = service.record_save(deck_key, before)
        branch_after_first = service.current_branch(deck_key)
        second = service.record_save(deck_key, after)

        assert second is not None and second != first
        # One branch, two commits, the newer one parented on the older.
        assert service.current_branch(deck_key) == branch_after_first
        graph = service.build_graph(deck_key)
        assert len(graph) == 2
        tip = next(c for c in graph if c.sha == second)
        assert tip.commit.parents == (first,)

    def test_that_second_node_diffs_as_the_edit(self, tmp_path) -> None:
        service = DeckVcsService(vcs_repo=DeckVcsRepository(tmp_path / "deck_vcs"))
        deck_key = "one deck"

        first = service.record_save(deck_key, _decklist("4 Mox Opal", "4 Pinnacle Emissary"))
        second = service.record_save(deck_key, _decklist("4 Mox Opal", "2 Pinnacle Emissary"))

        diff = service.diff(deck_key, first, second)
        changes = {(c.name, c.before, c.after) for c in diff.changed}
        assert ("Pinnacle Emissary", 4, 2) in changes

    def test_only_one_repo_exists_for_the_deck(self, tmp_path) -> None:
        root = tmp_path / "deck_vcs"
        service = DeckVcsService(vcs_repo=DeckVcsRepository(root))
        deck_key = "one deck"

        service.record_save(deck_key, _decklist("4 Mox Opal", "4 Pinnacle Emissary"))
        service.record_save(deck_key, _decklist("4 Mox Opal", "2 Pinnacle Emissary"))

        assert [p.name for p in sorted(root.iterdir()) if p.is_dir()] == [deck_key]

    def test_a_deck_with_no_id_yet_is_keyed_by_the_file_it_is_saved_to(self, tmp_path) -> None:
        """Before its first save a deck has no id, and the file is what tells two apart.

        Once it has one the file stops mattering: the same deck saved somewhere
        else is the same deck, which is what
        ``TestHistoryFollowsTheDeckAndNotItsName`` covers.
        """
        deck = self._scraped()
        saved = tmp_path / "pedronavaja, 17th, 2026-09-21_Modern Challenge 32.txt"
        deck["path"] = str(saved)
        deck["source"] = "file"

        chosen = tmp_path / "My Own Brew.txt"
        assert deck_key_for(deck, chosen) != deck_key_for(deck, saved)

    def test_both_saves_write_the_same_file_and_key(self, tmp_path) -> None:
        """The regression this redesign exists for.

        The deck is named once; the second save must resolve to the same file
        and the same history key even though the first save re-pointed the
        record at the file it wrote (``source='file'``, ``path`` set), which is
        what used to switch the Save As default to the record's archetype slug.
        """
        from services.deck_name import deck_file_for, set_deck_name

        deck = self._scraped()
        set_deck_name(deck, "pedronavaja, 17th, 2026-09-21_Modern Challenge 32")

        first_file = deck_file_for(deck, tmp_path)
        first_key = deck_key_for(deck, first_file)

        # What AppController._sync_saved_deck_record does after a save.
        deck["path"] = str(first_file)
        deck["source"] = "file"

        second_file = deck_file_for(deck, tmp_path)
        assert second_file == first_file
        assert deck_key_for(deck, second_file) == first_key


class TestDeckName:
    """The name is the deck's own state, and the only thing that picks its file."""

    @staticmethod
    def _scraped() -> dict:
        return {
            "href": "modern-affinity",
            "name": "modern-affinity",
            "source": "mtggoldfish",
            "player": "pedronavaja",
            "result": "17th",
            "date": "2026-09-21",
            "event": "Modern Challenge 32",
        }

    def test_a_fresh_deck_has_no_name(self) -> None:
        from services.deck_name import deck_name_of, has_deck_name

        deck = self._scraped()
        assert deck_name_of(deck) == ""
        assert not has_deck_name(deck)

    def test_the_placeholder_is_never_stored_or_keyed(self) -> None:
        """ "No name selected" is display text; storing it would key every
        unnamed deck to one shared history."""
        from services.deck_name import DECK_NAME_KEY, deck_name_of, set_deck_name

        deck = self._scraped()
        for rejected in ("", "   ", None):
            assert set_deck_name(deck, rejected) == ""
        assert DECK_NAME_KEY not in deck
        assert deck_name_of(deck) == ""
        # With no name it falls back to the record, never to placeholder text.
        assert deck_key_for(deck, None) == "modern-affinity"

    def test_an_unnamed_deck_has_no_file_to_save_to(self, tmp_path) -> None:
        from services.deck_name import deck_file_for

        assert deck_file_for(self._scraped(), tmp_path) is None

    def test_a_name_is_sanitized_into_a_legal_stem(self) -> None:
        from services.deck_name import set_deck_name

        deck = self._scraped()
        stored = set_deck_name(deck, 'Mono/Red: "Burn"?')
        assert stored == deck["deck_name"]
        assert not set(stored) & set('\\/:*?"<>|')

    def test_the_name_decides_the_key_over_the_record(self) -> None:
        from services.deck_name import set_deck_name

        deck = self._scraped()
        set_deck_name(deck, "My Own Brew")
        assert deck_key_for(deck, None) == "my own brew"

    def test_renaming_points_the_next_save_at_a_new_file(self, tmp_path) -> None:
        from services.deck_name import deck_file_for, set_deck_name

        deck = self._scraped()
        set_deck_name(deck, "First Name")
        first = deck_file_for(deck, tmp_path)
        deck["path"] = str(first)

        set_deck_name(deck, "Second Name")
        second = deck_file_for(deck, tmp_path)

        # The new name wins over the file the deck is still pointing at, which
        # is what makes the next save write a new file. The history is not
        # affected either way -- it is keyed by the deck's id, not its name.
        assert second != first
        # ...and nothing moved or deleted the old one.
        assert deck["path"] == str(first)

    def test_a_deck_keeps_saving_where_it_was_opened_from(self, tmp_path) -> None:
        """A list opened outside the deck folder goes on saving there."""
        from services.deck_name import adopt_file_name, deck_file_for

        elsewhere = tmp_path / "somewhere else" / "Mono Red.txt"
        elsewhere.parent.mkdir()
        deck = {"href": "x", "name": "Mono Red", "path": str(elsewhere), "source": "file"}
        adopt_file_name(deck, elsewhere)

        assert deck_file_for(deck, tmp_path / "deck folder") == elsewhere

    def test_a_file_deck_keeps_the_key_it_had_before_names_existed(self, tmp_path) -> None:
        """A deck with no id yet still reads the history its file already has."""
        from services.deck_name import adopt_file_name

        path = tmp_path / "Izzet Murktide.txt"
        legacy_key = deck_key_for({"href": "whatever"}, path)

        deck = {"href": "whatever", "name": path.stem, "path": str(path), "source": "file"}
        adopt_file_name(deck, path)

        assert deck_key_for(deck, path) == legacy_key
        assert deck_key_for(deck, None) == legacy_key

    def test_adopting_never_overwrites_a_chosen_name(self, tmp_path) -> None:
        from services.deck_name import adopt_file_name, set_deck_name

        deck = self._scraped()
        set_deck_name(deck, "Chosen")
        adopt_file_name(deck, tmp_path / "Something Else.txt")
        assert deck["deck_name"] == "Chosen"


class TestDiffShowsNetCardChanges:
    """The diff pane reads as a player's change, not as a file's line changes."""

    @staticmethod
    def _render(before: str, after: str) -> list[str]:
        from widgets.panels.deck_history_panel.layout import diff_lines

        return diff_lines(
            diff_decklists(before, after),
            before_label="aaaaaaa",
            after_label="bbbbbbb",
            main_heading="Maindeck",
            sideboard_heading="Sideboard",
            identical="No card differences.",
        )

    def test_a_trimmed_playset_is_one_net_line(self) -> None:
        """The user's acceptance criterion: 4 -> 2 reads as -2, not -4 then +2."""
        shown = self._render(
            _decklist("4 Mox Opal", "4 Pinnacle Emissary"),
            _decklist("4 Mox Opal", "2 Pinnacle Emissary"),
        )
        assert "-2 Pinnacle Emissary" in shown
        assert "-4 Pinnacle Emissary" not in shown
        assert "+2 Pinnacle Emissary" not in shown

    def test_a_card_that_appears_reads_as_plus(self) -> None:
        shown = self._render(_decklist("4 Mox Opal"), _decklist("4 Mox Opal", "3 Emry"))
        assert "+3 Emry" in shown

    def test_a_card_that_disappears_reads_as_minus(self) -> None:
        shown = self._render(_decklist("4 Mox Opal", "3 Emry"), _decklist("4 Mox Opal"))
        assert "-3 Emry" in shown

    def test_a_move_to_the_sideboard_cancels_nothing(self) -> None:
        """The one way collapsing by card name alone loses a real change."""
        before = "4 Mox Opal\n2 Tormod's Crypt\n\nSideboard\n1 Pithing Needle\n"
        after = "4 Mox Opal\n\nSideboard\n1 Pithing Needle\n2 Tormod's Crypt\n"

        shown = self._render(before, after)
        assert "-2 Tormod's Crypt" in shown
        assert "+2 Tormod's Crypt" in shown
        # ...and each on its own side of the zone headings.
        main_at = shown.index("Maindeck")
        side_at = shown.index("Sideboard")
        assert main_at < shown.index("-2 Tormod's Crypt") < side_at
        assert side_at < shown.index("+2 Tormod's Crypt")

    def test_an_identical_pair_says_so(self) -> None:
        same = _decklist("4 Mox Opal", "4 Urza's Saga")
        shown = self._render(same, same)
        assert shown[-1] == "No card differences."
        assert not any(line.startswith(("+", "-")) for line in shown[1:])

    def test_counts_render_as_integers(self) -> None:
        shown = self._render(
            _decklist("4 Mox Opal", "4 Pinnacle Emissary"),
            _decklist("4 Mox Opal", "2 Pinnacle Emissary"),
        )
        assert not any(".0" in line for line in shown)

    def test_the_header_names_both_versions(self) -> None:
        shown = self._render(_decklist("4 Mox Opal"), _decklist("3 Mox Opal"))
        assert shown[0] == "aaaaaaa -> bbbbbbb"


# --------------------------------------------------------------------------- read sessions
class TestReadSessionsHoldOneHandle:
    """Reading a history must not re-open the repo once per commit.

    Building the graph for a hundred-version deck opened the repo two hundred
    times and read every blob twice, and spent 98% of its time doing that rather
    than comparing anything. These pin the shape of the fix, not its speed: the
    counts are what regress silently, and a timing assertion would be flaky.
    """

    @staticmethod
    def _count_opens(monkeypatch) -> list[int]:
        """Count ``Repo`` constructions for the duration of a test."""
        from dulwich.repo import Repo

        calls = [0]
        original = Repo.__init__

        def counting_init(self, *args, **kwargs):
            calls[0] += 1
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Repo, "__init__", counting_init)
        return calls

    @staticmethod
    def _history(service, deck_key: str, saves: int) -> None:
        for i in range(saves):
            service.record_save(deck_key, _decklist(f"{1 + i % 4} Mox Opal", "4 Urza's Saga"))

    def test_building_the_graph_opens_the_repo_once(self, service, monkeypatch):
        self._history(service, "deck", 6)
        opens = self._count_opens(monkeypatch)

        graph = service.build_graph("deck")

        assert len(graph) == 6
        assert opens[0] == 1, "one handle for the whole walk, not two per commit"

    def test_reading_the_whole_view_opens_the_repo_once(self, service, monkeypatch):
        """Graph, branches, current branch and the opening preview: one trip."""
        self._history(service, "deck", 5)
        opens = self._count_opens(monkeypatch)

        snapshot = service.read_history("deck")

        assert len(snapshot.graph) == 5
        assert snapshot.branches == ("main",)
        assert snapshot.current_branch == "main"
        assert snapshot.preview is not None
        assert opens[0] == 1

    def test_each_blob_is_read_once_per_session(self, service, monkeypatch):
        """A walk wants every commit's text and its parent's -- the same blobs.

        Counted at the object store, not at ``read_commit_text``: the caller
        still asks twice, and the point is that the second ask is answered from
        the session rather than by opening the blob again.
        """
        self._history(service, "deck", 5)

        from repositories.deck_vcs_repository import commits as commits_module

        reads = []
        original = commits_module._blob_text

        def recording(repo, sha):
            reads.append(sha)
            return original(repo, sha)

        monkeypatch.setattr(commits_module, "_blob_text", recording)
        graph = service.build_graph("deck")

        assert len(reads) == len(graph), "one blob read per commit, no more"
        assert len(reads) == len(set(reads))

    def test_identifying_a_file_opens_the_repo_once(self, service, monkeypatch):
        """The fingerprint scan reads a blob per commit; it may not re-open."""
        self._history(service, "deck", 6)
        opens = self._count_opens(monkeypatch)

        verdict = service.identify("deck", _decklist("3 Black Lotus"))

        assert verdict.status is ExternalEditStatus.UNATTRIBUTED
        assert opens[0] == 1

    def test_recording_a_save_never_walks_the_history(self, service, vcs, monkeypatch):
        """A save wants the tip, which is a ref -- not every commit object.

        It asked three times over: once for the unchanged check, once more for
        the auto summary, and each of those decoded the whole history to find
        the commit that ``HEAD`` already named.
        """
        self._history(service, "deck", 3)
        walks = []
        original = vcs.list_commits

        def recording(deck_key):
            walks.append(deck_key)
            return original(deck_key)

        monkeypatch.setattr(vcs, "list_commits", recording)
        sha = service.record_save("deck", _decklist("4 Mox Opal", "2 Urza's Saga"))

        assert sha is not None
        assert walks == [], "the history was walked to find a commit HEAD already names"

    def test_an_unchanged_save_records_nothing(self, service):
        """The short-circuit still has to hold now that it reads a ref."""
        deck = _decklist("4 Mox Opal", "4 Urza's Saga")
        service.record_save("deck", deck)

        assert service.record_save("deck", deck) is None
        assert len(service.build_graph("deck")) == 1

    def test_a_reorder_is_still_not_a_save(self, service):
        service.record_save("deck", _decklist("4 Mox Opal", "4 Urza's Saga"))

        assert service.record_save("deck", _decklist("4 Urza's Saga", "4 Mox Opal")) is None


class TestReadSessionsAreSafeToCache:
    """A session's blob cache may never outlive the operation that opened it."""

    def test_a_commit_made_after_a_session_is_visible(self, service):
        service.record_save("deck", DECK_V1)
        first = service.build_graph("deck")

        service.record_save("deck", DECK_V2)
        second = service.build_graph("deck")

        assert len(first) == 1
        assert len(second) == 2
        assert second[0].commit.message == diff_decklists(DECK_V1, DECK_V2).summary()

    def test_the_text_a_later_session_reads_is_the_current_one(self, service, vcs):
        service.record_save("deck", DECK_V1)
        head = vcs.list_commits("deck")[0].sha

        with vcs.read_session("deck"):
            first = vcs.read_commit_text("deck", head)
        assert normalize_decklist(first) == normalize_decklist(DECK_V1)

        service.record_save("deck", DECK_V2)
        with vcs.read_session("deck"):
            new_head = vcs.list_commits("deck")[0].sha
            latest = vcs.read_commit_text("deck", new_head)
        assert normalize_decklist(latest) == normalize_decklist(DECK_V2)

    def test_a_deck_with_no_history_is_not_an_error(self, vcs):
        """``read_session`` on a repo that does not exist yet simply does nothing."""
        with vcs.read_session("never-saved"):
            assert vcs.list_commits("never-saved") == []

    def test_sessions_do_not_leak_between_threads(self, service, vcs):
        """The repository is a singleton; two threads must not share a handle."""
        import threading

        service.record_save("deck", DECK_V1)
        seen: list[object] = []

        def other_thread() -> None:
            seen.append(vcs._active_session("deck"))

        with vcs.read_session("deck"):
            assert vcs._active_session("deck") is not None
            thread = threading.Thread(target=other_thread)
            thread.start()
            thread.join()

        assert seen == [None]

    def test_a_session_may_be_opened_inside_another(self, service, vcs):
        """Nesting is re-entrant: the inner block must not close the handle."""
        service.record_save("deck", DECK_V1)
        with vcs.read_session("deck"):
            outer = vcs._active_session("deck")
            with vcs.read_session("deck"):
                assert vcs._active_session("deck") is outer
            assert vcs._active_session("deck") is outer
        assert vcs._active_session("deck") is None


class TestReadHistoryPicksAVersionToShow:
    """What the view opens on, decided where the history is read."""

    def test_it_opens_on_head_when_nothing_is_selected(self, service):
        service.record_save("deck", DECK_V1)
        service.record_save("deck", DECK_V2)

        snapshot = service.read_history("deck")

        head = next(g for g in snapshot.graph if g.commit.is_head)
        assert snapshot.selected_sha == head.sha

    def test_a_selection_from_another_deck_falls_back_to_head(self, service, pinned_commit_clock):
        """The selection survives a deck change otherwise, pointing nowhere.

        ``HEAD`` is deliberately not the newest version: the deck is parked on
        its first save while two later ones are still the tip of the branch it
        came from. On a one-commit history the two coincide and the fallback is
        indistinguishable from ``return graph[0]`` -- which would open the tab
        on a version the user is not on.
        """
        first = service.record_save("deck", DECK_V1)
        service.record_save("deck", DECK_V2)
        service.record_save("deck", DECK_V3)
        service.checkout("deck", first)

        snapshot = service.read_history("deck", selected_sha="0" * 40)

        assert snapshot.selected_sha == first
        assert snapshot.graph[0].sha != first
        assert snapshot.graph[0].commit.is_head is False

    def test_the_preview_diffs_against_the_parent_by_default(self, service):
        service.record_save("deck", DECK_V1)
        service.record_save("deck", DECK_V2)

        snapshot = service.read_history("deck")

        assert snapshot.preview is not None
        assert snapshot.preview.base_sha == snapshot.graph[0].commit.parents[0]
        assert snapshot.preview.diff is not None
        assert "Consider" in snapshot.preview.diff.summary()

    def test_a_pinned_baseline_wins_over_the_parent(self, service):
        service.record_save("deck", DECK_V1)
        service.record_save("deck", DECK_V2)
        service.record_save("deck", DECK_V3)
        graph = service.build_graph("deck")
        root = graph[-1].sha

        snapshot = service.read_history("deck", baseline_sha=root)

        assert snapshot.preview is not None
        assert snapshot.preview.base_sha == root

    def test_a_root_commit_previews_with_no_diff(self, service):
        service.record_save("deck", DECK_V1)

        snapshot = service.read_history("deck")

        assert snapshot.preview is not None
        assert snapshot.preview.base_sha is None
        assert snapshot.preview.diff is None

    def test_a_deck_with_no_history_reads_as_empty(self, service):
        snapshot = service.read_history("never-saved")

        assert snapshot.graph == ()
        assert snapshot.branches == ()
        assert snapshot.preview is None

    def test_an_unreadable_repo_reads_as_empty_rather_than_raising(self, service, vcs):
        """A broken history must not take the tab down with it, or keep its handle.

        The repo is corrupted for real: its objects are repacked so the store is
        a packfile -- the case ``store.py`` warns about, because Windows will not
        delete a file another handle still holds -- and the packfile is then
        overwritten with junk. The ``.git`` directory and the refs survive, so
        the repo still *opens*: the read fails partway through a live
        ``read_session``, which is the only place the handle can leak from.
        """
        from dulwich import porcelain

        service.record_save("deck", DECK_V1)
        service.record_save("deck", DECK_V2)
        repo_path = vcs.repo_path("deck")

        porcelain.repack(str(repo_path))
        objects = repo_path / ".git" / "objects"
        for loose in (d for d in objects.iterdir() if d.is_dir() and d.name != "pack"):
            shutil.rmtree(loose)
        for pack in (objects / "pack").glob("*.pack"):
            pack.write_bytes(b"PACK this is not a packfile")

        # The corruption is deep enough to break a read and shallow enough that
        # the session still opens -- otherwise this would prove nothing.
        with vcs.read_session("deck"):
            assert vcs._active_session("deck") is not None

        snapshot = service.read_history("deck")
        assert snapshot.branches == ()
        assert snapshot.preview is None
        assert vcs._active_session("deck") is None

        # The packfile index is the handle that leaks, and Windows will not let
        # go of it: if the failed read kept one, this raises PermissionError.
        for index in (objects / "pack").glob("*.idx"):
            index.unlink()

        assert service.read_history("deck").graph == ()


class TestHistoryFollowsTheDeckAndNotItsName:
    """A6: the history is keyed on the deck's stable id, not on what it is called.

    Both tests drive the real save path (``DeckWorkflowService.save_deck``) and
    then read the history back the way the History tab does, because the bug was
    never in either half on its own -- it was that the save and the later read
    computed the same key from something the user is free to change.

    The global deck-VCS service is pointed at ``tmp_path`` rather than reset,
    since the save path reaches it through :func:`get_deck_vcs_service` and the
    point of the test is to read back exactly what that save wrote.
    """

    @staticmethod
    def _workflow(tmp_path):
        from repositories.deck_repository.repository import DeckRepository
        from services.deck_service.averager import DeckAverager
        from services.deck_workflow_service import DeckWorkflowService

        return DeckWorkflowService(
            deck_repo=DeckRepository(db_path=tmp_path / "decks.sqlite"),
            deck_service=DeckAverager(),
            metagame_repo=object(),
        )

    @staticmethod
    def _history_on(tmp_path, monkeypatch) -> DeckVcsService:
        from services import deck_vcs_service as module

        service = DeckVcsService(vcs_repo=DeckVcsRepository(tmp_path / "deck_history"))
        monkeypatch.setattr(module, "_default_service", service)
        return service

    def test_renaming_a_deck_keeps_the_versions_it_already_has(self, tmp_path, monkeypatch):
        """The user's report: rename the deck, and the version graph is empty."""
        from services.deck_name import deck_file_for, set_deck_name

        history = self._history_on(tmp_path, monkeypatch)
        deck = {"href": "modern-burn", "name": "modern-burn", "source": "mtggoldfish"}
        set_deck_name(deck, "Kiki Chord")

        saved_path, _deck_id = self._workflow(tmp_path).save_deck(
            deck_name="Kiki Chord",
            deck_content=DECK_V1,
            format_name="Modern",
            deck=deck,
            deck_save_dir=tmp_path,
        )
        deck["path"] = str(saved_path)
        deck["source"] = "file"
        before = [node.sha for node in history.build_graph(deck_key_for(deck, saved_path))]
        assert len(before) == 1

        set_deck_name(deck, "Kiki Chord But Better")
        renamed = deck_file_for(deck, tmp_path)

        after = [node.sha for node in history.build_graph(deck_key_for(deck, renamed))]
        assert after == before

    def test_two_decks_called_the_same_thing_keep_two_histories(self, tmp_path, monkeypatch):
        """Two ``Mono Red.txt`` in two folders are two decks, not one deck twice."""
        from services.deck_name import set_deck_name

        history = self._history_on(tmp_path, monkeypatch)
        workflow = self._workflow(tmp_path)
        folders = [tmp_path / "league", tmp_path / "challenge"]
        for folder in folders:
            folder.mkdir()

        keys = []
        for folder, content in zip(folders, (DECK_V1, DECK_V3)):
            deck = {"href": "modern-burn", "name": "modern-burn", "source": "mtggoldfish"}
            set_deck_name(deck, "Mono Red")
            saved_path, _deck_id = workflow.save_deck(
                deck_name="Mono Red",
                deck_content=content,
                format_name="Modern",
                deck=deck,
                deck_save_dir=folder,
            )
            keys.append(deck_key_for(deck, saved_path))

        assert keys[0] != keys[1]
        # One save each: neither deck's list was appended to the other's branch.
        for key, content in zip(keys, (DECK_V1, DECK_V3)):
            graph = history.build_graph(key)
            assert len(graph) == 1
            assert history.version_text(key, graph[0].sha) == normalize_decklist(content)


class TestAHistoryWrittenBeforeDecksHadIdsIsAdopted:
    """The old name-keyed repos are moved onto the deck's id by its next save.

    Deck history has never shipped, so this is not a migration owed to anyone --
    it is for a checkout that already holds repos under the old root, and it is
    asserted here because the alternative (a save silently starting an empty
    history next to a full one) would look exactly like the bug this replaced.
    """

    def test_the_next_save_moves_the_old_repo_onto_the_deck_id(self, tmp_path):
        from services.deck_identity import ensure_deck_id
        from services.deck_vcs_service import adoptable_legacy_key

        legacy_root = tmp_path / "cache" / "deck_vcs"
        repo = DeckVcsRepository(tmp_path / "deck_history", legacy_root=legacy_root)
        legacy = DeckVcsService(vcs_repo=DeckVcsRepository(legacy_root))
        old_sha = legacy.record_save("mono red", DECK_V1)

        deck = {"deck_name": "Mono Red"}
        deck_key = ensure_deck_id(deck)
        adopted = repo.adopt_legacy_repo(deck_key, adoptable_legacy_key(deck, None))

        assert adopted is True
        assert [c.sha for c in DeckVcsService(vcs_repo=repo).build_graph(deck_key)] == [old_sha]
        assert not (legacy_root / "mono red").exists()

    def test_a_deck_that_already_has_a_history_is_never_overwritten(self, tmp_path):
        legacy_root = tmp_path / "cache" / "deck_vcs"
        repo = DeckVcsRepository(tmp_path / "deck_history", legacy_root=legacy_root)
        DeckVcsService(vcs_repo=DeckVcsRepository(legacy_root)).record_save("mono red", DECK_V1)
        service = DeckVcsService(vcs_repo=repo)
        mine = service.record_save("a-deck-id", DECK_V2)

        assert repo.adopt_legacy_repo("a-deck-id", "mono red") is False
        assert [c.sha for c in service.build_graph("a-deck-id")] == [mine]

    def test_a_shared_fallback_key_is_never_adopted(self, tmp_path):
        """``href`` is an archetype slug and ``manual`` is everyone; neither is a deck."""
        from services.deck_vcs_service import adoptable_legacy_key

        scraped = {"href": "modern-affinity", "name": "modern-affinity"}

        assert adoptable_legacy_key(scraped, None) == ""
        assert adoptable_legacy_key(None, None) == ""
        # ...while the deck's own name and its own file still are.
        assert adoptable_legacy_key({"deck_name": "Mono Red"}, None) == "mono red"
        assert adoptable_legacy_key(None, tmp_path / "Mono Red.txt") == "mono red"
