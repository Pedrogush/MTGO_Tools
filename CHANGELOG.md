# Changelog

Notable changes to MTGO Tools, written for the people who use it.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
the project follows [semantic versioning](https://semver.org). The number itself
is computed after a merge lands on `main` — see
[`docs/VERSIONING.md`](docs/VERSIONING.md). Releases before 1.3.0 are documented
only by their [GitHub Release](https://github.com/Pedrogush/MTGO_Tools/releases)
notes.

## [1.3.0] — Unreleased

### Added

- **Deck version history.** Every save of a deck is recorded as a version, so a
  deck stops being one file you overwrite. A rail beside the cards lists the
  versions and loads any of them back with one click, and a new **History** tab
  shows the graph, the branches you have made, and the card-by-card difference
  between a version and what it came from. Your decklist file itself stays a
  plain `.txt` with no extra lines in it, so it still imports into MTGO and
  Manatraders unchanged.
- **Deck names.** A deck's name is shown in the deck's header and becomes the
  file it is saved to; click it to change it. The version history stays with
  the deck rather than with the name, so renaming keeps it — what a new name
  changes is the file: the next save writes one under it, and the old file is
  left where it is.
- **Archetype baseline.** A new **Baseline** tab measures the archetype of the
  deck on screen against the lists already cached for it: the cards every list
  runs and at what count, the cards every list runs at a count that moves, and
  the slots that are genuinely yours, with the flex candidates ranked by how
  often they are played. Decks that carry the archetype's label but do not
  resemble the pool are listed separately and left out of the measurement.
- **Goldfish tab.** Deal an opening hand off the mainboard, mulligan, draw, and
  play cards onto a table — click a card to put it down or tap it, drag it back
  to take it back.
- **Save the collection diff as a decklist.** The deck action button and the
  File menu can now save exactly what a deck needs and your collection does not
  have, as a decklist file you can paste wherever you buy, trade or rent. Copies
  are counted against one shared pool, so a card split between mainboard and
  sideboard asks for the right total.
- **File ▸ Check for updates.** Checks GitHub for a newer release on demand
  (and, optionally, on launch). If you accept, MTGO Tools downloads the
  installer, verifies it against the checksum published with the release,
  refuses to run anything that does not match, then closes itself while it
  installs and reopens when it is done.

### Changed

- **One MTGO bridge process instead of one per command.** Every collection
  import, trade query or watch used to start a new bridge and re-attach to the
  MTGO client, paying about four seconds before doing any work — and several
  bridges attached at once slowed each other down badly. The app now keeps one
  alive for the session. It respawns by itself if MTGO restarts, falls back to
  the old behaviour against a bridge build that does not support it, and
  `MTGO_BRIDGE_NO_SESSION=1` turns it off.

### Fixed

- Cards you own were reported as missing when your collection and your decklist
  spelled the name differently — MTGO reports the typographically correct name,
  accents and all, while decklists routinely spell it in plain ASCII. Names are
  now matched with accents folded, and collections already cached are corrected
  when they load rather than after the cache expires.
- The bridge's currency refresh scanned the collection card by card every ten
  minutes, which took minutes and stalled MTGO's own interface while it ran —
  including in the middle of a game. It is a single round trip now.
- When the bridge could not read your MTGO username it said nothing at all; it
  now reports why, and no longer gives up after the first of its two lookup
  strategies fails.
- Cards in the Goldfish tab were visibly softer than the same cards in the deck
  grid. They are drawn the same way now.

[1.3.0]: https://github.com/Pedrogush/MTGO_Tools/compare/v1.2.15...v1.3.0
