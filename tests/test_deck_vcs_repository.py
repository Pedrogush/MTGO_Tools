"""Tests for the deck-VCS *repository* layer, driven directly.

``tests/test_deck_vcs.py`` exercises the feature the way the app does: through
``DeckVcsService``, with a deck record deciding which repo a save lands in.
These go at :class:`DeckVcsRepository` and the functions under it with literal
deck keys, because what is under test here is the layer's own contract -- how a
decklist is parsed into zones, which branch names produce a ref git will accept,
which keys share a repo, and whether any of it survives the process that wrote
it -- none of which should depend on how a deck resolves to a key.

Same rules as the sibling module (``tests/README.md`` §1): a real repository over
``tmp_path`` and a real dulwich repo, no mocks of the code under test.
"""

from __future__ import annotations

import pytest

from repositories.deck_vcs_repository import DeckVcsRepository
from repositories.deck_vcs_repository.branches import sanitize_branch_name
from repositories.deck_vcs_repository.diffs import unified_lines
from repositories.deck_vcs_repository.normalize import (
    decklist_fingerprint,
    normalize_decklist,
    parse_entries,
)

# Copied rather than imported from ``tests/test_deck_vcs.py``: a test module that
# reaches into another one couples the two together, and these are three lines.
DECK_V1 = "4 Lightning Bolt\n2 Consider\n\nSideboard\n2 Abrade\n"
DECK_V2 = "4 Lightning Bolt\n4 Consider\n\nSideboard\n2 Abrade\n"
DECK_V3 = "4 Lightning Bolt\n4 Consider\n2 Fable of the Mirror-Breaker\n\nSideboard\n2 Abrade\n"


@pytest.fixture
def vcs(tmp_path):
    return DeckVcsRepository(tmp_path / "deck_vcs")


class TestNormalizationReadsWhatTheUserActuallyWrote:
    """The parse itself, on the text shapes an externally edited .txt arrives in.

    ``TestNormalization`` covers the canonical *output*. These cover the input
    side -- zone detection, the zero-count filter and card names that are not
    ASCII -- because every one of them decides which zone a card lands in or
    whether two spellings are one card, and both of those change the fingerprint
    that makes an edited file recognisable.
    """

    def test_a_blank_first_line_does_not_open_the_sideboard(self):
        """A file that merely starts with an empty line is not an all-sideboard deck.

        The zone marker is a blank line *between* the zones. Treating a leading
        one as a separator read the whole maindeck as a sideboard, which changes
        the fingerprint and so makes an already-committed file unrecognisable.
        """
        assert normalize_decklist("\n4 Lightning Bolt\n") == "4 Lightning Bolt\n"

    def test_leading_blank_lines_do_not_move_the_maindeck(self):
        assert normalize_decklist("\n\n  \n" + DECK_V1) == normalize_decklist(DECK_V1)

    def test_a_header_before_the_cards_is_not_a_separator_either(self):
        """A comment line and the blank after it are a preamble, not the sideboard."""
        assert normalize_decklist("// Modern Burn\n\n4 Lightning Bolt\n") == "4 Lightning Bolt\n"

    def test_a_blank_line_between_the_zones_still_separates_them(self):
        """The rule the leading-blank fix must not break."""
        text = normalize_decklist("4 Lightning Bolt\n\n2 Abrade\n")
        assert text == "4 Lightning Bolt\n\nSideboard\n2 Abrade\n"

    def test_a_leading_blank_line_leaves_the_fingerprint_alone(self):
        """This is the consequence: a committed file otherwise stops being recognised."""
        assert decklist_fingerprint("\n" + DECK_V1) == decklist_fingerprint(DECK_V1)

    def test_parse_entries_tags_each_card_with_its_zone(self):
        """The public parse the archetype baseline reads every pool deck through."""
        entries = parse_entries("2 Consider\n4 Lightning Bolt\n\nSideboard\n2 Abrade\n")
        assert [(e.name, e.count, e.is_sideboard) for e in entries] == [
            ("Consider", 2.0, False),
            ("Lightning Bolt", 4.0, False),
            ("Abrade", 2.0, True),
        ]

    def test_a_zero_count_card_is_not_a_card(self):
        """A count of zero is a slot the user emptied, not a line to keep."""
        assert normalize_decklist("0 Consider\n4 Lightning Bolt\n") == "4 Lightning Bolt\n"
        assert parse_entries("0 Consider\n") == []

    def test_diacritics_survive_a_commit_untouched(self, vcs):
        """Accented card names are common enough that folding one is a silent data loss."""
        deck = "4 Jötun Grunt\n1 Lim-Dûl the Necromancer\n"
        sha = vcs.commit_deck("odd-names", deck, "v1")
        assert (
            vcs.read_commit_text("odd-names", sha) == "4 Jötun Grunt\n1 Lim-Dûl the Necromancer\n"
        )

    def test_two_spellings_of_one_name_are_two_cards(self):
        """Nothing here folds accents, so the fingerprint must not pretend it does."""
        assert decklist_fingerprint("4 Jötun Grunt\n") != decklist_fingerprint("4 Jotun Grunt\n")
        assert len(parse_entries("4 Jötun Grunt\n4 Jotun Grunt\n")) == 2

    def test_two_case_spellings_sort_together_and_deterministically(self):
        """Case folds for the sort, then the exact name breaks the tie."""
        entries = parse_entries("2 brazen borrower\n2 Brazen Borrower\n2 Abrade\n")
        assert [e.name for e in entries] == ["Abrade", "Brazen Borrower", "brazen borrower"]

    def test_the_same_card_under_two_printings_stays_two_lines(self):
        """The printing id is part of the name here, unlike in the collection diff."""
        one = "11111111-1111-1111-1111-111111111111"
        two = "22222222-2222-2222-2222-222222222222"
        text = normalize_decklist(f"2 Lightning Bolt {two}\n2 Lightning Bolt {one}\n")
        assert text == f"2 Lightning Bolt {one}\n2 Lightning Bolt {two}\n"


class TestBranchNamesGitWillActuallyAccept:
    """The point of ``sanitize_branch_name`` is that the ref can then be created.

    The name comes from a text field the user types into
    (``deck_history_panel/handlers.py::create_branch_at``), so every rule in
    ``git-check-ref-format`` is reachable from the keyboard. Two of those rules
    are about sequences rather than characters and so survive a per-character
    scan; each case here creates the branch for real, because "the string looks
    reduced" is not the property the function exists for.
    """

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("wip@{0}", "wip-0}"),
            ("main@{yesterday}", "main-yesterday}"),
            ("@{", "branch"),
            ("wip.lock", "wip"),
            ("wip.lock.lock", "wip"),
            ("feature/wip.lock", "feature/wip"),
            ("feature/.lock", "feature"),
            (".lock", "lock"),
        ],
    )
    def test_the_rules_a_character_scan_cannot_see(self, raw, expected):
        assert sanitize_branch_name(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        ["wip@{0}", "main@{yesterday}", "wip.lock", "feature/wip.lock", "@{", "feature/.lock"],
    )
    def test_a_sanitized_name_is_a_ref_the_repo_accepts(self, vcs, raw):
        """Before the fix these reached dulwich intact and it refused the ref."""
        sha = vcs.commit_deck("burn", DECK_V1, "v1")

        created = vcs.create_branch("burn", raw, sha)

        assert created in vcs.list_branches("burn")
        assert vcs.branch_tips("burn")[created] == sha


class TestMovingOntoSomethingThatIsNotThere:
    """The two ways a move can be asked for a version the deck does not have."""

    def test_switching_to_a_branch_that_does_not_exist_says_which(self, vcs):
        vcs.commit_deck("burn", DECK_V1, "v1")

        with pytest.raises(KeyError, match="No such deck branch"):
            vcs.switch_branch("burn", "never-created")

    def test_a_refused_switch_leaves_head_where_it_was(self, vcs):
        """The mirror's working file must not be rewritten by a move that failed."""
        vcs.commit_deck("burn", DECK_V1, "v1")

        with pytest.raises(KeyError):
            vcs.switch_branch("burn", "never-created")

        assert vcs.current_branch("burn") == "main"

    def test_checking_out_a_sha_the_deck_does_not_have_raises(self, vcs):
        vcs.commit_deck("burn", DECK_V1, "v1")

        with pytest.raises(KeyError):
            vcs.checkout("burn", "0" * 40)

    def test_a_refused_checkout_leaves_no_branch_behind(self, vcs):
        """checkout branches *before* it switches, so a failure could litter."""
        vcs.commit_deck("burn", DECK_V1, "v1")

        with pytest.raises(KeyError):
            vcs.checkout("burn", "0" * 40)

        assert vcs.list_branches("burn") == ["main"]

    def test_a_shared_tip_checks_out_the_alphabetically_first_branch(self, vcs):
        """Several branches on one commit have to resolve the same way every time.

        The refs do not come back sorted, so without the tie-break this lands on
        whichever branch dulwich happens to list first -- and the version rail
        would name a different branch from one refresh to the next.
        """
        sha = vcs.commit_deck("burn", DECK_V1, "v1")
        for name in ("zulu", "mike", "aardvark"):
            vcs.create_branch("burn", name, sha)

        branch, _text = vcs.checkout("burn", sha)

        assert branch == "aardvark"
        assert vcs.current_branch("burn") == "aardvark"


class TestOneRepoPerDeckKey:
    """Which keys share a repo, since sharing one merges two decks' histories."""

    def test_keys_differing_only_in_case_are_one_history(self, vcs):
        """``repo_path`` lowercases, so "Burn" and "burn" are the same deck.

        Pinned rather than argued with: the repos sit in one flat directory on a
        case-insensitive filesystem, so two of them could not coexist there
        anyway, and a key scheme that stopped folding case would have to answer
        for that. What matters is that it is a decision and not an accident.
        """
        first = vcs.commit_deck("Burn", DECK_V1, "v1")
        second = vcs.commit_deck("burn", DECK_V2, "v2")

        # Compared as text: two ``Path``s differing only in case are equal on
        # Windows whether or not the key was folded, which would prove nothing.
        assert str(vcs.repo_path("Burn")) == str(vcs.repo_path("burn"))
        assert vcs.repo_path("BURN").name == "burn"
        assert vcs.has_repo("BURN")
        assert [c.sha for c in vcs.list_commits("Burn")] == [second, first]

    def test_two_different_keys_do_not_share_a_history(self, vcs):
        burn = vcs.commit_deck("burn", DECK_V1, "v1")
        vcs.commit_deck("tron", DECK_V3, "v1")

        assert vcs.repo_path("burn") != vcs.repo_path("tron")
        assert [c.sha for c in vcs.list_commits("burn")] == [burn]

    def test_every_repo_is_one_directory_under_the_root(self, vcs):
        """A scraped key is a URL fragment; it must not dig a tree of folders."""
        vcs.commit_deck("archetype/modern/burn", DECK_V1, "v1")

        assert [p.name for p in vcs._vcs_root.iterdir()] == ["archetype_modern_burn"]


class TestAHistoryOutlivesTheObjectThatWroteIt:
    """Nothing else reopens a store from disk, so nothing proved it was on disk.

    A repository built over the same root by a later process -- which is what
    every run after the one that saved is -- has to see the same commits, the
    same text, the same branch and the same tip.
    """

    def test_the_commits_are_still_there(self, tmp_path):
        root = tmp_path / "deck_vcs"
        first = DeckVcsRepository(root).commit_deck("burn", DECK_V1, "v1")
        second = DeckVcsRepository(root).commit_deck("burn", DECK_V2, "v2")

        reopened = DeckVcsRepository(root)

        assert [c.sha for c in reopened.list_commits("burn")] == [second, first]
        assert reopened.head_sha("burn") == second

    def test_the_decklist_reads_back_byte_for_byte(self, tmp_path):
        root = tmp_path / "deck_vcs"
        sha = DeckVcsRepository(root).commit_deck("burn", DECK_V1, "v1")

        assert DeckVcsRepository(root).read_commit_text("burn", sha) == normalize_decklist(DECK_V1)

    def test_the_branch_the_deck_was_left_on_is_where_it_reopens(self, tmp_path):
        root = tmp_path / "deck_vcs"
        writer = DeckVcsRepository(root)
        first = writer.commit_deck("burn", DECK_V1, "v1")
        writer.commit_deck("burn", DECK_V2, "v2")
        writer.checkout("burn", first)

        reopened = DeckVcsRepository(root)

        assert reopened.current_branch("burn") == f"branch-from-{first[:7]}"
        assert sorted(reopened.list_branches("burn")) == [f"branch-from-{first[:7]}", "main"]

    def test_a_deck_saved_by_one_object_extends_under_another(self, tmp_path):
        """The next run appends to the history rather than starting one."""
        root = tmp_path / "deck_vcs"
        first = DeckVcsRepository(root).commit_deck("burn", DECK_V1, "v1")

        second = DeckVcsRepository(root).commit_deck("burn", DECK_V2, "v2")

        assert DeckVcsRepository(root).list_commits("burn")[0].parents == (first,)
        assert second != first


class TestCommitFingerprints:
    """The content hash that answers "is this file a version I already have?"."""

    def test_a_commits_fingerprint_is_its_decklists(self, vcs):
        sha = vcs.commit_deck("burn", DECK_V1, "v1")
        assert vcs.commit_fingerprint("burn", sha) == decklist_fingerprint(DECK_V1)

    def test_two_versions_of_a_deck_fingerprint_apart(self, vcs):
        first = vcs.commit_deck("burn", DECK_V1, "v1")
        second = vcs.commit_deck("burn", DECK_V2, "v2")
        assert vcs.commit_fingerprint("burn", first) != vcs.commit_fingerprint("burn", second)

    def test_a_reordered_copy_fingerprints_the_same(self, vcs):
        sha = vcs.commit_deck("burn", DECK_V1, "v1")
        shuffled = "2 Consider\n4 Lightning Bolt\n\nSideboard\n2 Abrade\n"
        assert vcs.commit_fingerprint("burn", sha) == decklist_fingerprint(shuffled)

    def test_the_same_decklist_in_two_repos_fingerprints_the_same(self, tmp_path):
        """It is a hash of content, not a sha: comparable across decks and runs."""
        one = DeckVcsRepository(tmp_path / "one")
        two = DeckVcsRepository(tmp_path / "two")
        here = one.commit_deck("burn", DECK_V1, "v1")
        there = two.commit_deck(
            "aggro", "2 Consider\n4 Lightning Bolt\n\nSideboard\n2 Abrade\n", ""
        )

        assert here != there
        assert one.commit_fingerprint("burn", here) == two.commit_fingerprint("aggro", there)


class TestDiffingACommitAgainstTextInHand:
    """``diff_against_text`` and the root-commit case of ``diff_from_parent``."""

    def test_a_commit_against_a_decklist_that_was_never_committed(self, vcs):
        first = vcs.commit_deck("burn", DECK_V1, "v1")

        diff = vcs.diff_against_text("burn", first, DECK_V3)

        assert [d.name for d in diff.added] == ["Fable of the Mirror-Breaker"]
        assert [(d.name, d.before, d.after) for d in diff.changed] == [("Consider", 2.0, 4.0)]

    def test_text_that_only_reorders_the_commit_is_no_change(self, vcs):
        """The same normalization both sides, or every reorder reads as an edit."""
        first = vcs.commit_deck("burn", DECK_V1, "v1")
        shuffled = "2 Consider\n4 Lightning Bolt\n\nSideboard\n2 Abrade\n"

        assert vcs.diff_against_text("burn", first, shuffled).is_empty

    def test_a_root_commit_diffs_against_nothing(self, vcs):
        """The first version has no parent, so all of it is an addition."""
        root = vcs.commit_deck("burn", DECK_V1, "v1")

        diff = vcs.diff_from_parent("burn", root, None)

        assert [d.name for d in diff.added] == ["Consider", "Lightning Bolt", "Abrade"]
        assert diff.removed == ()
        assert diff.changed == ()

    def test_a_later_commit_diffs_against_its_parent(self, vcs):
        first = vcs.commit_deck("burn", DECK_V1, "v1")
        second = vcs.commit_deck("burn", DECK_V3, "v2")

        diff = vcs.diff_from_parent("burn", second, first)

        assert [d.name for d in diff.added] == ["Fable of the Mirror-Breaker"]


class TestUnifiedDiffLabels:
    """The labels are the only thing ``unified_lines`` adds over a plain diff."""

    def test_the_headers_name_the_two_commits(self, vcs):
        first = vcs.commit_deck("burn", DECK_V1, "v1")
        third = vcs.commit_deck("burn", DECK_V3, "v3")

        lines = vcs.unified_diff("burn", first, third)

        assert lines[0] == f"--- {first[:7]}"
        assert lines[1] == f"+++ {third[:7]}"

    def test_the_labels_are_whatever_the_caller_named_them(self):
        lines = unified_lines(DECK_V1, DECK_V3, before_label="before", after_label="after")
        assert lines[:2] == ["--- before", "+++ after"]

    def test_a_reorder_produces_no_lines_at_all(self):
        """Both sides are normalized first, so there is not even a header."""
        shuffled = "2 Consider\n4 Lightning Bolt\n\nSideboard\n2 Abrade\n"
        assert unified_lines(DECK_V1, shuffled, before_label="a", after_label="b") == []
