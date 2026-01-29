# Attributions

This project incorporates ideas, techniques, and code patterns from various open-source projects and community resources. We gratefully acknowledge the following:

---

## Code Adaptations

### cderickson/MTGO-Tracker

**Repository:** https://github.com/cderickson/MTGO-Tracker

**Author:** Chris Erickson (cderickson)

**License:** Not explicitly stated (assumed open source)

**What we use:**
- GameLog parsing logic from `modo.py`
- Player name extraction patterns
- Match winner determination algorithms
- Log file format understanding

**Files influenced:**
- `utils/gamelog_parser.py` - Core parsing logic adapted from `modo.py`

**Key modifications:**
- Simplified for opponent extraction focus (removed deck analysis, play-by-play tracking)
- Integrated with MTGOSDK for log file location
- Refactored for Python 3.11+ with type hints
- Adapted for MongoDB storage instead of SQLite

**Credit:**
The MTGO log file format is complex and undocumented. Chris Erickson's MTGO-Tracker project provided invaluable insights into parsing these files correctly. The pattern matching logic, player name normalization, and winner detection algorithms are directly adapted from his work.

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
- `utils/mtgo_bridge_client.py` - Bridge client for SDK communication
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
- `navigators/mtggoldfish.py` - Web scraping implementation
- `widgets/deck_selector.py` - Deck browser using scraped data

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

This project is released under [LICENSE NAME TBD]. We have ensured compatibility with all dependencies:

- **MTGOSDK**: MIT License ✅ Compatible
- **Python libraries**: Various OSI-approved licenses ✅ Compatible
- **Adapted code**: Properly attributed and modified ✅ Compliant

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

**Last Updated:** 2025-01-15

**Maintained By:** Pedro (https://github.com/Pedro)

If you notice any attributions are missing or incorrect, please let us know!
