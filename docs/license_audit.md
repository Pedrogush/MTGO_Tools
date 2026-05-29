# License & Attribution Audit

**Last reviewed:** 2026-05-28
**Project license:** MIT (see [`LICENSE`](../LICENSE))
**Related issue:** [#471](https://github.com/Pedrogush/MTGO_Tools/issues/471)

This document records the licensing review performed for the public
release of MTGO_Tools. It complements [`ATTRIBUTIONS.md`](../ATTRIBUTIONS.md)
with the per-source verdicts that back the claims made there.

## Scope

The audit covers:

1. Third-party projects called out in `ATTRIBUTIONS.md` as having
   influenced our source code.
2. Declared runtime and dev-time Python dependencies in
   `requirements.txt` / `requirements-dev.txt`.
3. The .NET dependency `MTGOSDK` linked from `dotnet/MTGOBridge/`.

Out of scope:

- Vendored MTGO binary assets (icons, sounds) shipped under `assets/`
  and `sounds/`. These are user-supplied or Wizards-of-the-Coast
  trademarked artwork and are not redistributed publicly; see the
  Disclaimer in `ATTRIBUTIONS.md`.

## Adapted code — verdicts

| Source | Upstream license | Verdict | Notes |
| --- | --- | --- | --- |
| `cderickson/MTGO-Tracker` | **None published** (no `LICENSE` file as of 2026-05) | **Non-reusable code; only format facts retained** | `services/gamelog_service/parser.py` is an independent clean-room Python implementation. No regexes, tables, or control flow are translated from `modo.py`. Only factual observations about the MTGO `GameLog.txt` binary format (a third-party file format) were used, which is not copyrightable expression. |
| `videre-project/MTGOSDK` | MIT | Compatible | Used as a .NET library dependency in `dotnet/MTGOBridge/`. Attribution preserved per MIT terms. |
| `videre-project/Tracker` | MIT | Compatible | Architecture-level inspiration only. No source files reused. |

### Why the MTGO-Tracker entry is safe

The original `ATTRIBUTIONS.md` text said "directly adapted from his
work", which over-claimed the relationship. Reading
`services/gamelog_service/parser.py` against the upstream `modo.py`
confirms:

- Different module layout, naming, and types.
- Different parsing strategy: we split on `@P` markers and use a verb
  whitelist for own-card attribution; the upstream uses pandas
  DataFrames and a different state machine.
- No copied regular expressions, constants, or data tables.

The remaining overlap (knowing that `wins the game`, `mulligans to N
cards`, `chooses to play first`, etc. appear in the log) is factual
information about a third-party file format produced by Wizards of the
Coast's MTGO client. Facts are not copyrightable under U.S. copyright
law (Feist v. Rural), so even with no upstream license, our use is
clear.

We have nonetheless updated `ATTRIBUTIONS.md` to drop the
"directly adapted" wording and explicitly acknowledge the upstream as
prior art rather than as a code source.

## Python dependencies

All declared dependencies use OSI-approved permissive licenses
compatible with MIT redistribution:

| Package | License family |
| --- | --- |
| msgspec | BSD-3-Clause |
| requests | Apache-2.0 |
| loguru | MIT |
| wxPython | wxWindows Library License (LGPL-derived, permits closed-source linking) |
| beautifulsoup4 | MIT |
| curl-cffi | MIT |
| pygetwindow | BSD-3-Clause |
| defusedxml | PSF |
| pyautogui | BSD-3-Clause |
| pillow | MIT-CMU (HPND) |
| pytesseract | Apache-2.0 |
| pynput | LGPL-3.0 (linked at runtime, no static linking) |
| pythonnet | MIT |
| matplotlib | PSF-based (Matplotlib license) |
| numpy | BSD-3-Clause |
| lxml | BSD-3-Clause |
| pytest, pytest-cov | MIT |
| ruff | MIT |
| bandit | Apache-2.0 |
| pyinstaller | GPL-2.0-or-later with PyInstaller runtime exception (permits closed-source bundling) |
| pydeps | BSD-2-Clause |

Notes:

- **wxPython** uses the wxWindows Library License, which is LGPL with
  an explicit exception allowing applications that link against it to
  be distributed under any license. Compatible with MIT distribution.
- **pynput** is LGPL-3.0; we use it as a runtime-imported library
  without modification, which is permitted for any downstream license.
- **PyInstaller** is GPL-2.0 with a runtime exception that explicitly
  carves out the bundled bootloader and packed bytecode from GPL's
  copyleft effect, so packaging an MIT app with PyInstaller does not
  contaminate the app license.

No dependency is flagged as incompatible.

## Stale-path check (acceptance criterion)

All file paths referenced in `ATTRIBUTIONS.md` were re-verified against
the current tree on 2026-05-28:

| Path in `ATTRIBUTIONS.md` | Status |
| --- | --- |
| `services/gamelog_service/parser.py` | exists |
| `services/mtgo_bridge_service/client.py` | exists |
| `scripts/mtgosdk_repl.py` | exists |
| `dotnet/MTGOBridge/Program.cs` | exists |
| `repositories/scrapers/mtggoldfish.py` | exists |
| `widgets/panels/deck_research_panel/` | exists |

No stale paths found.

## Summary

- Repo license is MIT (`LICENSE`), README and `ATTRIBUTIONS.md` now
  agree on this.
- Only one adapted-code source (`cderickson/MTGO-Tracker`) lacks a
  license; we have downgraded our claim to "format facts only" and the
  parser is independently authored, so there is no MIT-incompatible
  reuse.
- All Python and .NET dependencies are under permissive,
  MIT-compatible licenses.
- File paths in `ATTRIBUTIONS.md` match the current tree.
