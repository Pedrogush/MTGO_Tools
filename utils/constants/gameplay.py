"""Gameplay-related constants shared across services."""

# All mana symbols joined in sequence, interspersed with the first 20 words of
# Lorem Ipsum, for use as oracle-text fixture data.
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
