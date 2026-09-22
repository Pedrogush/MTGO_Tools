"""Deciding which decks in a labelled pool actually belong to the archetype.

The archetype labels the data sources attach are contaminated. The Modern
"Affinity" pool is about 62% Affinity; the rest is Hammer Time, Grinding Station
combo and Dimir Mox Amber tempo wearing the same label. Because a baseline is a
**strict intersection** (see :mod:`~services.archetype_baseline_service.classify`),
a single non-member is not a small error -- it is fatal. One Dimir tempo list
dropped the real 60-deck Affinity baseline from twelve cards to zero, because
there is no card a Dimir tempo deck and an Affinity deck both run.

The rule this implements is therefore: *if a deck has nothing in common with any
other deck in the pool, it is not part of the group, whatever the label says.*

**The measure.** Each deck's maindeck is reduced to its set of card *names*, and
two decks are compared by Jaccard index -- cards in both, over cards in either.
A deck's membership score is the mean of that index against every other deck in
the pool. Three properties matter:

* It is **symmetric**, and a mean over all pairs does not depend on the order
  the pool arrives in, so the same pool always yields the same split.
* It **never reads a card**. Nothing here knows what any card does; only whether
  two lists contain the same string. There is no card list to maintain and no
  format knowledge to go stale.
* **Counts are ignored.** ``4 Mox Opal`` and ``1 Mox Opal`` both mean "runs Mox
  Opal", so two lists differing only in ratios score 1.0. Ratios are what the
  baseline itself measures; they are not what tells two archetypes apart.

Sideboards are excluded because they swing hardest with the local metagame, and
two pilots of one archetype can share a maindeck and disagree on fifteen cards.

The one real bias is that the union sits in the denominator, so breadth is
penalised: a toolbox list carrying twenty-five distinct names scores lower
against a lean twenty-name list even when it contains all twenty. Affinity's
Urza's Saga singletons depress its own scores for exactly this reason. It costs
nothing here because the gap between members and non-members is so wide, but it
is why the threshold is not tighter.

The measure finds the *minority*, which is not the same as finding the *wrong
label*. In a pool that was half Hammer Time, Hammer would stop looking atypical.
This is a guard against contamination, not a substitute for the tagging being
right.
"""

from __future__ import annotations

from services.archetype_baseline_service.frequency import deck_card_counts
from services.archetype_baseline_service.models import ExcludedDeck, PoolMembership

#: Mean pairwise Jaccard below which a deck is not a member of its own pool.
#:
#: Chosen empirically, and it is not a knife edge. On the real 60-list Modern
#: Affinity pool the kept decks score 0.462-0.638 and the rejected ones
#: 0.093-0.266: **nothing lands between 0.266 and 0.462**, so every threshold in
#: roughly [0.27, 0.46] produces the identical split. 0.30 sits inside that
#: empty gap with room on both sides. The separation is that clean because the
#: thing being detected is a different deck, not a variant build -- an Affinity
#: list and a Hammer list share only the artifact-mana shell (Mox Opal, Urza's
#: Saga, Metallic Rebuke) out of ~37 distinct names between them.
#:
#: This is a filter on *decks*. It is deliberately not a play-rate cut-off on
#: *cards* -- the baseline keeps its strict intersection, and no card enters it
#: on a majority vote.
MEMBERSHIP_THRESHOLD = 0.30

#: Below two decks there are no pairs, so there is no similarity to measure.
#: A lone deck cannot be atypical of a pool it is the whole of, so filtering is
#: skipped rather than applied to a score that would have to be invented.
MIN_POOL_FOR_FILTERING = 2


def maindeck_names(deck_text: str) -> frozenset[str]:
    """The set of maindeck card names in ``deck_text``.

    Counts are dropped, the sideboard is dropped, and a line with a count of
    zero is not a card the deck runs. Parsing goes through the same counter the
    frequency table uses, so a decklist is read identically on both paths.
    """
    counts = deck_card_counts(deck_text)
    return frozenset(
        name for (name, is_sideboard), count in counts.items() if not is_sideboard and count > 0
    )


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    """Cards in both, over cards in either. ``0.0`` when both are empty."""
    union = len(left | right)
    if not union:
        return 0.0
    return len(left & right) / union


def similarity_scores(name_sets: list[frozenset[str]]) -> list[float]:
    """Each deck's mean Jaccard against every *other* deck in the pool.

    The pairwise matrix is symmetric, so only the upper triangle is computed and
    each result is credited to both decks.
    """
    size = len(name_sets)
    if size < MIN_POOL_FOR_FILTERING:
        # No pairs exist. Treating the deck as perfectly typical is the only
        # answer that does not invent evidence either way.
        return [1.0] * size

    totals = [0.0] * size
    for i in range(size):
        for j in range(i + 1, size):
            score = jaccard(name_sets[i], name_sets[j])
            totals[i] += score
            totals[j] += score

    divisor = size - 1
    return [total / divisor for total in totals]


def partition_pool(
    deck_texts: list[str],
    *,
    sources: tuple[str, ...] = (),
    threshold: float = MEMBERSHIP_THRESHOLD,
) -> PoolMembership:
    """Split ``deck_texts`` into the archetype's members and the impostors.

    Single pass: every deck is scored against the *whole* pool, then everything
    below ``threshold`` is dropped at once. Iterating to a fixed point was tried
    against the real Affinity pool and changes nothing -- removing the outliers
    only raises the survivors' scores, so a second pass has nothing left to
    reject -- and a single pass is the version whose result obviously cannot
    depend on the order decks were removed in.
    """
    name_sets = [maindeck_names(text or "") for text in deck_texts]
    scores = similarity_scores(name_sets)

    def identify(index: int) -> str:
        if index < len(sources) and sources[index]:
            return str(sources[index])
        return f"#{index}"

    kept: list[int] = []
    excluded: list[ExcludedDeck] = []
    for index, score in enumerate(scores):
        if score < threshold:
            excluded.append(ExcludedDeck(source=identify(index), similarity=score))
        else:
            kept.append(index)

    return PoolMembership(
        kept_indices=tuple(kept),
        excluded=tuple(excluded),
        scores=tuple(scores),
        threshold=threshold,
    )


__all__ = [
    "MEMBERSHIP_THRESHOLD",
    "MIN_POOL_FOR_FILTERING",
    "jaccard",
    "maindeck_names",
    "partition_pool",
    "similarity_scores",
]
