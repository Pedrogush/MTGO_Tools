# Contributing

This file is an index, not a guide: every subject below is owned by a file that
is kept current, and the standing rule here is that this page never restates
what it links to — a fifth copy of a rule is how the copies start disagreeing.

## Where the change goes

- **Open the PR against `develop`, not `main`.** Merging to `main` *is* the
  release: [`.github/workflows/release.yml`](.github/workflows/release.yml)
  computes the version, builds and verifies the installer, tags it and
  publishes a GitHub Release.
- **Write conventional-commit subjects**, and put a `Version-Bump: minor`
  trailer on a commit when the work is more than a patch — inference on its own
  never proposes more than one: [`docs/VERSIONING.md`](docs/VERSIONING.md).

## Before you open it

- **Run the suite:** `python scripts/run_tests_fast.py` — non-UI tests across
  the cores, UI tests alongside them ([`tests/README.md`](tests/README.md) §5).
- **It runs on your real data.** Run from source, the app keeps `config/`,
  `cache/` and `logs/` inside the checkout — a linked worktree resolves back to
  the primary one — and saved decks in `~/Documents/mtgo_decks`. So don't start
  the app or a second run alongside it: [`tests/README.md`](tests/README.md) §7.
- **User-facing strings go through `_t(...)`** and exist in both
  `utils/i18n/_en_us/` and `utils/i18n/_pt_br/`; the two key sets are checked by
  [`tests/test_i18n_key_coverage.py`](tests/test_i18n_key_coverage.py).
- **Touch [`README.md`](README.md) and [`README.pt-BR.md`](README.pt-BR.md)
  together** — they are one document in two languages.

The full checklist is
[`.github/pull_request_template.md`](.github/pull_request_template.md).
