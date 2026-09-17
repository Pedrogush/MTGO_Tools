"""Archetype classification of the partial decks a game log reveals.

A game log only shows the cards a player actually played, cast, activated,
discarded or revealed -- typically 5 to 20 distinct names across a match, with
no quantities. The question is which known archetype those few names came from.

The model is derived at runtime from the decklists the app already caches (see
:mod:`services.archetype_model_service` for where they come from); nothing here
is hardcoded. It is built in three steps, per format:

1. **Profiles.** Every archetype label gets a card profile: the mean number of
   copies of each card across that archetype's decks, sideboard copies counted
   at :data:`SIDEBOARD_WEIGHT`, because sideboard cards do show up in games 2
   and 3 but less often than maindeck ones.
2. **Clustering.** The labels come from two naming sources (MTGGoldfish and the
   MTGO decklists), and they disagree: ``TES`` and ``The EPIC Storm``,
   ``Landfall`` and ``Mono-Green Landfall``, ``Golgari Garden`` and ``Golgari
   Gardens`` are one deck each. Labels are merged agglomeratively while any two
   groups are at least :data:`MERGE_SIMILARITY` similar -- cosine over each
   card's *presence rate* weighted by an IDF across the format's archetypes, so
   basics, fetchlands and format staples cannot make two decks look alike. The
   merged group is named after its best-represented label.
3. **Scoring.** A sample is scored against each cluster as a multinomial naive
   Bayes likelihood (additive smoothing :data:`SMOOTHING` over the format's
   vocabulary, prior = the cluster's share of the format's decks) and the
   scores are normalised to a posterior. Staples score about the same under
   every cluster and so cancel out of the posterior; a card only one archetype
   plays moves it sharply. The top cluster wins only if its posterior reaches
   :data:`MIN_CONFIDENCE`; otherwise the answer is ``"Unknown"``.

The constants were chosen on a held-out evaluation over the real cache (5-fold,
random partial samples of 3-20 distinct names); the numbers are in the pull
request that introduced this module.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from itertools import combinations
from typing import Protocol

from utils.card_names import fold_card_name

UNKNOWN_ARCHETYPE = "Unknown"

#: Sideboard copies count this much of a maindeck copy in an archetype profile.
SIDEBOARD_WEIGHT = 0.5

#: Additive smoothing for the naive Bayes likelihood, in "copies per deck".
SMOOTHING = 0.1

#: Two archetype groups at least this similar are treated as one archetype.
#: 0.80 also merged real distinctions (Eldrazi Tron / Tron, Izzet / Temur
#: Prowess, Azorius Control / Azorius Energy all sit at 0.84); 0.85 is below the
#: naming duplicates and above those.
MERGE_SIMILARITY = 0.85

#: Posterior the best cluster needs before its name is returned.
MIN_CONFIDENCE = 0.8

#: MTGGoldfish files decks that fit no named archetype under their colours
#: ("UB", "WUR"). Those are bins, not archetypes: a sample matched to one says
#: nothing, so they are left out of the model.
_COLOR_BUCKET = re.compile(r"^[WUBRG]{1,5}$")


class ArchetypeClassifierProto(Protocol):
    """What :func:`detect_archetype` needs from a model."""

    def classify(self, cards: Iterable[str], mtg_format: str | None = None) -> str: ...


@dataclass(frozen=True)
class LabelledDeck:
    """One cached decklist with the archetype it was filed under."""

    mtg_format: str
    archetype: str
    mainboard: Mapping[str, float]
    sideboard: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ArchetypeCluster:
    """A group of archetype labels that share one card profile."""

    name: str
    labels: tuple[str, ...]
    deck_count: int


@dataclass(frozen=True)
class ArchetypeMatch:
    """The best cluster for a sample, before the confidence threshold."""

    archetype: str
    confidence: float
    mtg_format: str
    recognised_cards: int


@dataclass
class _Profile:
    cluster: ArchetypeCluster
    mtg_format: str
    weights: dict[str, float]
    log_denominator: float = 0.0
    log_prior: float = 0.0


@dataclass
class _Scope:
    """Clusters scored against each other, and the vocabulary they span."""

    profiles: list[_Profile]
    vocabulary: frozenset[str]


def is_color_bucket(archetype: str) -> bool:
    """Whether *archetype* is a colour-only bin rather than a named archetype."""
    return bool(_COLOR_BUCKET.match(archetype.strip()))


def _format_key(mtg_format: str | None) -> str:
    return (mtg_format or "").strip().lower()


def _presence(decks: list[dict[str, float]]) -> dict[str, float]:
    counts: dict[str, int] = {}
    for deck in decks:
        for card in deck:
            counts[card] = counts.get(card, 0) + 1
    return {card: n / len(decks) for card, n in counts.items()}


def _weighted_unit(presence: Mapping[str, float], idf: Mapping[str, float]) -> dict[str, float]:
    vector = {card: rate * idf[card] for card, rate in presence.items()}
    norm = math.sqrt(sum(v * v for v in vector.values()))
    return {card: v / norm for card, v in vector.items()} if norm else {}


def _dot(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b[card] for card, v in a.items() if card in b)


def _cluster_labels(
    decks_by_label: dict[str, list[dict[str, float]]], merge_similarity: float | None
) -> list[list[str]]:
    """Group labels whose IDF-weighted presence profiles are near-identical.

    Agglomerative: the most similar pair at or above the threshold is merged,
    the merged group's profile is recomputed from its pooled decks, and the scan
    repeats until no pair qualifies. Only the merged group's similarities are
    recomputed after each merge, so a format with ~90 labels stays cheap.
    """
    labels = sorted(decks_by_label)
    groups = [[label] for label in labels]
    if merge_similarity is None or len(groups) < 2:
        return groups

    # IDF over archetypes, each counted by the share of its decks playing the card.
    presences = [_presence(decks_by_label[label]) for label in labels]
    spread: dict[str, float] = {}
    for presence in presences:
        for card, rate in presence.items():
            spread[card] = spread.get(card, 0.0) + rate
    n_labels = len(labels)
    idf = {card: math.log((n_labels + 1) / (s + 0.5)) for card, s in spread.items()}

    vectors = [_weighted_unit(presence, idf) for presence in presences]
    similarity = {
        (i, j): _dot(vectors[i], vectors[j]) for i, j in combinations(range(len(groups)), 2)
    }
    alive = set(range(len(groups)))

    while True:
        best_pair: tuple[int, int] | None = None
        best = merge_similarity
        for pair, value in similarity.items():
            if value >= best:
                best, best_pair = value, pair
        if best_pair is None:
            break
        keep, drop = best_pair
        groups[keep] = groups[keep] + groups[drop]
        alive.discard(drop)
        similarity = {pair: v for pair, v in similarity.items() if drop not in pair}
        pooled = [deck for label in groups[keep] for deck in decks_by_label[label]]
        vectors[keep] = _weighted_unit(_presence(pooled), idf)
        for other in alive:
            if other != keep:
                similarity[(min(keep, other), max(keep, other))] = _dot(
                    vectors[keep], vectors[other]
                )

    return [groups[i] for i in sorted(alive)]


class ArchetypeModel:
    """Per-format archetype profiles built from labelled decklists."""

    def __init__(
        self,
        scopes: dict[str, _Scope],
        *,
        aliases: Mapping[str, str] | None = None,
        smoothing: float = SMOOTHING,
        min_confidence: float = MIN_CONFIDENCE,
        deck_count: int = 0,
    ) -> None:
        self._scopes = scopes
        self._aliases = dict(aliases or {})
        self._smoothing = smoothing
        self.min_confidence = min_confidence
        self.deck_count = deck_count
        self._all: _Scope | None = None

    # ------------------------------------------------------------------ build
    @classmethod
    def build(
        cls,
        decks: Iterable[LabelledDeck],
        *,
        sideboard_weight: float = SIDEBOARD_WEIGHT,
        smoothing: float = SMOOTHING,
        merge_similarity: float | None = MERGE_SIMILARITY,
        min_confidence: float = MIN_CONFIDENCE,
    ) -> ArchetypeModel:
        folded: dict[str, str] = {}

        def fold(name: str) -> str:
            key = folded.get(name)
            if key is None:
                key = folded[name] = fold_card_name(name)
            return key

        # format -> label -> [{folded card: weighted copies}]
        by_format: dict[str, dict[str, list[dict[str, float]]]] = {}
        deck_count = 0
        for deck in decks:
            fmt = _format_key(deck.mtg_format)
            label = (deck.archetype or "").strip()
            if not fmt or not label or is_color_bucket(label) or not deck.mainboard:
                continue
            copies: dict[str, float] = {}
            for name, count in deck.mainboard.items():
                key = fold(name)
                if key:
                    copies[key] = copies.get(key, 0.0) + count
            for name, count in deck.sideboard.items():
                key = fold(name)
                if key:
                    copies[key] = copies.get(key, 0.0) + count * sideboard_weight
            by_format.setdefault(fmt, {}).setdefault(label, []).append(copies)
            deck_count += 1

        scopes: dict[str, _Scope] = {}
        for fmt, decks_by_label in by_format.items():
            profiles: list[_Profile] = []
            vocabulary: set[str] = set()
            for group in _cluster_labels(decks_by_label, merge_similarity):
                pooled = [deck for label in group for deck in decks_by_label[label]]
                totals: dict[str, float] = {}
                for copies in pooled:
                    for card, count in copies.items():
                        totals[card] = totals.get(card, 0.0) + count
                weights = {card: total / len(pooled) for card, total in totals.items()}
                vocabulary.update(weights)
                # Best-represented label names the group; ties break alphabetically.
                name = min(group, key=lambda label: (-len(decks_by_label[label]), label))
                cluster = ArchetypeCluster(
                    name=name, labels=tuple(sorted(group)), deck_count=len(pooled)
                )
                profiles.append(_Profile(cluster=cluster, mtg_format=fmt, weights=weights))
            scope = _Scope(profiles=profiles, vocabulary=frozenset(vocabulary))
            _prepare(scope, smoothing)
            scopes[fmt] = scope

        # MTGO's game log names the half of a split card that was cast, while
        # decklists carry "Fire // Ice"; let either half find the whole card.
        vocabulary_all = set().union(*(scope.vocabulary for scope in scopes.values()))
        aliases: dict[str, str] = {}
        for card in vocabulary_all:
            if " // " in card:
                for half in card.split(" // "):
                    half = half.strip()
                    if half and half not in vocabulary_all:
                        aliases.setdefault(half, card)

        return cls(
            scopes,
            aliases=aliases,
            smoothing=smoothing,
            min_confidence=min_confidence,
            deck_count=deck_count,
        )

    # ------------------------------------------------------------------ queries
    @property
    def formats(self) -> tuple[str, ...]:
        return tuple(sorted(self._scopes))

    @property
    def archetype_count(self) -> int:
        return sum(len(scope.profiles) for scope in self._scopes.values())

    def clusters(self, mtg_format: str) -> list[ArchetypeCluster]:
        scope = self._scopes.get(_format_key(mtg_format))
        return [profile.cluster for profile in scope.profiles] if scope else []

    def _scope_for(self, mtg_format: str | None) -> _Scope | None:
        scope = self._scopes.get(_format_key(mtg_format))
        if scope is not None:
            return scope
        # Format unknown (or one the cache has no decks for): score every
        # format's clusters together over the union vocabulary.
        if not self._scopes:
            return None
        if self._all is None:
            profiles = [
                _Profile(profile.cluster, profile.mtg_format, profile.weights)
                for key in sorted(self._scopes)
                for profile in self._scopes[key].profiles
            ]
            vocabulary = frozenset().union(*(s.vocabulary for s in self._scopes.values()))
            scope = _Scope(profiles=profiles, vocabulary=vocabulary)
            _prepare(scope, self._smoothing)
            self._all = scope
        return self._all

    def match(self, cards: Iterable[str], mtg_format: str | None = None) -> ArchetypeMatch | None:
        """Return the most likely cluster for *cards*, whatever its confidence.

        *mtg_format* scopes the candidates to that format's clusters; ``None``,
        ``"Unknown"`` or a format with no cached decks scores all of them.
        Returns ``None`` when none of the cards is known to that scope.
        """
        scope = self._scope_for(mtg_format)
        if scope is None or not scope.profiles:
            return None
        seen: set[str] = set()
        for card in cards:
            key = fold_card_name(card)
            key = self._aliases.get(key, key)
            if key in scope.vocabulary:
                seen.add(key)
        if not seen:
            return None

        smoothing = self._smoothing
        scores: list[float] = []
        for profile in scope.profiles:
            weights = profile.weights
            score = profile.log_prior - len(seen) * profile.log_denominator
            for card in seen:
                score += math.log(weights.get(card, 0.0) + smoothing)
            scores.append(score)
        best_index = max(range(len(scores)), key=scores.__getitem__)
        top = scores[best_index]
        confidence = 1.0 / sum(math.exp(score - top) for score in scores)
        best = scope.profiles[best_index]
        return ArchetypeMatch(
            archetype=best.cluster.name,
            confidence=confidence,
            mtg_format=best.mtg_format,
            recognised_cards=len(seen),
        )

    def classify(self, cards: Iterable[str], mtg_format: str | None = None) -> str:
        """Return the archetype name, or ``"Unknown"`` below the confidence bar."""
        result = self.match(cards, mtg_format)
        if result is None or result.confidence < self.min_confidence:
            return UNKNOWN_ARCHETYPE
        return result.archetype


def _prepare(scope: _Scope, smoothing: float) -> None:
    """Precompute each profile's likelihood denominator and prior."""
    size = len(scope.vocabulary)
    total_decks = sum(profile.cluster.deck_count for profile in scope.profiles)
    for profile in scope.profiles:
        profile.log_denominator = math.log(sum(profile.weights.values()) + smoothing * size)
        profile.log_prior = math.log(profile.cluster.deck_count / total_decks)


def detect_archetype(
    cards: list[str],
    model: ArchetypeClassifierProto | None = None,
    mtg_format: str | None = None,
) -> str:
    """Classify the cards one player revealed in a match.

    ``"Unknown"`` when no model is available yet (it is built in the background
    at startup from the cached decklists) or when the evidence is too thin.
    """
    if model is None or not cards:
        return UNKNOWN_ARCHETYPE
    return model.classify(cards, mtg_format)


__all__ = [
    "MERGE_SIMILARITY",
    "MIN_CONFIDENCE",
    "SIDEBOARD_WEIGHT",
    "SMOOTHING",
    "UNKNOWN_ARCHETYPE",
    "ArchetypeClassifierProto",
    "ArchetypeCluster",
    "ArchetypeMatch",
    "ArchetypeModel",
    "LabelledDeck",
    "detect_archetype",
    "is_color_bucket",
]
