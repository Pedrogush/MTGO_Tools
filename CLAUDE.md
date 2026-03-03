# MTG Metagame Analysis Tools

A Python tool for Magic: The Gathering Online that combines web scraping, log file parsing, and OCR for opponent tracking and metagame research.

**Purpose:** Provides real-time opponent deck tracking during MTGO matches and comprehensive metagame analysis through MTGGoldfish data scraping and MTGO GameLog parsing.

**Tech Stack:** Python 3.11+, BeautifulSoup, MongoDB, wxPython GUI, PyGetWindow (window detection), MTGOSDK (C# bridge).

**Key Features:**
- **Opponent Tracking Widget:** Real-time window-title-based opponent identification with automatic deck lookup from tournament results
- **Hypergeometric Calculator:** Built-in probability calculator for draw odds (e.g., "chance to draw a 4-of in opening hand")
- **Metagame Research:** Browse and analyze MTGGoldfish archetype data, deck lists, and tournament results
- **Match History:** Parse MTGO GameLog files to extract historical match data, opponent names, and results
- **Deck Editor:** Interactive deck list editor with card adjustment, averaging, export, and MongoDB storage
- **Challenge Timer Alerts:** Monitor and alert on MTGO challenge timer countdowns

**Key Modules:**
- `widgets/identify_opponent.py` - Real-time opponent tracking overlay with hypergeometric calculator
- `widgets/deck_selector_wx.py` - Deck browser and editor GUI
- `navigators/mtggoldfish.py` - MTGGoldfish web scraping
- `utils/find_opponent_names.py` - Opponent detection via MTGO window titles ("vs." pattern)
- `utils/math_utils.py` - Hypergeometric probability calculations for draw odds
- `utils/metagame.py` - Player lookup and metagame data processing
- `utils/gamelog_parser.py` - MTGO GameLog parsing for match history
- `utils/dbq.py` - MongoDB deck storage (save/load/delete/update)
- `utils/deck.py` - Deck parsing and analysis (`analyze_deck()`)
- `dotnet/MTGOBridge/Program.cs` - C# bridge to MTGOSDK for MTGO client interaction
- `scripts/mtgosdk_repl.py` - PythonNET scratchpad for exploring MTGOSDK API surface

**Use Case:** Helps competitive MTGO players by providing intelligence on opponents' recent decks and facilitating metagame research, all through passive observation and web scraping (no gameplay automation).

```bash
python main.py
```

# Standalone Widget Entry Points

Each widget can be executed directly as a Python module:

```bash
python -m widgets.identify_opponent   # Opponent Tracker
python -m widgets.match_history       # Match History viewer
python -m widgets.timer_alert         # Challenge timer alerts
python -m widgets.metagame_analysis   # Metagame analysis
```

Console scripts (after `pip install -e .`):
```bash
mtgo-opponent-tracker
mtgo-match-history
mtgo-timer-alert
mtgo-metagame
```

**Requirements by widget:**
- `mtgo-opponent-tracker`: MTGO running with an active match window
- `mtgo-match-history`: GameLog files (MTGO creates these automatically)
- `mtgo-timer-alert`: MTGO running + MTGOBridge.exe compiled
- `mtgo-metagame`: No MTGO required (web scraping only)

Each widget has a `main()` function that initializes base dirs, configures logging, creates a wxPython app, and runs the event loop.

# CI/PR Workflow

When creating a PR:
1. After `gh pr create`, poll `gh pr checks <PR#>` every **1 minute**
2. If checks fail, fix locally, commit, push, and continue polling
3. **Stop polling** when either all checks pass OR 3 consecutive polls show no status changes
4. Common CI checks: Linting & Formatting (ruff/black), Type Checking, Compilation, Security Scanning, .NET Build
5. Run `black <file>` and `ruff check <file> --fix` locally before pushing

# Architecture

## Opponent Detection

Opponent names are detected by scanning MTGO window titles for the "vs." pattern using `pygetwindow.getAllTitles()`. The widget polls every 2 seconds. No MTGOSDK bridge is required for opponent tracking.

Example: `"MTGO - Match vs. PlayerName"` → extracts `"PlayerName"`

## GameLog Parsing (Hybrid Architecture)

Historical match data is extracted by parsing MTGO's GameLog files directly (bypassing MTGOSDK, which has a broken `HistoricalMatch.Opponents` API).

- **MTGOSDK / C# MTGOBridge**: challenge timer, collection export, log file location
- **GameLog parsing (Python)**: match history, opponent names, match results

GameLog files use pipe-delimited format with `@PPlayerName@` markers. `MTGOBridge.exe logfiles` returns JSON with file paths; filesystem search is used as a fallback.

See `docs/GAMELOG_PARSING.md` for full format details.

## Deck Research Browser

All network operations (MTGGoldfish scraping, database queries) are async via background threads. UI updates use `wx.CallAfter` / `root.after(0, callback)` to stay thread-safe. The window opens instantly; data loads in the background.

Two browsing modes:
- **Browse MTGGoldfish**: scrape tournament decks by archetype
- **Saved Decks**: browse your local MongoDB collection

# Database (MongoDB)

MongoDB database: `lm_scraper`, collection: `decks`.

```javascript
{
  _id: ObjectId,
  name: "2025-01-15 PlayerName MTGO Challenge 5-0",
  content: "4 Lightning Bolt\n...",
  format: "Modern",
  archetype: "UR Murktide",
  player: "PlayerName",
  source: "mtggoldfish" | "manual" | "averaged",
  date_saved: ISODate,
  date_modified: ISODate,
  metadata: { date, event, result, deck_number }
}
```

**API (`utils/dbq.py`):**
- `save_deck_to_db(name, content, format, archetype, player, source, metadata)` → ObjectId
- `get_saved_decks(format_type, archetype, sort_by)` → list of docs
- `load_deck_from_db(deck_id)` → doc or None
- `delete_saved_deck(deck_id)` → bool
- `update_deck_in_db(deck_id, content, name, metadata)` → bool

**Troubleshooting:**
- "Connection refused": verify MongoDB is running on port 27017
- "No module named 'pymongo'": `pip install -r requirements.txt`

# Hypergeometric Calculator

Built into the Opponent Tracker widget (collapsible panel). Calculates draw probabilities using the hypergeometric distribution (`math.comb()`).

Inputs: Deck Size, Copies in Deck, Cards Drawn, Target Copies. Presets for opening hand (60-card, 40-card) and turn 3 (play/draw).

- `utils/math_utils.py` - calculation functions
- `tests/test_math_utils.py` - unit tests
- `widgets/identify_opponent.py` - UI integration

# UI Automation (WSL Testing)

The app runs in Windows but can be launched and controlled entirely from WSL. The `automation` package exposes a socket server (port 19847); WSL2 localhost forwarding (on by default) makes `127.0.0.1` in WSL reach the Windows-side server transparently.

## Launching the app from WSL

Use `cmd.exe` to start the Windows Python process in the background:

```bash
cmd.exe /c "start python C:\Users\Pedro\Documents\GitHub\mtgo_tools\main.py --automation"
```

Then wait for the server to come up before sending commands:

```bash
python -m automation ping   # retry until this succeeds (takes a few seconds)
```

The `AutomationClient.wait_for_server(timeout=30)` method can be used in scripts to poll automatically.

## CLI commands

```bash
# Verify connection
python -m automation ping

# Take a screenshot and view the result
python -m automation screenshot --path /tmp/screen.png

# Typical workflow: set format → load archetypes → select one → inspect decks
python -m automation set-format Modern
python -m automation list-archetypes
python -m automation select-archetype --name "UR Murktide"
python -m automation list-decks
python -m automation select-deck 0
python -m automation get-deck

# Other useful commands
python -m automation status          # Read the status bar
python -m automation window-info     # Window geometry and visibility
python -m automation list-widgets    # Enumerate registered widgets
python -m automation click <widget> --label <button>
python -m automation switch-tab "Stats"
python -m automation wait 500        # Wait 500ms (e.g. after triggering async load)
python -m automation builder-search "Lightning Bolt"

# Zone editing commands (deck builder tests)
python -m automation load-deck --file deck.txt           # Load a deck from file
python -m automation load-deck --text "4 Lightning Bolt\nSideboard\n2 Negate"
python -m automation get-zone-cards --zone main          # List mainboard cards
python -m automation get-zone-cards --zone side          # List sideboard cards
python -m automation add-card --zone main --name "Lightning Bolt"
python -m automation add-card --zone side --name "Rest in Peace" --qty 2
python -m automation remove-card --zone main --name "Goblin Guide"
python -m automation get-scroll-pos --zone main          # Check scroll position
python -m automation get-builder-results                 # Count of search results + mana symbols
python -m automation open-widget opponent_tracker        # Open a widget window
```

All commands accept `--json` for machine-readable output and `--timeout <seconds>` (default 30).

**Key files:**
- `automation/server.py` — socket server embedded in the app (`AutomationServer`, default port 19847)
- `automation/client.py` — Python client (`AutomationClient`, `wait_for_server()`)
- `automation/cli.py` — CLI entry point (`python -m automation`)
- `automation/test_runner.py` — basic connectivity test suite
- `automation/e2e_tests.py` — **UI regression test suite** (run locally, not in CI)

## UI Regression Tests

The `automation/e2e_tests.py` suite covers add/subtract cards, scrollbar persistence,
mana symbol rendering, buttons, widget opening, and card face loading.  It is
**not wired into GitHub Actions** and is meant for local verification only.

```bash
# Run all e2e tests (app must be running with --automation)
python -m automation.e2e_tests

# Run a specific group
python -m automation.e2e_tests --only builder
python -m automation.e2e_tests --only scrollbar
python -m automation.e2e_tests --only mana
```

Golden screenshots (for visual review) are saved to `automation/golden/`.

**Convention:** When using the automation CLI to diagnose and fix a UI bug,
add a test to `automation/e2e_tests.py` that reproduces the exact command
sequence used.  This ensures the fix is verifiable and prevents regressions.

# Notes

- MTGGoldfish scraping uses `/deck/{deck_num}` (robots.txt compliant); the `/deck/download/` endpoint is disallowed and must not be used.
