"""Small labelled decklists for the archetype-model tests.

Hand-written stand-ins for the cached decklists the real model is built from.
Each archetype has a *core* every list plays and *flex* slots that vary from
list to list, so held-out decks are never byte-identical to the training ones --
the property the offline evaluation relies on at full scale.

Deliberate overlaps, because they are what the classifier has to cope with:

- Lightning Bolt is in Boros Burn *and* Izzet Murktide (a format staple).
- The Tron lands are in Tron *and* Eldrazi Tron (two real, distinct archetypes).
- "Living End" and "Living End Cascade" are one deck under two names (the
  MTGGoldfish-vs-MTGO naming split the clustering step exists for).
- Pauper "Burn" shares its burn spells with Modern "Boros Burn", so the same
  cards name different archetypes depending on the format.
- "UR" is an MTGGoldfish colour bin, which the model must ignore.
"""

from __future__ import annotations

import random

from services.gamelog_service.archetypes import LabelledDeck

_MODERN: dict[str, tuple[dict[str, int], dict[str, int]]] = {
    "Boros Burn": (
        {
            "Lightning Bolt": 4,
            "Lava Spike": 4,
            "Rift Bolt": 4,
            "Goblin Guide": 4,
            "Monastery Swiftspear": 4,
            "Boros Charm": 4,
            "Skewer the Critics": 4,
            "Lightning Helix": 4,
            "Inspiring Vantage": 4,
            "Sacred Foundry": 2,
            "Arid Mesa": 4,
            "Mountain": 6,
        },
        {
            "Eidolon of the Great Revel": 4,
            "Searing Blaze": 3,
            "Light Up the Stage": 4,
            "Bloodstained Mire": 2,
            "Sunbaked Canyon": 2,
            "Path to Exile": 2,
        },
    ),
    "Izzet Murktide": (
        {
            "Murktide Regent": 4,
            "Dragon's Rage Channeler": 4,
            "Ragavan, Nimble Pilferer": 4,
            "Expressive Iteration": 4,
            "Consider": 4,
            "Lightning Bolt": 4,
            "Counterspell": 4,
            "Unholy Heat": 4,
            "Mishra's Bauble": 4,
            "Scalding Tarn": 4,
            "Steam Vents": 2,
            "Island": 3,
        },
        {
            "Spell Pierce": 2,
            "Spirebluff Canal": 4,
            "Fire // Ice": 2,
            "Flusterstorm": 2,
            "Mountain": 1,
            "Otawara, Soaring City": 1,
        },
    ),
    "Tron": (
        {
            "Urza's Tower": 4,
            "Urza's Mine": 4,
            "Urza's Power Plant": 4,
            "Karn Liberated": 4,
            "Wurmcoil Engine": 3,
            "Ancient Stirrings": 4,
            "Sylvan Scrying": 4,
            "Expedition Map": 4,
            "Chromatic Star": 4,
            "Forest": 4,
        },
        {
            "Oblivion Stone": 2,
            "Relic of Progenitus": 2,
            "Ugin, the Spirit Dragon": 2,
            "World Breaker": 1,
            "Chromatic Sphere": 4,
            "Sanctum of Ugin": 1,
        },
    ),
    "Eldrazi Tron": (
        {
            "Urza's Tower": 4,
            "Urza's Mine": 4,
            "Urza's Power Plant": 4,
            "Thought-Knot Seer": 4,
            "Reality Smasher": 4,
            "Matter Reshaper": 4,
            "Chalice of the Void": 4,
            "Eldrazi Temple": 4,
            "Wastes": 4,
            "Karn, the Great Creator": 4,
        },
        {
            "Walking Ballista": 2,
            "Kozilek's Command": 3,
            "Dismember": 2,
            "Ulamog, the Defiler": 1,
            "Cavern of Souls": 2,
            "Talisman of Resilience": 2,
        },
    ),
    "Living End": (
        {
            "Living End": 3,
            "Violent Outburst": 4,
            "Shardless Agent": 4,
            "Street Wraith": 4,
            "Striped Riverwinder": 4,
            "Architects of Will": 4,
            "Curator of Mysteries": 4,
            "Force of Negation": 4,
            "Grief": 4,
            "Watery Grave": 2,
        },
        {
            "Subtlety": 2,
            "Endurance": 2,
            "Waker of Waves": 2,
            "Misty Rainforest": 3,
            "Breeding Pool": 2,
            "Blood Crypt": 1,
        },
    ),
    "UR": (
        {
            "Lightning Bolt": 4,
            "Counterspell": 4,
            "Snapcaster Mage": 4,
            "Cryptic Command": 4,
            "Steam Vents": 4,
            "Island": 8,
            "Mountain": 6,
        },
        {"Opt": 4, "Electrolyze": 3, "Vendilion Clique": 2},
    ),
}

_PAUPER: dict[str, tuple[dict[str, int], dict[str, int]]] = {
    "Burn": (
        {
            "Lightning Bolt": 4,
            "Chain Lightning": 4,
            "Fireblast": 4,
            "Rift Bolt": 4,
            "Lava Dart": 4,
            "Skewer the Critics": 4,
            "Kessig Flamebreather": 4,
            "Mountain": 16,
        },
        {"Firebolt": 4, "Fireblast Wave": 2, "Searing Blaze": 2, "Guttersnipe": 3},
    ),
    "Affinity": (
        {
            "Myr Enforcer": 4,
            "Thoughtcast": 4,
            "Galvanic Blast": 4,
            "Frogmite": 4,
            "Seat of the Synod": 4,
            "Vault of Whispers": 4,
            "Springleaf Drum": 4,
            "Carapace Forger": 4,
        },
        {"Deadly Dispute": 4, "Krark-Clan Shaman": 2, "Fling": 2, "Atog": 3},
    ),
}


def _variants(
    mtg_format: str,
    label: str,
    core: dict[str, int],
    flex: dict[str, int],
    count: int,
    rng: random.Random,
) -> list[LabelledDeck]:
    decks = []
    flex_names = sorted(flex)
    for _ in range(count):
        mainboard = dict(core)
        for name in rng.sample(flex_names, k=max(1, len(flex_names) // 2)):
            mainboard[name] = flex[name]
        sideboard = {name: 1 for name in flex_names if name not in mainboard}
        decks.append(LabelledDeck(mtg_format, label, mainboard, sideboard))
    return decks


def fixture_decks(per_archetype: int = 4, seed: int = 7) -> list[LabelledDeck]:
    """Every fixture archetype, *per_archetype* varied lists each.

    "Living End Cascade" is the same deck as "Living End" filed under the other
    naming source, with fewer lists, as a real duplicate label would be.
    """
    rng = random.Random(seed)
    decks: list[LabelledDeck] = []
    for label, (core, flex) in _MODERN.items():
        decks += _variants("modern", label, core, flex, per_archetype, rng)
    core, flex = _MODERN["Living End"]
    decks += _variants("modern", "Living End Cascade", core, flex, 2, rng)
    for label, (core, flex) in _PAUPER.items():
        decks += _variants("pauper", label, core, flex, per_archetype, rng)
    return decks


def deck_text(deck: LabelledDeck) -> str:
    """Render a fixture deck the way the deck-text cache stores one."""
    main = "\n".join(f"{count} {name}" for name, count in deck.mainboard.items())
    side = "\n".join(f"{count} {name}" for name, count in deck.sideboard.items())
    return f"{main}\n\n{side}" if side else main


def sample_seen_cards(deck: LabelledDeck, distinct: int, rng: random.Random) -> list[str]:
    """Deal a shuffled 75 until *distinct* names have shown up, as a game log would."""
    pool = [name for name, n in deck.mainboard.items() for _ in range(int(n))]
    pool += [name for name, n in deck.sideboard.items() for _ in range(int(n))]
    rng.shuffle(pool)
    seen: list[str] = []
    for name in pool:
        if name not in seen:
            seen.append(name)
            if len(seen) == distinct:
                break
    return seen
