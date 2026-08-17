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

## How the number is computed

`scripts/next_version.py` compares a PR against the branch it targets: the base
version is `VERSION` **as it exists on the base branch**, and the bump is the
largest applicable one across the PR's commits (`base..HEAD`):

| Commit | Bump |
| --- | --- |
| `<type>!: …` or a body with `BREAKING CHANGE:` | **major** (`2.0.0`) |
| `feat: …` | **minor** (`1.1.0`) |
| `fix: …` or `perf: …` | **patch** (`1.0.1`) |
| `refactor`, `chore`, `docs`, `test`, `style`, `ci`, merges, … | no release |

Precedence is major > minor > patch. If the PR has nothing release-worthy, the
version is unchanged.

Run it locally (no dependencies beyond git + Python). `--base` points at the
branch a PR targets:

```bash
python scripts/next_version.py current                  # what VERSION currently says
python scripts/next_version.py bump --base origin/main   # major | minor | patch | none
python scripts/next_version.py next --base origin/main   # version this PR should carry
python scripts/next_version.py apply --base origin/main  # write that version into VERSION
```

## CI automation

Work is gated behind PRs and **nothing bot-driven pushes to `main`**. So the
version is decided in the PR, not after merge. `.github/workflows/versioning.yml`
runs on `pull_request` (opened / synchronize / reopened) and:

1. computes the version this PR should carry, relative to its base branch;
2. if a bump is warranted, writes `VERSION` and commits it **onto the PR branch**
   as `chore(version): set VERSION to X.Y.Z`.

It runs **once**: as soon as the branch's `VERSION` differs from the base it is
considered already-bumped, and later runs are no-ops. So the number set when the
PR first earns a bump is the number it keeps as more commits land. Because the
installer build reads `VERSION`, the PR's installer is versioned to match.

> **Optional — CI on the bump commit:** a commit pushed with the default
> `GITHUB_TOKEN` does **not** trigger other workflows, so CI won't re-run on the
> bump commit itself. `main`'s ruleset doesn't require status checks, so this
> doesn't block merging and **no setup is needed**. If you'd like CI to run on
> the bump commit too, set a repo secret **`VERSION_BOT_TOKEN`** = a fine-grained
> PAT with *Contents: read/write* on this repo and the bump push will trigger CI
> normally. The bot only ever pushes to **PR branches**, never to `main`. Fork
> PRs are skipped (their token is read-only).

## Publishing the release

The number is decided in the PR; **merging it is what makes the release real**.
`.github/workflows/release.yml` runs on every push to `main` and asks one
question: does the tag `v<VERSION>` already exist?

- **No** → build the installer from `main`, verify it, create the tag, and
  publish a GitHub Release with `MTGOTools_Setup_v<VERSION>.exe` attached.
- **Yes** → that version already shipped; the run is a no-op.

Using the tag as the guard (rather than watching for changes to `VERSION`) keeps
the workflow **idempotent**: it cannot double-publish, and a release that failed
halfway is retried by pushing again or dispatching the workflow manually. The
check itself runs on a cheap Ubuntu job, so the ~10-minute Windows build only
starts when there is genuinely something to ship.

The tag is created *after* the installer builds and passes `test_installer.ps1`,
so a failed build never leaves a tag behind to clean up.

Release notes are the auto-generated commit changelog, prefixed with install
instructions and the installer's **SHA256**. The installer is not code-signed
yet, so that checksum is the only integrity check a user currently has — Windows
SmartScreen will warn on first run either way.

> **Not yet automated:** in-app update checks ([#142](https://github.com/Pedrogush/MTGO_Tools/issues/142)).
> Users still download and re-run the installer to update.

## What this means for you

Write conventional-commit subjects and the version takes care of itself:

- `feat: add mulligan tracker` → next release is a minor bump.
- `fix: correct wallet totals` → next release is a patch bump.
- `feat!: rewrite deck storage format` (or a `BREAKING CHANGE:` footer) → major bump.

To cut a major deliberately for a milestone (a big redesign), land it behind a
`!`/`BREAKING CHANGE` commit.
