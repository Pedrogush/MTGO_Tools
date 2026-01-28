"""Gameplay-related constants shared across services."""

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
