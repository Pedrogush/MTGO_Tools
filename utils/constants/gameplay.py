"""Gameplay-related constants shared across services."""

import re

MANA_SYMBOL_PATTERN = re.compile(r"\{[^}]{1,6}\}")

MANA_INPUT_CHARS: frozenset[str] = frozenset("wubrgcsxyz0123456789p")

_MANA_SINGLE_KEYS: dict[str, str] = {
    "w": "W",
    "u": "U",
    "b": "B",
    "r": "R",
    "g": "G",
    "c": "C",
    "s": "S",
    "x": "X",
    "y": "Y",
    "z": "Z",
}

_MANA_HYBRID_KEYS: dict[tuple[str, str], str] = {
    ("w", "u"): "W/U",
    ("w", "b"): "W/B",
    ("u", "b"): "U/B",
    ("u", "r"): "U/R",
    ("b", "r"): "B/R",
    ("b", "g"): "B/G",
    ("r", "g"): "R/G",
    ("r", "w"): "R/W",
    ("g", "w"): "G/W",
    ("g", "u"): "G/U",
    ("c", "w"): "C/W",
    ("c", "u"): "C/U",
    ("c", "b"): "C/B",
    ("c", "r"): "C/R",
    ("c", "g"): "C/G",
    ("2", "w"): "2/W",
    ("2", "u"): "2/U",
    ("2", "b"): "2/B",
    ("2", "r"): "2/R",
    ("2", "g"): "2/G",
    ("w", "p"): "W/P",
    ("u", "p"): "U/P",
    ("b", "p"): "B/P",
    ("r", "p"): "R/P",
    ("g", "p"): "G/P",
}

MANA_KEY_SYMBOL_MAP: dict[frozenset[str], str] = {
    frozenset({k}): v for k, v in _MANA_SINGLE_KEYS.items()
}
for _pair, _sym in _MANA_HYBRID_KEYS.items():
    MANA_KEY_SYMBOL_MAP[frozenset(_pair)] = _sym
for _i in range(10):
    MANA_KEY_SYMBOL_MAP[frozenset({str(_i)})] = str(_i)


LOREM_MANA: str = (
    "{G/U} Lorem {R/W} ipsum {W} dolor {U} sit {B} amet, {R} consectetur {G} adipiscing"
    " {C} elit, {S} sed {X} do {Y} eiusmod {Z} tempor {W/U} incididunt {W/B} ut {U/B}"
    " labore {U/R} et {B/R} dolore {B/G} magna {R/G} aliqua. {G/W} Ut {G/U} enim {C/W}"
    " ad {C/U} minim {C/B} veniam {C/R} quis {C/G} nostrud {2/W} exercitation {2/U}"
    " ullamco {2/B} laboris {2/R} nisi {2/G} aliquip {W/P} ex {U/P} ea {B/P} commodo"
    " {R/P} consequat. {G/P} Duis {0} aute {1} irure {2} dolor {3} in"
)

FULL_MANA_SYMBOLS: list[str] = (
    ["W", "U", "B", "R", "G", "C", "S", "X", "Y", "Z", "∞", "½"]
    + [str(i) for i in range(0, 21)]
    + [
        "W/U",
        "W/B",
        "U/B",
        "U/R",
        "B/R",
        "B/G",
        "R/G",
        "R/W",
        "G/W",
        "G/U",
        "C/W",
        "C/U",
        "C/B",
        "C/R",
        "C/G",
        "2/W",
        "2/U",
        "2/B",
        "2/R",
        "2/G",
        "W/P",
        "U/P",
        "B/P",
        "R/P",
        "G/P",
    ]
)
