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

- Runs automatically on push to any branch (except `main`)
- Takes ~3-5 minutes
- Must pass: linting, formatting, compilation, .NET build
- Advisory: type checking, dependency security

## See Full Docs

📖 [docs/PRE_COMMIT_VALIDATION.md](../docs/PRE_COMMIT_VALIDATION.md)
