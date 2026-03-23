# MTGO Metagame Tools

Windows-first wxPython desktop tooling for Magic: The Gathering Online. The repo now centers on a single main application with supporting widgets, an automation interface for UI testing, optional MongoDB-backed deck persistence, and a .NET bridge for MTGO collection and client-adjacent data.

## What The App Does

- Metagame research via MTGGoldfish scraping and local cacheing
- Deck browsing, import, editing, averaging, and export
- Deck statistics, notes, sideboard guides, and radar/frequency views
- Opponent tracking from MTGO window titles with an embedded hypergeometric calculator
- Match history parsing from MTGO GameLog files
- Collection loading and ownership analysis, with MTGO bridge refresh support
- Challenge timer alerts
- Automation server + CLI used for local UI regression coverage

## Current Entry Points

Main desktop app:

```bash
python3 main.py
```

Main app with automation enabled:

```bash
python3 main.py --automation
python3 -m automation ping
```

Standalone widget entry points:

```bash
python3 -m widgets.identify_opponent
python3 -m widgets.match_history
python3 -m widgets.timer_alert
python3 -m widgets.metagame_analysis
```

Installed console scripts from `pyproject.toml`:

```bash
mtgo-opponent-tracker
mtgo-match-history
mtgo-timer-alert
mtgo-metagame
```

## Architecture Snapshot

The old Tk/deck-selector-era documentation is no longer accurate. The current codebase is structured around:

- `main.py`
  - Bootstraps `MetagameWxApp`, splash screen, logging, base dirs, and optional automation server.
- `controllers/`
  - `app_controller.py` is the orchestration layer between UI, services, repositories, background work, and persisted session state.
  - `session_manager.py` persists format, deck source, locale, window state, current deck text, and zone contents.
  - `bulk_data_helpers.py` and `mtgo_background_helpers.py` coordinate background refresh flows.
- `widgets/`
  - `app_frame.py` is the main window.
  - `widgets/panels/` contains the research, builder, stats, notes, radar, card inspector, and sideboard guide panels.
  - `widgets/handlers/` keeps UI event wiring out of the view constructors.
  - Top-level widgets include opponent tracker, match history, metagame analysis, timer alerts, splash frame, and mana keyboard.
- `services/`
  - Business logic for decks, deck workflows, search, images, collection handling, radar analysis, persistence stores, MTGO background fetch, parsing, and export.
- `repositories/`
  - `card_repository.py` for bulk card data, printings, and collection file access.
  - `deck_repository.py` for current deck state, file save/load helpers, MongoDB deck CRUD, notes/outboard/guide JSON stores, and averaging support.
  - `metagame_repository.py` for archetype/deck caching and source merging.
- `navigators/`
  - `mtggoldfish.py` is the active scraper path.
  - `mtgo_decklists.py` exists, but MTGO decklist ingestion is feature-flagged off by default.
- `automation/`
  - Socket server/client/CLI for driving a running app instance from tests or WSL.
- `dotnet/MTGOBridge/`
  - .NET 9 bridge used for collection snapshots and other MTGO-facing operations.

## Important Current Behavior

### MTGO decklists are disabled by default

`utils.constants.MTGO_DECKLISTS_ENABLED` is controlled by the `MTGO_DECKLISTS_ENABLED` environment variable and defaults to `false`.

Effect:

- Background MTGO deck fetch is skipped unless explicitly enabled.
- Archetype/deck browsing still works through MTGGoldfish.
- Repository/service code still supports MTGO deck sources when the feature flag is turned on again.

### Persistence is split across files and optional MongoDB

- Deck/session/UI state is stored in JSON/text files under paths defined in `utils/constants/`.
- Deck saves still attempt MongoDB persistence through `repositories/deck_repository.py`.
- MongoDB is optional in practice for many workflows, but database save/load support is still implemented against `mongodb://localhost:27017/`, database `lm_scraper`, collection `decks`.

### Opponent tracking no longer depends on MTGOSDK for detection

`widgets/identify_opponent.py` detects opponents from MTGO window titles via `utils.find_opponent_names`, then enriches the result with scraped/cached deck data and optional radar/guide information.

### Match history is file-driven

`widgets/match_history.py` and `utils/gamelog_parser.py` operate on MTGO GameLog files instead of relying on MTGOSDK historical match objects.

## Main UI Surface

The main application window in `widgets/app_frame.py` currently provides:

- Left stack:
  - `DeckResearchPanel`
  - `DeckBuilderPanel`
- Right-side tools:
  - toolbar buttons for opponent tracker, timer alerts, match history, metagame analysis, collection load, image download, card database refresh, and diagnostics export
- Deck workspace tabs/panels:
  - deck tables
  - stats
  - sideboard guide
  - notes
  - card inspector
  - deck results summary/list

Session state includes:

- current format
- left-side mode
- deck data source: `both`, `mtggoldfish`, or `mtgo`
- language/locale
- event logging toggle
- saved deck text and zone contents
- window size and screen position

## Automation And UI Testing

The app can expose a local socket automation server when launched with `--automation`.

Typical flow:

```bash
python3 main.py --automation
python3 -m automation ping
python3 -m automation status
python3 -m automation list-archetypes
python3 -m automation builder-search "Lightning Bolt"
```

Key files:

- `automation/server.py` - embedded server in the running app
- `automation/client.py` - Python client API
- `automation/cli.py` - `python3 -m automation ...`
- `automation/e2e_tests/` - local end-to-end UI regression suite

The e2e automation suite is for local verification and is not the same as the standard `pytest` test suite under `tests/`.

## Development Commands

Run the app:

```bash
python3 main.py
```

Run tests:

```bash
python3 -m pytest
python3 -m pytest tests/test_deck_service.py
python3 -m pytest tests/ui/
```

Lint/format checks:

```bash
python3 -m ruff check .
python3 -m black --check .
```

Repo helper scripts:

```bash
./lint_test_commit.sh
./scripts/lint_test_commit_codex.sh
./run_pytest_on_host.sh
```

Architecture helpers:

```bash
python3 scripts/generate_architecture_diagram.py
python3 scripts/generate_dependency_diagram.py
```

Packaging helpers:

```bash
./packaging/build_installer.sh
./packaging/test_installer.sh
```

## Tests And Coverage Areas

The current test suite covers substantially more than the older docs implied. Major areas include:

- services: deck, search, collection, workflow, radar, store
- repositories: deck, metagame, card
- utilities: deck parsing, aliases, card data/image caches, background worker, i18n, diagnostics, math utils, gamelog parser
- widgets/UI logic: deck selector behavior, card box/panel logic
- automation: separate local e2e package for UI command flows and screenshot/golden workflows

Fixtures live under `tests/fixtures/`. UI tests under `tests/ui/` require a display-capable environment.

## Data And External Dependencies

- Python 3.11+
- wxPython on Windows
- MTGGoldfish scraping via `curl_cffi`/BeautifulSoup/lxml
- Scryfall and MTGJSON-style bulk/card data flows for metadata and images
- Optional MongoDB for deck persistence
- Optional MTGOBridge (.NET 9 + MTGOSDK) for MTGO-facing integration

Important dependency files:

- `requirements.txt`
- `requirements-dev.txt`
- `pyproject.toml`

## Useful Files To Start With

- `main.py`
- `controllers/app_controller.py`
- `widgets/app_frame.py`
- `services/deck_workflow_service.py`
- `repositories/metagame_repository.py`
- `repositories/deck_repository.py`
- `repositories/card_repository.py`
- `widgets/identify_opponent.py`
- `widgets/match_history.py`
- `automation/cli.py`
- `utils/constants/__init__.py`

## Notes On Stale Historical References

Older references to modules such as `widgets/deck_selector_wx.py`, `utils/dbq.py`, or a Tkinter-based UI are stale and should not be used as guidance for new work. The active codebase is the wxPython app/controller/services/repositories structure described above.
