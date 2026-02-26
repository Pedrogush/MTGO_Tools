# Change History

Historical record of significant changes, fixes, and architectural decisions.

---

## Hypergeometric Calculator

Added a built-in hypergeometric probability calculator to the Opponent Tracker widget (Issue #151). Helps players calculate draw probabilities during matches.

**Features:**
- Collapsible panel toggled via "Calculator" / "Hide Calc" button
- Inputs: Deck Size (default 60), Copies in Deck (default 4), Cards Drawn (default 7), Target Copies (default 1)
- Presets: "Open 60", "Open 40", "T3 Play", "T3 Draw"
- Shows exact probability and cumulative "at least N" probability
- Panel visibility persists across sessions

**Files:** `utils/math_utils.py`, `tests/test_math_utils.py`, `widgets/identify_opponent.py`

---

## Opponent Tracker Rewrite — Window Title Detection

The wxPython opponent tracker was failing with `wx.PyDeadObjectError` and had unreliable state management via the MTGOSDK bridge.

**Fix:** Replaced MTGOSDK bridge integration with simple window title polling. `utils/find_opponent_names.py` scans all window titles every 2 seconds for the "vs." pattern. All widget lifecycle exceptions are caught as `RuntimeError`.

Before: `BridgeWatcher` + MTGOSDK `activeMatch.players`
After: `pygetwindow.getAllTitles()` + regex on "MTGO - Match vs. PlayerName"

---

## GameLog Parsing — Architecture Change

`MTGOSDK.HistoricalMatch.Opponents` throws `InvalidCastException` because raw MTGO data stores opponents as strings but the SDK tries to cast them to `User` objects.

**Fix:** Parse MTGO GameLog files directly in Python, bypassing the broken API. Log files use a pipe-delimited format with `@PPlayerName@` markers. Parsing logic adapted from [cderickson/MTGO-Tracker](https://github.com/cderickson/MTGO-Tracker).

`MTGOBridge.exe logfiles` was added to return GameLog file paths via JSON. Filesystem search is used as a fallback when MTGO is not running.

See `docs/GAMELOG_PARSING.md` for the full log format spec.

---

## Deck Browser — Statistics Panel

Added a collapsible statistics panel to the Deck Research Browser showing:
- Metadata: archetype, player, format, source, date saved, tournament event/result
- Composition: mainboard/sideboard counts (total and unique), estimated lands/spells
- Top 5 most-played cards

`utils/deck.py:analyze_deck()` was added to parse mainboard/sideboard separately, handle fractional quantities from averaged decks, and estimate land counts heuristically.

The saved decks list now shows a `[MM/DD]` date prefix. Statistics display automatically when selecting a saved deck and hide when switching to Browse mode.

---

## Deck Browser — MongoDB Integration

Added full deck CRUD operations via MongoDB (`utils/dbq.py`). Decks are saved to both the database and the filesystem (dual storage). Database failures do not prevent file saves.

Two browsing modes were added to the UI:
- **Browse MTGGoldfish**: original scraping functionality
- **Saved Decks**: browse, load, edit, and delete your local collection

Decks are filtered by format in the saved decks list. All database operations run in background threads.

---

## Deck Browser — Lazy Loading

The Deck Research Browser previously blocked for 5–10 seconds on open while scraping MTGGoldfish synchronously.

**Fix:** All network I/O moved to background threads. The window now opens in <100ms; archetypes load 100ms after open. Progress indicators (⏳) are shown during loading. UI updates use `root.after(0, callback)` for thread safety.

---

## Deck Browser — Mode Switching Bug Fix

After switching from "Saved Decks" back to "Browse MTGGoldfish", the "Select archetype" button remained disabled.

**Fix:** `ui_reset_to_archetype_selection()` now explicitly sets `state="normal"` and calls `lazy_load_archetypes()` if archetypes have not yet been loaded. `on_archetypes_loaded()` guards against updating UI if the mode has changed since the background thread started.

---

## robots.txt Compliance Fix

MTGGoldfish's `robots.txt` disallows `/deck/download/{deck_num}`. The scraper was updated to use `/deck/{deck_num}` instead, extracting deck data from the embedded JavaScript on that page.
