# Versioning & releases

The project uses [semantic versioning](https://semver.org) (`MAJOR.MINOR.PATCH`).
The number is computed **after a merge lands on `main`**, from the commits that
have shipped since the last release tag. You never hand-pick it — but you do get
to say, explicitly, when something is more than a patch.

## Single source of truth

The repo-root **`VERSION`** file holds the current released version (e.g. `1.1.6`).
Everything else reads from it, so a bump is a one-line change in one place:

| Consumer | How it reads `VERSION` |
| --- | --- |
| `packaging/installer.iss` | ISPP `FileRead` at compile time (`MyAppVersion`) |
| `packaging/build_installer.{ps1,sh}` | reads `VERSION`, builds `MTGOTools_Setup_v<VERSION>.exe` |
| `packaging/test_installer*.{ps1,sh}`, `test_install_uninstall.ps1` | same filename derivation |
| `pyproject.toml` | `version` is declared `dynamic`; `setup.py` supplies it by reading `VERSION` |
| `utils/constants/app.py` | `APP_VERSION`, bundled into the frozen build by `mtgo_tools.spec` |

The file is written by the release workflow, not by hand and not on a PR branch.

## Why after the merge

The version a change deserves depends on everything that shipped alongside it,
and that set is only final once the merge lands.

The first design decided the number on the PR branch instead, and it went wrong
in three ways that all reached the published release history:

- **It froze.** The bump was computed the first time the bot saw the PR and never
  recomputed, so `feat(updates): tell the user in-app when a newer release exists`
  landed after the bot had already written a patch — and a real feature shipped
  as `1.0.2`.
- **Its base went stale.** The number was pinned against the target branch as it
  was *at the time*. When a stacked PR merged out of order, `main` went
  **backwards** from `1.4.0` to `1.3.3`, and `v1.3.4`/`v1.3.5` were then published
  *after* `v1.4.0` — leaving anyone on 1.4.0 permanently "up to date".
- **It skipped releases.** The release gate only ever looked at `main`'s *current*
  `VERSION`, so back-to-back merges meant `1.0.1`, `1.0.3`, `1.1.0` and `1.2.0`
  were never tagged or built at all.

Computing on `main`, against tags, removes all three: there is one place the
decision is made, its base is the release record itself, and every version `main`
passes through is a version that gets built.

## How the number is computed

`scripts/next_version.py` reads the newest `vX.Y.Z` **tag** as the base and looks
at the commits in `<tag>..HEAD`:

| Signal in the range | Bump |
| --- | --- |
| `Release-As: 2.4.0` | exactly that version, overriding everything below |
| `Version-Bump: major` \| `minor` \| `patch` | that level |
| `<type>!: …` or a body with `BREAKING CHANGE:` | **major** |
| `feat: …`, `fix: …`, `perf: …` | **patch** |
| `refactor`, `chore`, `docs`, `test`, `style`, `ci`, merges, … | no release |

The largest signal in the range wins.

**Inference on its own never proposes more than a patch.** That is deliberate.
Whether ten commits are one feature or ten features is a judgement no commit
parser can make: the UI redesign landed as ten PRs, each carrying honest
`feat(ui):` subjects, and inference turned one feature into three separate minor
bumps (`1.1.0`, `1.2.0`, `1.3.0`). It also turned a branch called
`fix/pile-view-virtual-columns` into `1.4.0`, because one commit inside it said
`feat(pile):`.

So a minor or a major is something you ask for. `Release-As:` and `Version-Bump:`
are git trailers — their own line, in any commit in the range, including the
merge commit:

```
feat(ui): land the full redesign

Ten phases of one redesign, not ten features.

Version-Bump: minor
```

There is deliberately **no suppression marker**. Anything that isn't
`feat`/`fix`/`perf` already produces no release, and a `fix:` that reached `main`
is a fix users should be able to install.

Run it locally (no dependencies beyond git + Python):

```bash
python scripts/next_version.py current   # what VERSION currently says
python scripts/next_version.py base      # the newest release tag's version
python scripts/next_version.py bump      # major | minor | patch | pinned | none
python scripts/next_version.py next      # the version the next release will carry
python scripts/next_version.py apply     # write that version into VERSION
```

`tests/test_next_version.py` pins these rules against throwaway git repos,
including the ten-phase-redesign shape.

## Publishing the release

`.github/workflows/release.yml` runs on every push to `main` and does the whole
job in one place:

1. **Decide** — compute the next version from the newest tag plus the commits
   since it. Nothing release-worthy → the run stops here.
2. **Record** — commit `chore(release): VERSION x.y.z` to `main`, so the file, the
   tag and the installer all agree on one number.
3. **Build** — build the installer from *that exact commit* and verify it with
   `test_installer.ps1`.
4. **Publish** — tag `v<VERSION>` and publish a GitHub Release with
   `MTGOTools_Setup_v<VERSION>.exe` and its `.sha256` sidecar attached.
5. **Prune** — drop superseded releases (see below).

The gate is "does the tag `v<next>` already have a release?", which makes the
whole thing idempotent: it cannot double-publish, and a build that failed *after*
the version was recorded is retried by the next push — the recomputed number is
the same, the file already matches it, and the missing tag is what triggers the
retry. The tag is only ever written once a verified installer exists, so a failed
build leaves nothing behind to clean up.

> **Push access:** `main` requires a pull request, so the `VERSION` commit is
> pushed with a write-scoped **deploy key** (repo secret `RELEASE_SSH_KEY`) that
> the `main` ruleset lists as a bypass actor. A deploy key is scoped to this one
> repository, which is narrower than a personal access token. That push
> re-triggers the workflow, so the first job skips any head commit whose message
> starts with `chore(release):`.

### What a release carries

| Asset | Read by |
| --- | --- |
| `MTGOTools_Setup_v<VERSION>.exe` | the person installing it |
| `MTGOTools_Setup_v<VERSION>.exe.sha256` | the app |

The sidecar holds one line in `sha256sum` format — `<lowercase hex>`, two
spaces, `<filename>`. The **same** digest also appears as prose in the release
notes, and the duplication is deliberate rather than an oversight: the prose is
for a human verifying a 180+ MB unsigned download by hand with `Get-FileHash`,
and the sidecar is for the in-app updater
([#142](https://github.com/Pedrogush/MTGO_Tools/issues/142)), which downloads the
installer and then *executes* it. Something deciding whether to run a binary
needs an integrity check it can parse with certainty; a Markdown body whose
wording is free to change is not one. Both are written from a single
`Get-FileHash` in the workflow, so they cannot drift apart.

The installer also accepts a `/RELAUNCH` switch, which is what lets an update
applied silently put the app back on screen afterwards. See
[`../packaging/README.md`](../packaging/README.md).

## Retention

`scripts/prune_releases.py` keeps the published releases down to what someone
would actually install:

1. **The newest patch of each `MAJOR.MINOR` line.** Nobody wants `1.0.0`
   once `1.0.4` exists; it is the same line with known bugs still in it. Keeping
   the newest patch of *each* line still lets someone stay on an older line
   deliberately — the last build before a redesign, say.
2. **The `x.y.0` of each line** — its first release, kept even once later patches
   supersede it.
3. **At most 10 releases**, newest first, if the number of lines ever grows past
   that.

Rule 2 is the **upgrade-path** rule. Rule 1 on its own made an update impossible
to test end to end: `v1.2.0` was deleted the instant `v1.2.1` published, so the
release you would upgrade *from* never coexisted with the one you would upgrade
*to*, and the in-app updater had nothing to run against. A `.0` is also the
natural baseline of a line — the build before any of its patches — which makes
it the one worth keeping if you are keeping two.

Rules 2 and 3 interact, and 3 wins: the cap is applied last and newest-first, so
a repo with more lines than the cap can still have a `.0` trimmed off the
*oldest* end. That is deliberate — the cap is a hard ceiling on storage, and the
lines it reaches are ones nobody is upgrading from any more.

> Pruning is **not** reversible. GitHub deletes release assets permanently, so a
> `.0` that rule 1 already removed cannot be restored by adding rule 2 — it has
> to be rebuilt from its tag (which is why the tags are never deleted).

Only the **Release** and its assets (the ~180 MB installer and its checksum
sidecar) are deleted. **Tags are never
deleted**: they are the version history, they are the base `next_version.py`
computes from, they cost nothing, and removing one would let a number be quietly
reused.

## Telling the user a release exists

The published release is also what the app itself reads. On startup
`services/update_service.py` asks the GitHub API for the latest release, parses
its `v<VERSION>` tag, and compares it against the running `VERSION` — the same
tag this workflow creates, which is the whole contract between the two.

The check is background-only and best-effort: it never blocks startup, and being
offline, rate-limited, or served an unfamiliar payload all resolve to "no update
info" rather than an error. The answer is cached with a timestamp and refreshed
at most once every `UPDATE_CHECK_INTERVAL_SECONDS` (24 h), including across
restarts, so repeat launches make one request a day. When a newer version does
exist the app says so in the right-hand status-bar field and in a **Help** menu
entry that appears only while the update is pending. The whole thing can be
turned off from **File ▸ Preferences… ▸ Check for updates**.

Because the comparison is numeric, the version history has to stay monotonic —
which is the concrete reason the 1.4.0 regression above mattered rather than
being merely untidy.

## Applying it

Clicking either the status-bar note or that Help-menu entry opens the
updater ([#142](https://github.com/Pedrogush/MTGO_Tools/issues/142)): it
confirms, downloads the installer asset with a progress bar, checks it against
the `.sha256` sidecar published beside it, closes the app, and runs Setup with
`/SILENT /NORESTART /RELAUNCH` — the last of which is what puts the new build
back on screen. A file whose digest does not match the sidecar is deleted and
never executed; there is no verification-optional path.

> Releases that carry no installer/sidecar pair — a hand-made release, or one
> published before the sidecar existed — keep the original behaviour: the same
> click opens the release page in a browser and the user installs it themselves.
> `services.update_installer.can_auto_update` is what picks between the two.

### What this does *not* do

Worth knowing before relying on it, and worth keeping honest as it changes:

- **The installer is not code-signed.** The SHA256 check proves the file matches
  what the release publishes; it proves nothing about who published the release.
  Windows SmartScreen still treats the build as it always has. The checksum is
  fetched over HTTPS from the same host as the installer, so an attacker holding
  that host can replace both — the sidecar closes the corruption and
  wrong-file gaps, not a compromised release.
- **A failed update is never applied halfway.** Every failure path deletes the
  partial download and the running app is untouched, but the recovery is the
  user's: nothing retries on its own, and a repeated failure is a manual install
  from the release page.
- **The relaunch depends on the installer, not the app.** The app exits so its
  files can be replaced, so if `/RELAUNCH` does not fire the user is left with a
  correctly updated build that simply did not reopen. `RelaunchRequested` in
  `packaging/installer.iss` is only exercised by an actual Inno Setup build.
- **`prune_releases.py` deletes old releases and their assets.** An app pinned to
  an old version has nothing to say about that, but nothing in the updater reads
  a pruned release either — it only ever asks for `latest`.

## What this means for you

Write conventional-commit subjects and patches take care of themselves:

- `fix: correct wallet totals` → next release is a patch.
- `feat: add mulligan tracker` → also a patch, unless you say otherwise.
- `feat: add mulligan tracker` + a `Version-Bump: minor` trailer → a minor.
- `feat!: rewrite deck storage format` (or a `BREAKING CHANGE:` footer) → a major.

For work that lands across many PRs, let the steps be patches and put
`Version-Bump: minor` on the one that completes it.
