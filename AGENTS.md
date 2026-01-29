# Repository Guidelines

## Project Structure & Module Organization
- Entry: `main.py` launches the wxPython UI via `controllers/app_controller.py`.
- UI: `widgets/` (panels, dialogs, handlers) plus `sounds/` for assets.
- Business logic: `services/` and `repositories/` for deck, collection, search, image, and metagame flows.
- Utilities: `utils/` (constants, card data/images, deck parsing, search filters, background workers).
- Integrations: `navigators/` (MTGGoldfish + MTGO decklists scrapers) and `dotnet/MTGOBridge/` (.NET bridge).
- Tests: `tests/` plus `tests/ui/` for wx UI coverage; fixtures in `tests/fixtures/`.

## Build, Test, and Development Commands
- `python3 main.py` – run the desktop app (Windows primary target).
- `python3 -m pytest` or `python3 -m pytest tests/<file>.py` – run unit tests; UI tests require a display/Windows.
- `./lint_test_commit.sh` – black + ruff + pytest on host (uses `run_pytest_on_host.sh` to execute on configured Windows box).
- `python3 -m ruff check .` and `python3 -m black --check .` – lint/format checks individually.
- CI: GitHub Actions workflows `ci.yml` (PR/main) and `pre-commit.yml` (non-main pushes).

## Coding Style & Naming Conventions
- Python 3.11+, black (line length 100) and ruff enforced in CI; prefer type hints where practical.
- Use snake_case for functions/vars, PascalCase for classes, UPPER_SNAKE_CASE for constants.
- Keep UI logic thin; push business rules into services/controllers per `ARCHITECTURE.md`.
- Avoid import-time side effects; call `utils.constants.ensure_base_dirs()` from bootstrap if paths are needed.

## Testing Guidelines
- Framework: pytest. Add fixtures under `tests/fixtures/`; mock network/bridge I/O.
- Name tests `test_*.py`; include regression cases for scrapers and card data refresh (see `tests/test_card_data_refresh.py`).
- For UI tests, use helpers in `tests/ui/conftest.py` (`pump_ui_events`, `deck_selector_factory`).
- Keep tests offline-safe; record or stub network responses.

## Commit & Pull Request Guidelines
- Commit messages are concise, present-tense summaries (e.g., “Simplify CI triggers and harden card data refresh”).
- For PRs: describe scope, testing (`python3 -m pytest ...`), and any UI-impacting changes; link issues when applicable.
- Avoid force-push on shared branches; prefer small, reviewable changes.
- When a PR is created or updated, poll PR checks about once per minute; stop only after all checks pass or after 3 polls with no status changes.

## Agent Workflow
- Start new tasks by checking out `main`, pulling from remote, then creating a new branch for the work.
- Each turn in a conversation should either commit work to the remote branch or ask clarifying follow-up questions to improve instructions.
- Always run `python3 -m ruff check .` and `python3 -m black --check .` before opening pull requests.
- Completing a task should culminate in raising a pull request targeting `main`.
- Agents operate with Full Approval settings and run from a Linux VM inside a host machine.

## Security & Configuration Tips
- Secrets live outside the repo; do not commit host-specific configs (`pytest_host.conf.example` documents required vars).
- MTGO bridge path can be overridden via `MTGO_BRIDGE_PATH`; avoid hardcoding local paths in code or tests.
