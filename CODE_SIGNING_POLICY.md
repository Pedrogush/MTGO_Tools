# Code Signing Policy

MTGO Tools publishes signed Windows binaries so that users can verify that a
release came from this project and reached them unmodified.

> Free code signing provided by [SignPath.io](https://signpath.io), certificate by
> [SignPath Foundation](https://signpath.org).

## Team roles

MTGO Tools is currently maintained by a single person. The roles below are
defined separately anyway, because they describe distinct responsibilities and
because the project is open to additional maintainers — a contributor taking on
one of these roles does not have to take on all of them.

| Role | Who | Responsibility |
| --- | --- | --- |
| **Author** | <TODO: NAME> (@Pedrogush) | Commit access. May modify the repository directly. |
| **Reviewer** | <TODO: NAME> (@Pedrogush) | Reviews every pull request opened by a non-committer before it is merged. |
| **Approver** | <TODO: NAME> (@Pedrogush) | Approves each individual signing request. No release is signed automatically. |

All people holding any of these roles are required to have multi-factor
authentication enabled on both their GitHub account and their SignPath account.

Contributions from people without commit access arrive as pull requests and are
reviewed before merge. Contributions from AI coding assistants are treated as
proposals from a non-committer regardless of who ran the tool: they are reviewed
and approved by a human maintainer before merge, and are attributed in the commit
history with a `Co-Authored-By` trailer.

## Build and release process

Releases are built and published by an automated pipeline; no binary is built on
a maintainer's workstation and uploaded by hand.

1. The version number is derived from conventional-commit messages by
   `scripts/next_version.py` and written to the repository-root `VERSION` file,
   which is the single source of truth for the app, the installer, and the
   release tag.
2. GitHub Actions (`.github/workflows/release.yml`) builds the application with
   PyInstaller, builds the bundled .NET bridge as a self-contained publish, and
   packages both into a Windows installer with Inno Setup
   (`packaging/installer.iss`).
3. The installer is submitted to SignPath for signing. A human approver
   authorises each signing request individually.
4. The signed installer is published as a GitHub Release together with a
   `.sha256` sidecar containing its SHA-256 digest.

The application's own updater refuses to execute a downloaded installer whose
SHA-256 does not match the published sidecar; there is no verification-optional
path (`services/update_installer.py`).

## Privacy

MTGO Tools does not collect analytics or telemetry, and does not transmit
personal data to the project or to any third party operated by the project.

- **Local diagnostics** are opt-in, anonymised, and written only to a local file
  on the user's machine. They are never uploaded (`utils/diagnostics.py`).
- **Network access** is limited to fetching public data the application
  displays: card data and images, metagame and decklist data, and the GitHub
  Releases API for update checks. These requests carry no user identifier.
- **User data stays local.** Collection data, saved decks, match history, and
  settings are stored on the user's machine and are not sent anywhere.
- **Code signing metadata.** SignPath receives the built artifact and the
  associated build metadata from the CI pipeline. It does not receive user data.

## Reporting a problem

Security or signing concerns can be reported by opening an issue at
<https://github.com/Pedrogush/MTGO_Tools/issues> or by contacting
<TODO: CONTACT EMAIL>.
