# Architecture

MTGO Tools is a wxPython desktop application for Windows that provides metagame research, deck building, opponent tracking, and collection management for Magic: The Gathering Online players.

## Architecture Overview

```mermaid
graph TB
    subgraph "Entry Point"
        MAIN[main.py<br/>MetagameWxApp]
    end

    subgraph "Controllers Layer"
        AC[AppController<br/>Central State & Coordination<br/>package: controllers/app_controller/]
        SM[SessionManager]
    end

    subgraph "UI Layer (wxPython Widgets)"
        AF[AppFrame<br/>Main Window]
        DRP[DeckResearchPanel]
        DBP[DeckBuilderPanel]
        CTP[CardTablePanel]
        CIP[CardInspectorPanel]
        SGP[SideboardGuidePanel]
        RP[RadarPanel]
        ODS[MTGOpponentDeckSpy<br/>Overlay Tracker]
        MH[MatchHistory]
        TA[TimerAlert]
    end

    subgraph "Services Layer"
        DS[DeckService]
        CS[CollectionService]
        SS[SearchService]
        IS[ImageService]
        StS[StoreService]
        RS[RadarService]
        FCPS[FormatCardPoolService]
        DWS[DeckWorkflowService]
        BSC[BundleSnapshotClient]
        MBS[MtgoBridgeService<br/>client + facade]
    end

    subgraph "Repositories Layer"
        CR[CardRepository<br/>+ CardDataManager / MTGJson]
        DR[DeckRepository]
        DTC[DeckTextCache<br/>SQLite]
        MR[MetagameRepository]
        RR[RadarRepository<br/>SQLite]
        FCPR[FormatCardPoolRepository<br/>SQLite]
        MTG_GF[mtggoldfish.py<br/>scraper]
        RSC[RemoteSnapshotClient]
    end

    subgraph "Utilities"
        DECK[deck.py<br/>Deck Parser]
        AIO[atomic_io.py]
        BW[background_worker.py]
        LOG[logging_config.py]
    end

    subgraph "External Bridge"
        BRIDGE[MTGOBridge.exe<br/>.NET 9.0 + MTGOSDK]
    end

    subgraph "External Data Sources"
        SCRYFALL[Scryfall API/CDN]
        MTGJSON[MTGJson Database]
        GOLDFISH[MTGGoldfish]
        MTGO_CLIENT[MTGO Client]
    end

    MAIN --> AC
    AC --> AF
    AC --> SM
    AF --> DRP
    AF --> DBP
    AF --> CTP
    AF --> CIP
    AF --> SGP
    AF --> RP
    AC --> ODS
    AC --> MH
    AC --> TA
    AC --> DS
    AC --> CS
    AC --> SS
    AC --> IS
    AC --> StS
    AC --> RS
    DS --> DR
    DS --> CR
    SS --> CR
    SS --> FCPS
    CS --> CR
    RS --> RR
    FCPS --> FCPR
    DR --> DECK
    CS --> MBS
    MR --> MTG_GF
    MR --> BSC
    MR --> RSC
    MTG_GF --> GOLDFISH
    IS --> SCRYFALL
    CR --> MTGJSON
    MBS --> BRIDGE
    BRIDGE --> MTGO_CLIENT

    classDef controller fill:#ff9999,stroke:#333,stroke-width:2px
    classDef service fill:#99ccff,stroke:#333,stroke-width:2px
    classDef repo fill:#99ff99,stroke:#333,stroke-width:2px
    classDef ui fill:#ffcc99,stroke:#333,stroke-width:2px
    classDef util fill:#cc99ff,stroke:#333,stroke-width:2px
    classDef external fill:#ffff99,stroke:#333,stroke-width:2px

    class AC,SM controller
    class DS,CS,SS,IS,StS,RS,FCPS,DWS,BSC,MBS service
    class CR,DR,DTC,MR,RR,FCPR,MTG_GF,RSC repo
    class AF,DRP,DBP,CTP,CIP,SGP,RP,ODS,MH,TA ui
    class DECK,AIO,BW,LOG util
    class SCRYFALL,MTGJSON,GOLDFISH,MTGO_CLIENT,BRIDGE external
```

## Layer Responsibilities

**Controllers**: Central coordination and state management via `AppController`. The controller is a package (`controllers/app_controller/`) composed of focused mixins (`lifecycle`, `archetypes`, `decks`, `collection`, `bulk_data`, `card_data`, `settings`, `ui_callbacks`) plus a small `SessionManager` for per-run state. Each mixin owns one subsystem to keep the composed controller class lean.

**Services**: Business logic. Image, collection, and deck services are each Python packages whose main class inherits from (or composes) focused mixins/helpers. For example `services/collection_service/` contains `cache`, `parsing`, `ownership`, `deck_analysis`, `stats`, `bridge_refresh`, and `exporter` modules; `services/image_service/` splits into `bulk_data`, `metadata`, `printing_index`, `cache`, and `download_queue`; `services/deck_service/` contains `parser`, `averager`, and `text_builder`. Radar, format card pool, and deck workflow each have their own service. `services/card_rarity_service.py` answers one question -- has this card name ever been printed at common? -- by deriving it from the Scryfall bulk file the image service already caches, because that is the only per-printing rarity source on disk and it is what `services/gamelog_service/formats.py` needs to recognise Pauper (the one MTGO format defined by rarity rather than by a card list, and therefore the one that legality data structurally cannot name). `services/mtgo_bridge_service/` wraps the external CLI bridge: `client` is the subprocess/multiprocessing transport, and the package facade exposes collection/history/trade snapshots and the challenge watcher.

**Repositories**: Data access with caching. `DeckRepository` and `MetagameRepository` use JSON file caches. `RadarRepository`, `FormatCardPoolRepository`, and `DeckTextCache` use SQLite. `CardRepository` is a single package that combines the collection-file repo with `CardDataManager`, owning the MTGJSON AtomicCards download, on-disk index format, and in-memory query API (`builder`, `remote`, `storage`, `schemas`, `card_data_manager`). `repositories/scrapers/` (`mtggoldfish.py`, `mtggoldfish_visual.py`) is the source side of `MetagameRepository` and `DeckTextCache`, and `repositories/remote_snapshot_client/` provides remote-bundle archetype/stats snapshots as a source for `MetagameRepository` — these data sources live under `repositories/` because owning a data source and shaping it into domain records is a repository's job, not a service's.

**UI/Widgets**: wxPython panels in `widgets/panels/`, dialogs in `widgets/dialogs/`, and standalone overlay windows (`MTGOpponentDeckSpy`, `MatchHistory`, `TimerAlert`).

**Utils**: Cross-cutting helpers only — atomic I/O (`atomic_io.py`), deck text parsing (`deck.py`), background workers (`background_worker.py`), logging setup (`logging_config.py`), JSON helpers, perf timers, runtime flags, diagnostics, image effects, math, constants, and i18n. Single-consumer modules have been colocated with their callers: search filter helpers live in `services/search_service/`, image worker entrypoints and Scryfall bulk image downloading in `services/image_service/`, deck-results filtering in `widgets/panels/deck_research_panel/results_filter.py`, wx styling helpers in `widgets/stylize.py`, mana icon rendering in `widgets/mana_icon_factory/`, and small widget-specific helpers inside their respective `widgets/.../` packages. The MTGJSON atomic-cards dataset is owned by `repositories/card_repository/`, gamelog parsing by `services/gamelog_service/`, the deck-text SQLite cache by `repositories/deck_text_cache.py`, the MTGGoldfish scrapers by `repositories/scrapers/`, and the MTGO CLI bridge by `services/mtgo_bridge_service/`.

**External Bridge**: .NET 9.0 application using MTGOSDK to read collection and match data directly from the running MTGO client.

## Composition by Mixin

Most classes here that run past a page are assembled from mixins rather than written out in one file: 162 classes are named `*Mixin`, and 47 classes inherit from three or more bases. The extremes are worth stating plainly rather than hiding. `AppFrame` (`widgets/frames/app_frame/frame/__init__.py`) has **18 bases** — seventeen mixins and `wx.Frame`; `AutomationServer` has 11; `AppController` has 8; `MTGOpponentDeckSpyHandlersMixin` is itself a mixin built from seven more; `CollectionService`, `DeckBuilderPanel`, and `CardImageDisplay` have six each. Read as an inheritance hierarchy that is alarming, and a reader is right to flinch. It is not one: none of the 162 subclasses another to specialise it, none is ever instantiated, and none is used polymorphically — each is a flat namespace of methods that exactly one host class merges into itself. `AppFrame` is a single object carrying the 195 methods its mixins contribute and the 60 attributes its protocol declares, spread across the 4,700 lines of `widgets/frames/app_frame/`. The mixins are units of *navigation*, not units of encapsulation, and everything below follows from that substitution.

The UI layer is where the shape is least optional. A `wx.Frame` subclass has to *be* a frame — the native window is created inside `wx.Frame.__init__`, and every wx API that takes a parent takes a `wx.Window` — so `AppFrame` inherits from `wx.Frame` however its own code is organised, and its handlers have to be reachable as attributes of that same instance. `AppFrame.__init__` binds `self.Bind(wx.EVT_CHAR_HOOK, self._on_hotkey)` against a method defined in `CardShortcutHandlers`; the three column-builder mixins wire thirty callbacks of the form `on_deck_selected=self.on_deck_selected` into child panels while constructing them; the coalescing timers are bound with the frame as owner. None of that is *impossible* under composition — wx will bind `helper.method` quite happily — but it changes what the frame is. Each helper needs a back-reference to the frame it drives, and every such reference can outlive the window, because wx destroys the C++ side on close while the Python objects live until the last reference drops. This app has already paid for that class of bug: `widgets/menu_bar/panel.py` carries the post-mortem of a "wrapped C/C++ object of type Button has been deleted" crash, and `docs/WXMSW_BEHAVIOUR.md` exists because wxMSW's behaviour has repeatedly not been what its documentation says. Keeping the methods on the frame holds the number of objects that can outlive the window at one, so "is this window still alive?" stays a single question instead of one per helper.

Below the widgets there is no wx constraint and the pattern is used anyway, for a weaker but still real reason: a service's mixins share mutable state that has no owner other than the service. `CollectionService`'s six mixins all read and write the same `_collection` dict and `_collection_loaded` flag; `AutomationServer` collects the `_handle_*` methods contributed by all eleven of its mixins into one command-dispatch table. Delegation would give each of those either a back-reference to the service or a fourth object owning the state, in exchange for an encapsulation boundary no caller wants — `collection_service.get_owned_count(...)` is the API that should exist, and `collection_service.ownership.get_owned_count(...)` is not an improvement on it. Where that justification runs out the pattern should stop: `ExporterMixin` (`services/collection_service/exporter.py`) touches no instance state whatsoever and is a class only so that `export_to_file` lands on the service's public surface. That one is file-splitting with a class drawn around it, and it is the shape to avoid copying, not the template.

The `Protocol` classes exist because a mixin's `self` is otherwise untypeable. A mixin references attributes it does not define — `self.controller`, `self.zone_cards`, `self.main_table` — so a type checker reading the module in isolation has nothing to resolve them against. Thirty-one `protocol` modules answer that: `AppFrameProto` in `widgets/frames/app_frame/protocol.py` declares 60 attributes and 15 cross-mixin methods, and `AppControllerProto`, `CollectionServiceProto`, and their siblings do the same for their hosts. Each mixin picks the protocol up with one idiom, which gives the checker a real base while leaving the runtime MRO untouched:

```python
if TYPE_CHECKING:
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object
```

112 of the 162 mixins declare their protocol this way. The protocol module doubles as the only documentation the pattern has of the composed object's shape: it is the one file that answers "what does this thing actually hold?" without reading all seventeen mixins.

The second convention is that **no mixin defines `__init__`** — true of all 162, without exception. `AppFrameHandlersMixin` states the reason in its docstring: kept as a mixin with no `__init__` "so `AppFrame` remains the single source of truth for instance-state initialization". The consequence is that the MRO never has to be reasoned about at construction time. `super().__init__(...)` in `AppFrame` reaches `wx.Frame` and nothing in between; every attribute named in `AppFrameProto` is assigned in exactly one place, the host's constructor, and can be read in order. Cooperative multiple inheritance — the thing that makes MRO genuinely hard to reason about — is simply not in use, and the no-`__init__` rule is what keeps it out.

The costs are real and worth naming precisely, because a reader will find them anyway. Every mixin's methods and every attribute share one flat namespace, so two mixins choosing the same name silently shadow rather than collide, resolved by base order with no warning; across the six largest composites there are currently zero such collisions, but that is a property of the names chosen so far, not something the structure prevents. A reader inside `zone_editing.py` sees `self.main_table` and `self.zone_cards` with nothing in the file to say where either comes from — one is a widget built by `CenterPanelBuilderMixin`, the other a property on `AppFramePropertiesMixin` forwarding to the controller — and the protocol supplies the type but not the owner. There is no enforced contract between a mixin and its host: the `Protocol` base is a static check and only when the mixin remembers to declare it, so the fifty that do not (mostly small handler/properties pairs) are unchecked, and nothing at runtime objects to a mixin composed into a host missing half of what it assumes. A traceback through `AppFrame` names a class whose body is spread over seventeen files. These are the ordinary costs of trading encapsulation for navigability. The trade is deliberate, but it is a trade, not a free win.

The rules for adding one, as the existing code applies them: one subsystem per mixin, in its own module, named for the subsystem; no `__init__` and no state initialisation of any kind, since every attribute is born in the host's constructor; declare the package's `*Proto` as `_Base` under `TYPE_CHECKING` with the idiom above, and add any new shared attribute to that protocol in the same change; prefix method names by subsystem wherever a collision is plausible; and if the new code touches no host state, write a module-level function instead of a mixin. When a host's base list itself becomes hard to read, the established move is a second tier rather than a longer list — `MTGOpponentDeckSpyHandlersMixin` bundles seven subsystem mixins so that the frame it serves keeps a base list of five.

## Data Flow

- **Metagame research**: MTGGoldfish scrape → `MetagameRepository` (JSON cache, stale-while-revalidate) → UI display. Remote bundle snapshots can bypass live scraping.
- **Deck building**: Card search via `SearchService` → `DeckService` parsing → `CardTablePanel` rendering
- **Collection sync**: MTGO Bridge → `MtgoBridgeService` → `CollectionService` → ownership marking across UI
- **Card images**: Scryfall bulk data + CDN → `ImageService` caching → display
- **Radar analysis**: Cached deck lists → `RadarService` aggregation → `RadarRepository` (SQLite) → `RadarPanel`

## Development Environment

The project is **developed from WSL** but the application itself **runs on
Windows**: wxPython, the MTGO Bridge subprocess, the Scryfall image cache layout,
and the packaging/installer pipeline all target Windows. Linting, formatting,
type-checking, and most non-wx tests work in either environment, but the full
pytest suite is intended to run against the Windows-side Python interpreter
(where `wx` is installed) — from WSL this is invoked via the Windows interop
shim (`/init /mnt/c/Windows/System32/cmd.exe /c "pytest ..."`). CI runs the
test job on `windows-latest` and lint/type/security/compile jobs on
`ubuntu-latest`; see `.github/workflows/ci.yml` and
`.github/VALIDATION_QUICKSTART.md`.
