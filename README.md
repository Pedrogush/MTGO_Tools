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

```bash
# Format and lint
black .
ruff check --fix .

# Run tests
pytest
```

CI uses **black 26.3.1**. If formatting locally, match with `pip install black==26.3.1`.

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

- **Black**: formatting (line length 100)
- **Ruff**: linting
- **mypy**: type checking (permissive mode)
- **Bandit**: security linting

Configuration in `pyproject.toml`.

## Project Structure

```
├── main.py                         # Entry point (MetagameWxApp)
├── controllers/                    # AppController + helper modules
│   ├── app_controller.py
│   ├── app_controller_helpers.py
│   ├── bulk_data_helpers.py
│   ├── mtgo_background_helpers.py
│   └── session_manager.py
├── widgets/                        # wxPython UI
│   ├── app_frame.py                # Main window
│   ├── panels/                     # DeckResearchPanel, DeckBuilderPanel, RadarPanel, etc.
│   ├── dialogs/                    # Modal dialogs
│   └── buttons/                    # Custom button widgets
├── services/                       # Business logic
│   ├── deck_service.py             # Parsing, averaging, text building
│   ├── collection_service.py       # Collection loading and ownership
│   ├── search_service.py           # Card search and filtering
│   ├── image_service.py            # Card image caching
│   ├── radar_service.py            # Radar aggregation
│   ├── format_card_pool_service.py # Format card pool cache
│   ├── mtgo_background_service.py  # Background MTGO data fetch
│   └── store_service.py            # App state persistence
├── repositories/                   # Data access
│   ├── deck_repository.py          # Deck DB + file + state
│   ├── card_repository.py          # Card metadata + collection files
│   ├── metagame_repository.py      # Archetype/deck cache (JSON)
│   ├── radar_repository.py         # Radar snapshots (SQLite)
│   └── format_card_pool_repository.py  # Format pools (SQLite)
├── navigators/                     # Web scrapers
│   ├── mtggoldfish.py              # MTGGoldfish metagame + decklists
│   └── mtgo_decklists.py           # MTGO.com parser (currently disabled)
├── utils/                          # Shared utilities
│   ├── card_data.py                # CardDataManager (MTGJson atomic-cards)
│   ├── card_images.py              # Scryfall bulk image downloader
│   ├── atomic_io.py                # Atomic file writes
│   ├── gamelog_parser.py           # MTGO game log parser
│   ├── archetype_classifier.py     # Deck → archetype classification
│   ├── deck.py                     # Deck text parsing helpers
│   └── mtgo_bridge_client.py       # IPC client for .NET bridge
├── dotnet/MTGOBridge/              # .NET bridge (MTGOSDK)
├── automation/                     # Automation CLI, server, and E2E helpers
└── tests/                          # pytest test suite
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
