# Attributions

This project incorporates ideas, techniques, and code patterns from various open-source projects and community resources. We gratefully acknowledge the following:

---

## Code Adaptations

### cderickson/MTGO-Tracker

**Repository:** https://github.com/cderickson/MTGO-Tracker

**Author:** Chris Erickson (cderickson)

**License:** None published (no `LICENSE` file in the upstream repo as of
2026-05). Under default copyright this means "all rights reserved" and we
treat the upstream source as **non-reusable**. The per-source verdicts are
collected under [License Compatibility](#license-compatibility) below.

**What we use:**
- Conceptual understanding of the MTGO `GameLog.txt` binary format
  (record separators, `@P` player markers, verb/object grammar of
  action lines). These are factual observations about a third-party
  file format, not copyrightable expression.

**What we do NOT use:**
- No source code, functions, regular expressions, data tables, or
  control flow are copied or translated from `modo.py` or any other
  file in MTGO-Tracker. `services/gamelog_service/parser.py` is an
  independent clean-room Python implementation.

**Files informed (not copied):**
- `services/gamelog_service/parser.py` — independently written from log
  observation; MTGO-Tracker confirmed the format is parseable but no
  code was reused.

**Credit:**
The MTGO log file format is complex and undocumented. Chris Erickson's
MTGO-Tracker project demonstrated that the format could be parsed
programmatically and is gratefully acknowledged as prior art in the
problem space. If the upstream author publishes a license that would
require attribution beyond this note, please open an issue and we will
update accordingly.

---

### videre-project/MTGOSDK

**Repository:** https://github.com/videre-project/MTGOSDK

**Author:** Videre Project

**License:** Apache-2.0 (upstream also ships a `NOTICE` file that must be
preserved when redistributing the SDK or its binaries)

**What we use:**
- MTGOSDK library for MTGO client interaction
- `HistoryManager.GetGameHistoryFiles()` for log file location
- `CollectionManager` for collection export
- `EventManager` for challenge timer tracking
- API documentation and examples

**Files influenced:**
- `dotnet/MTGOBridge/Program.cs` - MTGOSDK integration
- `services/mtgo_bridge_service/client.py` - Bridge client for SDK communication
- `scripts/mtgosdk_repl.py` - REPL for exploring SDK API

**Credit:**
MTGOSDK provides the foundation for interacting with MTGO programmatically. Their comprehensive API and documentation enabled us to build features that would otherwise require complex reverse engineering. Special thanks for maintaining detailed API references and responding to community issues.

**Note on HistoricalMatch.Opponents bug:**
We identified a bug in `HistoricalMatch.Opponents` where string-to-User conversion fails. This led us to adopt the log file parsing approach. We've documented this issue for the maintainers.

---

### videre-project/Tracker

**Repository:** https://github.com/videre-project/Tracker

**Author:** Videre Project

**License:** Apache-2.0

**What we use:**
- Architecture patterns for MTGOSDK integration
- Event-driven match tracking concepts
- Database model structures (inspiration)

**Files influenced:**
- `dotnet/MTGOBridge/Program.cs` - Structure influenced by Tracker's service architecture
- Overall project architecture decisions

**Credit:**
The Tracker application provided excellent examples of how to structure an MTGOSDK-based application. Their approach to real-time event tracking and database persistence informed our design decisions.

---

### Badaro/MTGOArchetypeParser

**Repository:** https://github.com/Badaro/MTGOArchetypeParser

**Author:** Filipe Badaró (Phelps-san)

**License:** MIT. Verified against the upstream text itself, vendored verbatim
at `vendor/mtgo_archetype_parser/LICENSE` ("The MIT License (MIT) / Copyright
© 2025 Filipe Badaró"); GitHub's repository metadata reports the same
(checked 2026-09-24).

**What we use:**
- **No code.** Nothing from this repository is compiled, translated, executed
  or read by this project. It is the reference C# implementation of the
  archetype rules, and we did not port it.

**What we ship:**
- **Nothing.** `vendor/mtgo_archetype_parser/` contains exactly one file — the
  upstream MIT `LICENSE`, fetched into a developer's checkout by
  `scripts/update_vendor_data.py:137-142`. `vendor/` is gitignored and none of
  it is redistributed: neither the frozen build (`packaging/mtgo_tools.spec`)
  nor the installer (`packaging/installer.iss`) copies this directory. Both
  used to; because no code reads it, removing it changed nothing.
- That MIT grant covers **this repository only**. It does not extend to
  `Badaro/MTGOFormatData`, which is a separate repository with separate terms
  — see [Data Sources](#data-sources) below.

**Credit:**
MTGOArchetypeParser defines the archetype-rule format that MTGOFormatData is
written in, and is the prior art for how MTGO decklists get classified.

---

## Libraries and Dependencies

### Python Libraries

Declared in `requirements.txt`, with what each one actually backs:

- **wxPython** - the GUI toolkit; every frame, panel and grid under `widgets/`
- **msgspec** - JSON encode/decode on the hot paths
- **loguru** - application logging
- **requests** / **curl-cffi** - HTTP clients for the scrapers
- **BeautifulSoup4** + **lxml** - HTML parsing for MTGGoldfish scraping
  (`bs4.BeautifulSoup(page.text, "lxml")`, `repositories/scrapers/mtggoldfish.py:93`)
- **dulwich** - Pure-Python Git implementation backing deck version history
- **Pillow (PIL)** + **numpy** - card art and mana-glyph image processing
  (`utils/image_effects.py:7-9`, `widgets/panels/card_table_panel/card_render.py`)
- **pygetwindow** - MTGO window enumeration (`utils/find_opponent_names.py:2`)
- **pythonnet** - CLR bootstrap for the SDK exploration REPL
  (`scripts/mtgosdk_repl.py:10-14`)
- **defusedxml** - hardened XML parsing in the MTGOSDK vendor refresh script
  (`scripts/update_mtgosdk_vendor.py:16`)
- **pyautogui**, **pytesseract**, **pynput** - pinned for screen capture, OCR
  and input handling, but no module in this repository imports them today

### .NET Libraries

- **MTGOSDK** (videre-project) - MTGO client interaction; the only
  `PackageReference` in `dotnet/MTGOBridge/MTGOBridge.csproj`
- **System.Text.Json** - JSON serialization (part of the .NET runtime)

---

## Bundled Assets

### andrewgioia/mana (the Mana symbol font)

**Repository:** https://github.com/andrewgioia/mana — fetched from our pinned
fork `https://github.com/Pedrogush/mana` (`scripts/fetch_mana_assets.py:23-26`)

**Author:** Andrew Gioia

**License:** stated in the upstream `README.md`, which ships inside the asset
tree (`assets/mana/README.md:53-61`, Mana v1.18.0):
- the **font files** are under the **SIL Open Font License 1.1**;
- the **CSS, LESS and Sass** sources are under the **MIT License**
  (`assets/mana/package.json` likewise declares `"license": "MIT"`);
- the symbol artwork itself is stated there to be copyright Wizards of the
  Coast.

The upstream repository publishes no `LICENSE` file (checked 2026-09-24); that
README section is the license statement, and it travels with the assets because
the whole repository is cloned.

**What we use:**
- `fonts/mana.ttf`, `css/mana.min.css` and the `svg/` glyphs
  (`scripts/fetch_mana_assets.py:31-35`), rasterised to transparent PNGs by
  `widgets/mana_icon_factory/svg_renderer.py`.

**Redistribution:**
`assets/mana` is not tracked in git (`.gitignore:15-18`); it is cloned on demand
and then bundled into the frozen build (`packaging/mtgo_tools.spec:35`), so the
Windows installer redistributes the font, the stylesheets and the glyphs.

**Credit:**
Mana is the symbol set nearly every Magic community tool renders with.
Attribution is explicitly "greatly appreciated but not required" upstream; we
are glad to give it.

---

## Data Sources

### MTGGoldfish

**Website:** https://www.mtggoldfish.com/

**What we use:**
- Metagame deck lists
- Tournament results
- Archetype categorization
- Player names and standings

**Usage:**
We scrape MTGGoldfish in compliance with their `robots.txt` file. Our scraping is rate-limited and respects their terms of service. We do not republish or redistribute their data commercially.

**Files influenced:**
- `repositories/scrapers/mtggoldfish.py` - Web scraping implementation
- `widgets/panels/deck_research_panel/` - Deck browser using scraped data

**Credit:**
MTGGoldfish is an invaluable resource for the Magic: The Gathering community. Their metagame data and tournament coverage provide the foundation for competitive deck research. Please support them by visiting their site and considering their premium services.

---

### Badaro/MTGOFormatData

**Repository:** https://github.com/Badaro/MTGOFormatData

**Author:** Filipe Badaró (Phelps-san)

**License:** **None published.** The upstream repository root contains only
`Formats/` and `README.md` — there is no `LICENSE` file, the README states no
terms, and GitHub's repository metadata reports no license (all checked
2026-09-24). As with `cderickson/MTGO-Tracker` above, default copyright means
all rights reserved — and, as with that entry, **we do not redistribute it.**
The installer and the frozen build did ship the tree verbatim until those
entries were removed, precisely because there is no grant to ship it under. It
now exists only in a developer's checkout. Recorded under
[License Compatibility](#license-compatibility).

**Vendored at:** commit `71af3180` (`vendor/vendor_sources.json`), refreshed by
`scripts/update_vendor_data.py`.

**What we ship:**
- **Nothing.** `vendor/mtgo_format_data/` is the upstream `Formats/` tree copied
  verbatim — the per-format `Archetypes/` and `Fallbacks/` rule files,
  `metas.json`, `color_overrides.json` and `card_colors.json` — but `vendor/`
  is gitignored and nothing redistributes it. The frozen build bundled the whole
  tree and the installer wrote it to `{app}/vendor/mtgo_format_data`; both
  entries were removed (`packaging/mtgo_tools.spec`,
  `packaging/installer.iss`), which is where the unlicensed redistribution
  stopped.

**What reads it:**
- Nothing in the application, at present. The only code in this repository that
  names the path is the refresh script itself
  (`scripts/update_vendor_data.py:15`). That is why dropping it from the build
  cost nothing: there was no consumer to break.

**Credit:**
MTGOFormatData is the community's maintained description of MTGO archetypes,
format legality windows and card colors, maintained by Filipe Badaró alongside
MTGOArchetypeParser.

---

## Conceptual Inspiration

### General MTGO Tracking Tools

Several MTGO tracking and analysis tools informed our feature set:

- **17Lands** (https://www.17lands.com/) - Draft analysis concepts
- **MTGATracker** (https://github.com/mtgatracker) - Deck tracking patterns
- **Untapped.gg** - Overlay UI design concepts

While we did not use code from these projects, they demonstrated what features are valuable to the competitive Magic community.

---

## Documentation and Resources

### MTGO Community

- **MTGO Discord servers** - Community support and feature discussions
- **Reddit r/MTGO** - User feedback and bug reports
- **Wizards of the Coast** - MTGO game client (obviously!)

### Technical Resources

- **Stack Overflow** - Various programming solutions
- **Python documentation** - Language reference
- **.NET documentation** - C# and framework references

---

## AI Assistance

This project was developed with assistance from **Claude** (Anthropic), an AI assistant that helped with:
- Code review and debugging
- Architecture decisions
- Documentation writing
- Best practices recommendations

---

## License Compatibility

This project is released under the **MIT License** (see `LICENSE` in the
repo root). Audited below: the adapted code, everything the Windows installer
redistributes, and every dependency declared in `requirements.txt` /
`requirements-dev.txt`. Transitive dependencies are covered only in aggregate,
in the last bullet. This is a record of what was checked and what it said — it
is not legal advice, and the one item marked **open** below is not resolved.

- **MTGOSDK** (videre-project): Apache-2.0 License — compatible one-way
  (our code stays MIT, the SDK stays Apache-2.0). Its `LICENSE` and
  `NOTICE` files must accompany any redistribution of SDK binaries, and the
  installer does redistribute those binaries: `packaging/installer.iss:163`
  ships the whole `dotnet/MTGOBridge` publish output, which is built against
  the SDK, into `{app}\mtgo_integration`.
  The §4(d) `NOTICE` obligation is now **met**: `packaging/installer.iss`
  installs `vendor/mtgosdk/NOTICE` as `{app}\MTGOSDK-NOTICE.txt`, beside this
  project's own `LICENSE` and `README.md`. That `[Files]` entry is deliberately
  unguarded, so a build whose vendor refresh had not run fails to compile
  rather than silently shipping without it. The frozen executable is
  unaffected: it bundles no MTGOSDK binaries — the bridge is a separate .NET
  publish — so §4(d) does not attach to `packaging/mtgo_tools.spec`.
  **Open:** the §4(a) copy of the Apache License text itself is still not
  shipped, because it is not on disk to ship.
  `scripts/update_mtgosdk_vendor.py:59-63` returns after copying the *first* of
  `LICENSE`/`NOTICE` it finds in the NuGet package, and that package root
  contains only `NOTICE` — so the fallback at `:64-78`, which would download
  `LICENSE` from upstream, is never reached. `packaging/installer.iss` already
  carries a `#if FileExists`-guarded entry that ships it as
  `{app}\MTGOSDK-LICENSE.txt` the moment that script is corrected.
- **videre-project/Tracker**: Apache-2.0 License — compatible (architecture
  inspiration only, no source reuse).
- **dulwich**: dual-licensed **Apache-2.0 OR GPL-2.0-or-later** (its
  distribution metadata declares that SPDX expression and its `COPYING`
  file carries both texts). We take the **Apache-2.0** option, which is
  compatible one-way with MIT and asks for the attribution recorded
  above. It is a runtime dependency (`requirements.txt`) and is frozen
  into the Windows build unmodified (`packaging/mtgo_tools.spec` collects
  its submodules), so the installer redistributes it under those terms.
- **wxPython** (`requirements.txt:4`): the **wxWindows Library Licence** — its
  wheel metadata declares `License: wxWindows Library License` and the bundled
  `LICENSE.txt` is the wxWidgets text: the GNU Library General Public Licence
  v2, plus the explicit exception that object code built from the library may
  be distributed under the distributor's own terms with no obligation to
  distribute the library's source. That is not a permissive license, and
  wxPython is the single largest thing PyInstaller freezes into the build, so
  the installer redistributes it under that exception.
- **pynput** (`requirements.txt:12`): **LGPL-3.0** (its wheel metadata declares
  `LGPLv3` and ships `COPYING.LGPL`). It is a declared runtime dependency, but
  no module in this repository imports it, so PyInstaller's analysis never
  reaches it and it is not in the frozen build — it is installed into a
  developer's environment, not redistributed.
- **PyInstaller** (`requirements-dev.txt:11`): **GPL-2.0-or-later with the
  bootloader exception** — verbatim from its own metadata, "GPLv2-or-later with
  a special exception which allows to use PyInstaller to build and distribute
  non-free programs (including commercial ones)". Build-time only: it is not
  imported by the app and not shipped as a library. It is still relevant to
  what we ship, because the frozen `.exe` embeds PyInstaller's bootloader, and
  that exception is what allows the frozen output to be distributed under this
  project's own MIT terms.
- **Other declared Python dependencies**: permissive, read off each installed
  distribution's own metadata — msgspec (BSD-3-Clause), requests (Apache-2.0),
  loguru (MIT), beautifulsoup4 (MIT), curl-cffi (MIT), pygetwindow (BSD),
  defusedxml (PSF), pyautogui (BSD), Pillow (MIT-CMU), pytesseract
  (Apache-2.0), pythonnet (MIT), numpy (BSD-3-Clause AND 0BSD AND MIT AND Zlib
  AND CC0-1.0), lxml (BSD-3-Clause). The remaining `requirements-dev.txt`
  entries are developer tooling that is never redistributed; of those,
  pytest, pytest-randomly, pytest-xdist, ruff, black and mypy were checked and
  are MIT.
- **Transitive dependencies**: the frozen build also contains what the runtime
  dependencies pull in, which this audit does not enumerate package by package.
  Two observations from spot-checking the build environment: `certifi`
  (**MPL-2.0**) is imported unconditionally by `requests`
  (`requests/certs.py`), so it is collected into the frozen build; and the
  GPL-3.0-or-later packages present in the environment — `mouseinfo` and
  `pymsgbox` — arrive only as `pyautogui` dependencies, and since nothing in
  this repository imports `pyautogui`, they are not collected into the build.
- **cderickson/MTGO-Tracker**: No published license. Treated as
  non-reusable; only factual observations about the MTGO log format
  were used (see the entry under Code Adaptations above).
- **Badaro/MTGOArchetypeParser**: MIT — compatible one-way. No code from it is
  used; `vendor/mtgo_archetype_parser/` holds only its `LICENSE`, and nothing
  redistributes that directory — the installer and spec entries that used to
  copy it were removed. Developer checkout only.
- **Badaro/MTGOFormatData**: **no published license** — no `LICENSE` file in
  the upstream repository, no terms in its README, and no license in GitHub's
  repository metadata (re-checked 2026-09-24: the API reports `license: null`
  and the repository root holds only `Formats` and `README.md`). The MIT grant
  on the sibling MTGOArchetypeParser repository does **not** extend to it, so
  there was never a grant to redistribute under. **Resolved by not shipping
  it:** the installer and the frozen build used to copy the whole tree verbatim
  and no longer do (`packaging/installer.iss`, `packaging/mtgo_tools.spec`). No
  module in the app reads it (see the Data Sources entry), so removing it from
  the build cost nothing functionally — which is the only reason this could be
  settled by deletion rather than by obtaining a grant.
  `scripts/update_vendor_data.py` still fetches it into a developer checkout;
  if anything ever starts reading it, an explicit grant from the upstream
  author is required before it can ship again.
- **andrewgioia/mana**: **SIL OFL 1.1** for the font files and **MIT** for the
  CSS/LESS/Sass, per the upstream README that ships with the assets
  (`assets/mana/README.md:53-61`); the symbol artwork is stated there to be
  copyright Wizards of the Coast. The assets are frozen into the build
  (`packaging/mtgo_tools.spec:35`), so the installer redistributes them. The
  OFL requires its license text to accompany the font; `assets/mana` is cloned
  whole, so the README carrying that statement ships alongside the `.ttf`.
- **MTGGoldfish data**: Scraped per `robots.txt`; not redistributed.

---

## How to Contribute Attributions

If you believe we have:
1. Used your work without proper attribution
2. Misrepresented the extent of code reuse
3. Violated any license terms

Please open an issue at [repository URL] and we will address it promptly.

---

## Disclaimer

This project is **not affiliated with or endorsed by:**
- Wizards of the Coast
- Hasbro
- MTGGoldfish
- Any of the attributed projects above

Magic: The Gathering and MTGO are trademarks of Wizards of the Coast LLC.

This is a fan-made tool for personal use and metagame research. We respect all intellectual property rights and terms of service.

---

**Last Updated:** 2026-09-24

**Maintained By:** Pedro (https://github.com/Pedrogush)

If you notice any attributions are missing or incorrect, please let us know!
