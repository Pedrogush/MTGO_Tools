# Attributions

This project incorporates ideas, techniques, and code patterns from various open-source projects and community resources. We gratefully acknowledge the following:

---

## Code Adaptations

### cderickson/MTGO-Tracker

**Repository:** https://github.com/cderickson/MTGO-Tracker

**Author:** Chris Erickson (cderickson)

**License:** None published (no `LICENSE` file in the upstream repo as of
2026-05). Under default copyright this means "all rights reserved" and we
treat the upstream source as **non-reusable**. See
`docs/license_audit.md` for the full audit.

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

**License:** MIT

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

**License:** MIT

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

## Libraries and Dependencies

### Python Libraries

- **BeautifulSoup4** - HTML parsing for MTGGoldfish scraping
- **requests** - HTTP client for web scraping
- **pymongo** - MongoDB driver
- **pytesseract** - OCR for opponent name detection
- **Pillow (PIL)** - Image processing for OCR
- **pyautogui** - Screen capture (read-only)
- **tkinter / wxPython** - GUI frameworks

### .NET Libraries

- **MTGOSDK** (videre-project) - MTGO client interaction
- **System.Text.Json** - JSON serialization
- **Entity Framework Core** (referenced in architecture research)

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
- **MongoDB documentation** - Database usage

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
repo root). We have audited adapted code and dependencies:

- **MTGOSDK** (videre-project): MIT License — compatible.
- **videre-project/Tracker**: MIT License — compatible (architecture
  inspiration only, no source reuse).
- **Python libraries**: All declared deps in `requirements.txt` /
  `requirements-dev.txt` are under OSI-approved permissive licenses
  (MIT, BSD, Apache-2.0, PSF). See `docs/license_audit.md` for the
  per-dependency table.
- **cderickson/MTGO-Tracker**: No published license. Treated as
  non-reusable; only factual observations about the MTGO log format
  were used (see entry above and `docs/license_audit.md`).
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

**Last Updated:** 2026-05-28

**Maintained By:** Pedro (https://github.com/Pedrogush)

If you notice any attributions are missing or incorrect, please let us know!
