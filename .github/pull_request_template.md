<!-- Target `develop`, not `main`. Merging to `main` *is* the release: it computes
     the version, builds the installer, tags, and publishes a GitHub Release. -->

## What and why

Closes #

## Release

The version is computed after the merge to `main`, from the commit subjects in the
range, and inference on its own never proposes more than a patch — `docs/VERSIONING.md`.

- [ ] Commit subjects are conventional (`feat:`, `fix:`, `perf:`, `docs:`, …)
- [ ] Bigger than a patch? A commit here carries a `Version-Bump: minor` (or
      `Release-As: X.Y.Z`) trailer — nothing else will produce one

## Checks

- [ ] Tests pass: `python scripts/run_tests_fast.py` (non-UI in parallel, UI serial)
- [ ] The data-isolation guard stayed quiet — no test wrote the real `config/` or
      `cache/`, and `MTGO_TOOLS_ALLOW_CONCURRENT_APP` was not used to get there
      (`tests/README.md` §7)
- [ ] `black` and `ruff` clean
- [ ] New user-facing strings go through `_t(...)` and exist in both
      `utils/i18n/_en_us/` and `_pt_br/`
- [ ] Docs updated where behaviour changed — `README.md` **and** `README.pt-BR.md`,
      `help/`, `docs/`
