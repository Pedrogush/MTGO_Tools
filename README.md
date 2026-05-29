# MTGO Metagame Tools

A desktop application for Magic: The Gathering Online (MTGO) players providing metagame analysis, deck research, opponent tracking, and collection management.

![Python](https://img.shields.io/badge/python-3.11+-green)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![License](https://img.shields.io/badge/license-MIT-orange)

## Features

- **Metagame Analysis**: Browse top archetypes from MTGGoldfish with win rates, popularity, and per-day deck counts. Radar view shows card inclusion rates across recent tournament decks.
- **Deck Research**: Browse archetype deck lists, import from MTGGoldfish or paste directly, view average decklists from recent results.
- **Deck Builder**: Full card search with color, type, mana cost, oracle text, and format legality filters. Mana curve stats and collection ownership overlay.
- **Opponent Tracking**: Automatically detect opponents and fetch their recent decklists during a match.
- **Match History**: Parse MTGO game logs for comprehensive match history and win rate stats.
- **Sideboard Guides**: Create and manage matchup-specific sideboarding plans, stored per deck configuration.
- **Collection Management**: Import your MTGO collection via the .NET Bridge and see what cards you own or are missing for any deck.
- **Challenge Timer**: Alerts when MTGO challenge events are about to start.

## Installation

**Prerequisites**: Windows 10+, Python 3.11+, MongoDB (optional, for deck persistence), .NET 9.0 SDK (for MTGO Bridge).

```bash
git clone https://github.com/Pedrogush/MTGO_Tools.git
cd MTGO_Tools
pip install -r requirements-dev.txt
python main.py
```

## Development

Day-to-day development happens in WSL, while the app runtime target is Windows
(wxPython, MTGOSDK bridge, packaging). Linting, formatting, and most tests run
fine inside WSL; the full pytest suite (including wx-dependent tests) is run
against Windows Python via WSL interop:

```bash
# Format and lint (WSL or Windows)
black .
ruff check --fix .

# Run tests on the Windows-side Python from WSL
/init /mnt/c/Windows/System32/cmd.exe /c "pytest"

# Or, from Windows directly
pytest
```

CI installs the same pinned `black`, `ruff`, and `mypy` versions used locally
by reading `requirements-dev.txt`, so `pip install -r requirements-dev.txt`
already gives you the exact tool versions CI runs. See
`.github/VALIDATION_QUICKSTART.md` for the pre-commit validation flow that
mirrors CI (lint, format, compile, security).

### Automation CLI

The `automation` package can launch and control the wxPython app for manual UI
checks and E2E scripts:

```bash
python -m automation.cli open-app --wait
python -m automation.cli ping
python -m automation.cli screenshot --path screenshots/current.png
python -m automation.cli screenshot --headless --path screenshots/background.png
python -m automation.cli close-app
```

`screenshot --headless` is self-contained once the app is running with
automation enabled. It temporarily restores a minimized or hidden window for the
capture and returns it to the previous state afterward; no extra `cmd.exe` or
manual window-management step is required by the screenshot command itself.

See `automation/README.md` for port options, WSL interop notes, and close-app
behavior.

### GameLog / Match History Tests

`tests/test_gamelog_parser.py` parses local MTGO GameLog files and requires the `MTGO_USERNAME` environment variable. The venv activation scripts set this automatically. Tests are skipped when no GameLog directory is found.

### Code Quality

- **Black**: formatting (line length 100) — required, CI fails on diff
- **Ruff**: linting — required, CI fails on errors
- **mypy**: type checking (permissive mode) — **advisory only**; CI reports
  findings but does not block merges while typing coverage is incrementally
  improved
- **Bandit**: security linting — required, CI fails on issues
- **pip-audit**: dependency vulnerability scanning — advisory; audits
  `requirements.txt` and `requirements-dev.txt` explicitly

Tool versions are pinned in `requirements-dev.txt`; tool configuration lives
in `pyproject.toml`.

### Repo Reports

Two reports are committed under the repo root and `docs/diagrams/`:

```bash
python scripts/generate_loc_report.py            # writes LOC_REPORT.md
python scripts/generate_dependency_diagrams.py   # writes docs/diagrams/graph.json + dependencies_level_*.svg
```

Because these are generated from the whole source tree, they are **not** gated
in PR CI (every PR would otherwise conflict on them and fail a freshness
check). Instead the `Refresh Generated Reports` workflow
(`.github/workflows/refresh-reports.yml`) regenerates and commits them once a
day, and can be run on demand from the Actions tab. You can still run the
scripts locally (both support `--check` for drift detection), but you do not
need to commit their output in a feature branch.

## Project Structure

```
├── main.py                            # Entry point (MetagameWxApp)
├── controllers/                       # Application coordination
│   ├── app_controller/                # AppController package (mixins: lifecycle,
│   │                                  # archetypes, decks, collection, bulk_data,
│   │                                  # card_data, settings, ui_callbacks)
│   └── session_manager.py
├── widgets/                           # wxPython UI
│   ├── frames/                        # Main window + standalone frames
│   │   ├── app_frame/                 # Main window
│   │   ├── match_history/             # Match history viewer
│   │   ├── metagame_analysis/         # Metagame analysis frame
│   │   ├── radar/                     # Radar analysis frame
│   │   ├── identify_opponent/         # Opponent identification
│   │   └── ...                        # splash, rules_browser, top_cards, etc.
│   ├── panels/                        # DeckResearchPanel, DeckBuilderPanel, etc.
│   ├── dialogs/                       # Modal dialogs (feedback, help, tutorial, ...)
│   ├── buttons/                       # Custom button widgets
│   ├── lists/                         # List/grid widgets
│   ├── mana_icon_factory/             # Mana symbol bitmap/SVG renderer + cache
│   └── stylize.py                     # wx styling helpers
├── services/                          # Business logic
│   ├── deck_service/                  # Parsing, averaging, text building
│   ├── collection_service/            # Cache, parsing, ownership, stats, exporter
│   ├── search_service/                # Basic/builder/deck search, filtering, mana
│   ├── image_service/                 # Bulk data, metadata, cache, download queue
│   ├── radar_service/                 # Radar aggregation + precomputed snapshots
│   ├── gamelog_service/               # MTGO game log discovery + parsing
│   ├── mtgo_bridge_service/           # Python facade + transport for the .NET bridge
│   ├── bundle_snapshot_client/        # Remote bundle snapshot HTTP client
│   ├── format_card_pool_service.py    # Format card pool cache
│   ├── archetype_resolver.py          # Archetype name normalization
│   ├── card_service.py                # Card lookup facade
│   ├── deck_workflow_service.py       # Deck save/load workflow
│   ├── metagame_service.py            # Metagame queries
│   ├── comp_rules_service.py          # Comprehensive rules text
│   └── store_service.py               # App state persistence
├── repositories/                      # Data access
│   ├── card_repository/               # MTGJSON atomic-cards + collection files
│   ├── deck_repository/               # Deck DB + filesystem + UI state
│   ├── metagame_repository/           # Archetype/deck cache (JSON)
│   ├── radar_repository/              # Radar snapshots (SQLite)
│   ├── format_card_pool_repository/   # Format pools (SQLite)
│   ├── remote_snapshot_client/        # Remote bundle snapshot fetcher
│   ├── scrapers/                      # MTGGoldfish scrapers (text + visual)
│   └── deck_text_cache.py             # Deck text SQLite cache
├── utils/                             # Cross-cutting helpers
│   ├── atomic_io.py                   # Atomic file writes
│   ├── deck.py                        # Deck text parsing helpers
│   ├── background_worker.py           # Thread-pool helpers
│   ├── image_effects.py               # PIL image effects
│   ├── json_io.py                     # JSON read/write helpers
│   ├── logging_config.py              # Logging setup
│   ├── math_utils.py                  # Numeric helpers
│   ├── perf.py                        # Perf timers
│   ├── runtime_flags.py               # Runtime feature flags
│   ├── diagnostics.py                 # Diagnostic dumps
│   ├── find_opponent_names.py         # Opponent-name OCR helper
│   ├── constants/                     # Shared constants
│   └── i18n/                          # Translation helpers
├── dotnet/MTGOBridge/                 # .NET bridge (MTGOSDK)
├── automation/                        # Automation CLI, server, and E2E helpers
├── scripts/                           # Maintenance scripts (LOC + dep-graph reports, etc.)
└── tests/                             # pytest test suite
```

## MTGO Bridge

A .NET 9.0 component that reads collection and match data from the running MTGO client using MTGOSDK.

```bash
cd dotnet/MTGOBridge && dotnet build
```

MTGO must be running when using collection import features.

## Data Sources

- **Metagame data**: [MTGGoldfish](https://www.mtggoldfish.com/)
- **Card data**: [MTGJson](https://mtgjson.com/) atomic-cards database
- **Card images**: Scryfall bulk data + CDN
- **MTGO integration**: [MTGOSDK](https://github.com/videre-project/MTGOSDK)

## License

MIT — see LICENSE file.
