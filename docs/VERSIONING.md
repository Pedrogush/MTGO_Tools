# Versioning & releases

The project uses [semantic versioning](https://semver.org) (`MAJOR.MINOR.PATCH`),
derived automatically from [Conventional Commit](https://www.conventionalcommits.org)
messages. You never hand-pick a version number — it is computed from what landed.

## Single source of truth

The repo-root **`VERSION`** file holds the current released version (e.g. `1.0.0`).
Everything else reads from it, so a bump is a one-line change in one place:

| Consumer | How it reads `VERSION` |
| --- | --- |
| `packaging/installer.iss` | ISPP `FileRead` at compile time (`MyAppVersion`) |
| `packaging/build_installer.{ps1,sh}` | reads `VERSION`, builds `MTGOTools_Setup_v<VERSION>.exe` |
| `packaging/test_installer*.{ps1,sh}`, `test_install_uninstall.ps1` | same filename derivation |
| `pyproject.toml` | `version` is declared `dynamic`; `setup.py` supplies it by reading `VERSION` |

`vX.Y.Z` git tags mark releases and are what the automation diffs against to
decide the next number.

## How the number is computed

`scripts/next_version.py` scans conventional-commit messages since the most
recent `vX.Y.Z` tag and picks the largest applicable bump:

| Commit | Bump |
| --- | --- |
| `<type>!: …` or a body with `BREAKING CHANGE:` | **major** (`2.0.0`) |
| `feat: …` | **minor** (`1.1.0`) |
| `fix: …` or `perf: …` | **patch** (`1.0.1`) |
| `refactor`, `chore`, `docs`, `test`, `style`, `ci`, merges, … | no release |

Precedence is major > minor > patch. If nothing release-worthy landed since the
last tag, the version is unchanged.

Run it locally (no dependencies beyond git + Python):

```bash
python scripts/next_version.py current   # what VERSION currently says
python scripts/next_version.py bump      # major | minor | patch | none
python scripts/next_version.py next      # the version the next release would get
python scripts/next_version.py apply     # write the next version into VERSION
```

## CI automation

`.github/workflows/versioning.yml` runs on every push to `main`. It:

1. ensures a baseline `v<current>` tag exists;
2. computes the next version from the commits since the last tag;
3. if a release is warranted, writes `VERSION`, commits it as
   `chore(release): vX.Y.Z [skip ci]`, and pushes the commit plus a `vX.Y.Z` tag.

Because the installer build reads `VERSION`, the next installer is versioned
automatically — no manual edits.

> **One-time setup:** the job pushes a commit and tag to `main`, so it needs
> `contents: write` (already set in the workflow) **and** permission to push to
> `main`. If `main` has branch protection that blocks direct pushes, allow
> `github-actions[bot]` to bypass it (or change the job to open a PR instead).
> Without that, only the push step fails and the version simply won't advance —
> nothing else breaks. Pushes made with `GITHUB_TOKEN` don't retrigger
> workflows, so the release commit can't cause a loop.

## What this means for you

Write conventional-commit subjects and the version takes care of itself:

- `feat: add mulligan tracker` → next release is a minor bump.
- `fix: correct wallet totals` → next release is a patch bump.
- `feat!: rewrite deck storage format` (or a `BREAKING CHANGE:` footer) → major bump.

To cut a major deliberately for a milestone (a big redesign), land it behind a
`!`/`BREAKING CHANGE` commit.
