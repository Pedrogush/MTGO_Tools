# Pre-Commit Validation - Quick Start

## Install Tools

```bash
pip install -r requirements-dev.txt
```

## Run Before Committing

```bash
# Lint and auto-fix
ruff check --fix .

# Format code
black .

# Check security (optional but recommended)
bandit -r . -ll
```

## Common Fixes

### Linting errors
```bash
ruff check --fix .  # Auto-fix most issues
```

### Formatting
```bash
black .  # Auto-format all files
```

### Type errors
```bash
mypy --ignore-missing-imports .  # Advisory only
```

## CI Workflow

Runs on every pull request, on every push to `main` and `develop`, and on
manual dispatch (`.github/workflows/ci.yml`).

- **Must pass**: the two test jobs below, linting (ruff), formatting (black),
  compilation, .NET build, security linting (bandit)
- **Advisory**: type checking (mypy), dependency audit (pip-audit) — reported,
  not blocking

The suite runs as two jobs so every test runs exactly once:

- **Tests (non-UI, parallel)** — everything outside `tests/ui/`, spread across
  the runner's cores with `pytest-xdist` (`pytest -n auto`)
- **Tests (UI, serial)** — the wx tests, which build real top-level windows and
  have to run one at a time in one process (`pytest tests/ui`)

A third job, **Live Network Tests**, hits real external services and only runs
on manual dispatch, so flaky third parties never block a PR.

## See Also

- [`README.md`](../README.md#development) — running the suite locally, the
  fast split runner, and what each tool is for
- [`.github/workflows/ci.yml`](workflows/ci.yml) — the jobs themselves
