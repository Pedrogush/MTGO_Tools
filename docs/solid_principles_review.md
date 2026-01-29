# SOLID Principles Review - MTGO Tools

## Executive Summary

This codebase demonstrates a **generally good architectural foundation** with clear separation of concerns via the Controller → Service → Repository pattern. The recent refactoring effort has significantly improved maintainability by extracting business logic from UI code and creating well-defined layers.

**Overall Grade: B+ (Good, with room for optimization)**

**Key Strengths:**
- Clear layered architecture (Controllers, Services, Repositories, Widgets)
- Dependency injection throughout most of the codebase
- Repository pattern properly isolates data access
- Good use of singleton pattern with factory functions
- Atomic I/O utilities prevent race conditions
- Background worker abstraction for threading

**Key Weaknesses:**
- Some violations of Single Responsibility Principle (SRP) in controller and large widget classes
- Missing interface abstractions (LSP/DIP violations)
- Global state via singleton pattern creates hidden dependencies
- Some god classes and methods that do too much
- Tight coupling between some layers

---

## 1. Controllers Layer

### `controllers/app_controller.py`

**Severity: MEDIUM**

#### Single Responsibility Principle (SRP) - VIOLATION

**Issue:** The `AppController` class has multiple responsibilities:
- Session management
- Archetype/deck fetching orchestration
- Collection management
- Bulk data coordination
- MTGO bridge status checking
- Settings persistence
- UI callback registration
- Frame factory

**Lines 52-554:** The class handles 10+ distinct concerns.

**Impact:** Changes to any of these subsystems require modifying this central class, creating a bottleneck for maintenance and testing.

**Recommendation:**
```python
# Split into focused controllers:
class ArchetypeController:
    """Handles archetype fetching and caching"""

class DeckController:
    """Handles deck operations (download, save, average)"""

class CollectionController:
    """Handles collection loading and MTGO bridge"""

class SessionController:
    """Handles settings and session persistence"""

# AppController becomes a facade/coordinator:
class AppController:
    def __init__(self):
        self.archetype_ctrl = ArchetypeController(...)
        self.deck_ctrl = DeckController(...)
        self.collection_ctrl = CollectionController(...)
        self.session_ctrl = SessionController(...)
```

#### Dependency Inversion Principle (DIP) - VIOLATION

**Issue:** AppController directly instantiates concrete implementations:

**Lines 71-78:**
```python
self.deck_repo = deck_repo or get_deck_repository()
self.metagame_repo = metagame_repo or get_metagame_repository()
# ... etc
```

While this allows dependency injection, the controller still has hard dependencies on concrete classes via the `get_*` factory functions.

**Recommendation:**
Define interfaces (Protocol classes) for repositories:

```python
from typing import Protocol

class DeckRepositoryProtocol(Protocol):
    def get_decks(self, format_type: str) -> list[dict]: ...
    def save_to_db(self, deck_name: str, ...) -> Any: ...

class AppController:
    def __init__(
        self,
        deck_repo: DeckRepositoryProtocol,  # Interface, not concrete
        metagame_repo: MetagameRepositoryProtocol,
        ...
    ):
        self.deck_repo = deck_repo
```

#### Open/Closed Principle (OCP) - PARTIAL VIOLATION

**Issue:** Adding new data sources requires modifying the controller.

**Lines 426-437:** The `get_deck_data_source()` / `set_deck_data_source()` logic is hardcoded for specific sources ("mtggoldfish", "mtgo", "both").

**Recommendation:**
Use a strategy pattern for data sources:

```python
class DeckDataSource(Protocol):
    def fetch_deck(self, deck_id: str) -> str: ...

class MTGGoldfishSource:
    def fetch_deck(self, deck_id: str) -> str: ...

class MTGOSource:
    def fetch_deck(self, deck_id: str) -> str: ...

class CombinedSource:
    def __init__(self, sources: list[DeckDataSource]):
        self.sources = sources
```

---

### `controllers/session_manager.py`

**Severity: LOW**

**Well-designed class** with focused responsibilities.

**Positive Patterns:**
- Single Responsibility: Only handles session persistence and restoration
- Good use of atomic I/O for thread-safe writes
- Clear separation from business logic

**Minor Suggestions:**
- Lines 34-35: Loading both `settings` and `config` files creates some confusion. Consider consolidating or clarifying the distinction.

---

### `controllers/app_controller_helpers.py`

**Severity: LOW**

**Good separation of UI callback wiring from controller logic.**

**Positive Patterns:**
- Helper class properly separates UI threading concerns
- Uses `wx.CallAfter` appropriately for thread safety

---

### `controllers/bulk_data_helpers.py`

**Severity: LOW**

**Well-focused helper class for bulk data orchestration.**

**Positive Patterns:**
- Single Responsibility: Only coordinates bulk data flows
- Proper use of callbacks for async operations
- Good error handling

---

### `controllers/mtgo_background_helpers.py`

**Severity: LOW**

**Clean separation of MTGO background task coordination.**

**Positive Patterns:**
- Focused on background task lifecycle
- Proper shutdown handling
- Good failure tracking with consecutive failure counter

---

## 2. Services Layer

### `services/deck_service.py`

**Severity: LOW**

**Excellent service design** following SRP and DIP.

**Positive Patterns:**
- Delegates to specialized sub-services (DeckParser, DeckAverager, DeckTextBuilder)
- Clear dependency injection in constructor
- Focused methods with single responsibilities
- Good use of dataclasses for return types (ZoneUpdateResult)

**Lines 39-62:** Proper dependency injection with sensible defaults.

---

### `services/deck_workflow_service.py`

**Severity: LOW**

**Clean workflow coordination service.**

**Positive Patterns:**
- Focused on orchestrating deck workflows
- Good use of dependency injection with default providers
- Separates business logic from UI concerns

**Lines 22-30:** Excellent pattern of accepting callables for testability:
```python
def __init__(
    self,
    *,
    archetype_provider: Callable[..., list[dict]] | None = None,
    deck_downloader: Callable[[str, str | None], None] | None = None,
):
    self._archetype_provider = archetype_provider or self._default_archetype_provider
```

---

### `services/image_service.py`

**Severity: MEDIUM**

#### Single Responsibility Principle (SRP) - VIOLATION

**Issue:** ImageService handles multiple concerns:
- Bulk data existence checking
- Bulk data downloading
- Printing index loading
- State management (loading flags)
- Workflow coordination

**Lines 25-306:** The class mixes data operations with workflow orchestration.

**Recommendation:**
```python
# Split responsibilities:
class BulkDataChecker:
    def check_exists(self) -> tuple[bool, str]: ...
    def check_freshness(self, max_age_days: int) -> tuple[bool, str]: ...

class BulkDataLoader:
    def load_printing_index(self) -> dict: ...

class BulkDataDownloader:
    def download_metadata(self, force: bool) -> tuple[bool, str]: ...

# ImageService becomes a facade:
class ImageService:
    def __init__(
        self,
        checker: BulkDataChecker,
        loader: BulkDataLoader,
        downloader: BulkDataDownloader,
    ):
        self.checker = checker
        self.loader = loader
        self.downloader = downloader
```

#### Missing Abstraction

**Lines 80-145:** The `ensure_data_ready` method has too many parameters (11 parameters) and complex conditional logic. This is a code smell indicating missing abstractions.

**Recommendation:**
Create a configuration object:
```python
@dataclass
class BulkDataConfig:
    force_cached: bool
    max_age_days: int
    on_load_success: Callable
    on_load_error: Callable
    on_download_success: Callable
    on_download_error: Callable
    on_check_failed: Callable
    set_status: Callable

def ensure_data_ready(self, config: BulkDataConfig) -> None:
    ...
```

---

### `services/collection_service.py`

**Severity: LOW**

**Well-structured service with clear responsibilities.**

**Positive Patterns:**
- Delegates to specialized helper modules
- Good separation of concerns
- Uses dataclasses for return types (CollectionStatus)

---

### `services/store_service.py`

**Severity: LOW**

**Perfect example of SRP** - only handles JSON store persistence.

**Positive Patterns:**
- Single responsibility: JSON store operations
- Atomic writes via `atomic_write_json`
- Simple, focused API

---

### `services/state_service.py`

**Severity: LOW**

**Clean state persistence service.**

**Positive Patterns:**
- Focused on settings load/save
- Static helper methods for data transformation
- Atomic writes for thread safety

---

## 3. Repositories Layer

### `repositories/deck_repository.py`

**Severity: MEDIUM**

#### Single Responsibility Principle (SRP) - VIOLATION

**Issue:** DeckRepository has multiple responsibilities:
- MongoDB operations (lines 63-235)
- File system operations (lines 237-318)
- JSON store operations (notes, outboard, guides) (lines 320-395)
- UI state management (lines 396-508)

**Impact:** This class is too large (552 lines) and mixes data persistence with UI state management.

**Recommendation:**
```python
# Split into focused repositories:
class DeckDatabaseRepository:
    """Handles MongoDB operations only"""
    def save_to_db(self, ...): ...
    def get_decks(self, ...): ...
    def delete_from_db(self, ...): ...

class DeckFileRepository:
    """Handles file system operations"""
    def save_deck_to_file(self, ...): ...
    def list_deck_files(self, ...): ...

class DeckMetadataRepository:
    """Handles notes, guides, outboard"""
    def load_notes(self, ...): ...
    def save_notes(self, ...): ...

class DeckStateManager:
    """UI state - should be in a service layer, not repository"""
    def get_current_deck(self): ...
    def set_current_deck(self, ...): ...
```

#### Interface Segregation Principle (ISP) - VIOLATION

**Issue:** Clients that only need database operations are forced to depend on file operations and state management methods.

**Lines 398-508:** UI state management methods should not be in a repository.

**Recommendation:**
Split into smaller, focused interfaces or separate the state management into a dedicated service.

---

### `repositories/card_repository.py`

**Severity: LOW-MEDIUM**

#### Single Responsibility Principle (SRP) - PARTIAL VIOLATION

**Issue:** Mixes card metadata operations with collection loading.

**Lines 237-316:** Collection loading logic (`load_collection_from_file`) belongs in CollectionRepository or CollectionService.

**Recommendation:**
Move collection operations to CollectionRepository:
```python
class CollectionRepository:
    def load_collection_from_file(self, filepath: Path) -> list[dict]: ...

class CardRepository:
    # Only card metadata operations
    def get_card_metadata(self, name: str) -> dict | None: ...
    def search_cards(self, ...) -> list[dict]: ...
```

**Positive Patterns:**
- Good property pattern for lazy initialization (lines 43-48)
- Clean separation of bulk data operations

---

### `repositories/metagame_repository.py`

**Severity: LOW**

**Well-designed repository with good caching strategy.**

**Positive Patterns:**
- Clear separation of archetype vs deck operations
- Good cache management with TTL
- Proper error handling with stale cache fallback
- Private helper methods for internal operations

**Lines 330-399:** Excellent helper methods for filtering and merging data sources.

---

## 4. Utils Layer

### `utils/atomic_io.py`

**Severity: LOW**

**Excellent atomic file operations implementation.**

**Positive Patterns:**
- Thread-safe path locking with global registry
- Atomic write-replace pattern
- fsync for durability
- Clean, focused API

**Lines 14-36:** Smart lock registry pattern prevents deadlocks.

---

### `utils/background_worker.py`

**Severity: LOW**

**Well-designed background task executor.**

**Positive Patterns:**
- Clean thread lifecycle management
- Graceful shutdown with timeout
- Automatic UI thread marshaling (wx.CallAfter)
- Context manager support

---

### `utils/card_data.py`

**Severity: LOW**

**Clean data manager with focused responsibilities.**

**Positive Patterns:**
- Single Responsibility: Card data loading and querying
- Lazy loading pattern
- Good caching strategy with metadata comparison

---

## 5. Widgets Layer

### `widgets/app_frame.py`

**Severity: HIGH**

#### Single Responsibility Principle (SRP) - MAJOR VIOLATION

**Issue:** AppFrame is a **god class** with too many responsibilities:
- UI construction (panels, toolbar, inspector, etc.)
- Event handling (hotkeys, window events, etc.)
- Deck operations coordination
- State restoration
- Dialog management (opponent tracker, timer, history, etc.)
- Card inspector management
- Sideboard guide coordination

**Lines 49-300+:** The class is massive and handles dozens of different concerns.

**Impact:**
- Difficult to test
- High coupling
- Changes to any feature require modifying this central class
- Violates SRP severely

**Recommendation:**

This is the **biggest refactoring opportunity** in the codebase. Split into:

```python
# 1. UI Builder (construction only)
class AppFrameBuilder:
    def build_toolbar(self, parent) -> ToolbarButtons: ...
    def build_left_panel(self, parent) -> wx.Panel: ...
    def build_right_panel(self, parent) -> wx.Panel: ...

# 2. Event Coordinator (event handling only)
class AppFrameEventCoordinator:
    def on_format_changed(self, format: str): ...
    def on_archetype_selected(self, archetype: dict): ...
    def on_deck_selected(self, event): ...

# 3. Dialog Manager (dialog lifecycle)
class DialogManager:
    def open_opponent_tracker(self): ...
    def open_timer_alert(self): ...
    def open_match_history(self): ...

# 4. AppFrame becomes thin coordinator:
class AppFrame(wx.Frame):
    def __init__(self, controller: AppController):
        self.controller = controller
        self.builder = AppFrameBuilder()
        self.event_coordinator = AppFrameEventCoordinator(controller)
        self.dialog_manager = DialogManager()
        self._build_ui()
```

#### Law of Demeter - VIOLATION

**Example:** The frame reaches through multiple layers:

```python
# Line 287:
card_manager=self.controller.card_repo.get_card_manager()

# Line 293:
self.image_cache = self.controller.image_service.image_cache
```

**Recommendation:**
Add facade methods to controller:
```python
# In AppController:
def get_card_manager(self) -> CardDataManager:
    return self.card_repo.get_card_manager()

def get_image_cache(self) -> ImageCache:
    return self.image_service.image_cache
```

---

## 6. Global Singleton Pattern

**Severity: MEDIUM**

**Issue:** Heavy use of global singleton pattern via factory functions:

**Examples:**
- `get_deck_selector_controller()` (app_controller.py:544)
- `get_deck_service()` (deck_service.py:307)
- `get_deck_repository()` (deck_repository.py:535)
- `get_card_repository()` (card_repository.py:381)
- `get_metagame_repository()` (metagame_repository.py:416)
- `get_image_service()` (image_service.py:289)
- `get_store_service()` (store_service.py:56)

**Problems:**
1. **Hidden Dependencies:** Modules can call `get_*()` anywhere, creating hidden coupling
2. **Testing Difficulties:** Global state can leak between tests
3. **Concurrency Issues:** Singleton pattern assumes single-threaded access (though this app is mostly single-threaded)

**Positive:** Each singleton has a `reset_*()` function for testing (good practice).

**Recommendation:**

Consider dependency injection container pattern:

```python
class ServiceContainer:
    """Centralized service registry with explicit lifecycle"""
    def __init__(self):
        self._services: dict[type, Any] = {}

    def register(self, interface: type, implementation: Any):
        self._services[interface] = implementation

    def get(self, interface: type) -> Any:
        return self._services[interface]

# In main.py:
container = ServiceContainer()
container.register(DeckRepository, DeckRepository())
container.register(CardRepository, CardRepository())
# ...

# Pass container to controllers:
controller = AppController(
    deck_repo=container.get(DeckRepository),
    card_repo=container.get(CardRepository),
)
```

---

## 7. DRY Violations

### Duplicate Deck Download Logic

**Locations:**
- `deck_workflow_service.py:51` - `download_deck_text()`
- `metagame_repository.py:166` - `download_deck_content()`
- `navigators/mtggoldfish.py` - `download_deck()`, `fetch_deck_text()`

**Issue:** Multiple places handle deck downloading with similar logic.

**Recommendation:**
Centralize in a single service method that all others delegate to.

---

### Duplicate Cache TTL Checking

**Locations:**
- `metagame_repository.py:198-238` - `_load_cached_archetypes()`
- `metagame_repository.py:264-303` - `_load_cached_decks()`

**Issue:** Same TTL checking logic duplicated.

**Recommendation:**
Extract a generic cache helper:
```python
class CacheHelper:
    def load_with_ttl(
        self,
        cache_file: Path,
        key: str,
        max_age: int | None,
    ) -> dict | None:
        # Shared TTL logic
```

---

## 8. Missing Abstractions

### Protocol/Interface Classes

**Issue:** No explicit interface definitions for repositories or services.

**Impact:**
- Cannot easily swap implementations
- Violates DIP (Dependency Inversion Principle)
- Harder to mock for testing

**Recommendation:**

Define protocols for all major abstractions:

```python
# repositories/protocols.py
from typing import Protocol

class DeckRepositoryProtocol(Protocol):
    def save_to_db(self, deck_name: str, ...) -> Any: ...
    def get_decks(self, format_type: str, ...) -> list[dict]: ...
    def load_from_db(self, deck_id: str) -> dict | None: ...

class CardRepositoryProtocol(Protocol):
    def get_card_metadata(self, name: str) -> dict | None: ...
    def search_cards(self, query: str, ...) -> list[dict]: ...

class MetagameRepositoryProtocol(Protocol):
    def get_archetypes_for_format(self, format: str) -> list[dict]: ...
    def get_decks_for_archetype(self, archetype: dict) -> list[dict]: ...
```

Then use protocols in type hints:

```python
class AppController:
    def __init__(
        self,
        deck_repo: DeckRepositoryProtocol,  # Protocol, not concrete class
        card_repo: CardRepositoryProtocol,
        ...
    ):
        ...
```

---

## 9. Positive Patterns Worth Highlighting

### Repository Pattern

The codebase properly separates data access into repositories:
- `DeckRepository` - Database and file operations
- `CardRepository` - Card metadata access
- `MetagameRepository` - Metagame data fetching

This is **excellent** and makes the codebase testable and maintainable.

### Service Layer

Business logic is properly extracted into services:
- `DeckService` - Deck operations
- `CollectionService` - Collection management
- `ImageService` - Image/bulk data operations

### Dependency Injection

Most classes accept dependencies via constructor parameters with sensible defaults:

```python
def __init__(
    self,
    deck_repo: DeckRepository | None = None,
    metagame_repo: MetagameRepository | None = None,
):
    self.deck_repo = deck_repo or get_deck_repository()
```

This allows both default usage and test injection.

### Atomic I/O

The `atomic_io.py` module provides excellent race-condition prevention:
- Thread-safe file locking
- Atomic write-replace pattern
- Directory fsync for durability

### Background Worker

Clean abstraction for threading with proper lifecycle management and UI marshaling.

### Dataclasses for Return Types

Good use of dataclasses for structured returns:
- `ZoneUpdateResult` (deck_service.py:31)
- `CollectionStatus` (collection_service.py:37)

---

## 10. Critical Refactoring Priorities

### Priority 1: CRITICAL - Split AppFrame (God Class)

**File:** `widgets/app_frame.py`

**Action:** Break into 4-5 smaller classes as outlined in section 5.

**Benefit:**
- Massively improves testability
- Reduces coupling
- Makes UI changes safer and easier

### Priority 2: HIGH - Split AppController

**File:** `controllers/app_controller.py`

**Action:** Extract specialized controllers as outlined in section 1.

**Benefit:**
- Clearer separation of concerns
- Easier to test individual subsystems
- Reduces bottleneck for changes

### Priority 3: HIGH - Split DeckRepository

**File:** `repositories/deck_repository.py`

**Action:** Separate database, file, metadata, and state management into distinct classes.

**Benefit:**
- Repository pattern becomes clearer
- Easier to test database vs file operations separately
- UI state management moves to appropriate layer

### Priority 4: MEDIUM - Add Protocol Interfaces

**Files:** All repositories and services

**Action:** Define Protocol classes for all major abstractions.

**Benefit:**
- Enables proper dependency inversion
- Makes testing easier (mocking)
- Documents contracts explicitly

### Priority 5: MEDIUM - Reduce Singleton Usage

**Files:** All `get_*()` factory functions

**Action:** Introduce dependency injection container.

**Benefit:**
- Eliminates hidden dependencies
- Improves testability
- Makes lifecycle management explicit

---

## 11. Code Metrics Summary

| Module | Lines | Classes | Methods/Functions | Complexity |
|--------|-------|---------|-------------------|------------|
| app_controller.py | 554 | 1 | 35 | HIGH |
| app_frame.py | 300+ | 1 | 40+ | VERY HIGH |
| deck_repository.py | 552 | 1 | 40 | HIGH |
| deck_service.py | 332 | 2 | 16 | MEDIUM |
| metagame_repository.py | 433 | 1 | 14 | MEDIUM |
| card_repository.py | 398 | 1 | 22 | MEDIUM |
| image_service.py | 306 | 1 | 16 | MEDIUM |

**God Classes Identified:**
1. `AppFrame` (widgets/app_frame.py) - CRITICAL
2. `AppController` (controllers/app_controller.py) - HIGH
3. `DeckRepository` (repositories/deck_repository.py) - HIGH

---

## 12. Testability Assessment

### High Testability

- `StoreService` - Pure functions, no side effects
- `StateService` - Minimal dependencies
- `BackgroundWorker` - Clean abstraction
- `atomic_io` - Pure utility functions
- `DeckService` - Good dependency injection
- `SessionManager` - Focused responsibilities

### Medium Testability

- `DeckRepository` - Too many responsibilities, but DI allows mocking
- `CardRepository` - Some global state access
- `MetagameRepository` - Network dependencies (can be injected)
- `ImageService` - Some complex orchestration logic

### Low Testability

- `AppController` - Too many dependencies, hard to isolate
- `AppFrame` - Massive class with tight wx coupling
- `BulkDataHelpers` - Complex callback orchestration
- `MtgoBackgroundHelpers` - Thread lifecycle complexity

---

## 13. Thread Safety Assessment

### Thread-Safe

- `atomic_io.py` - Excellent path-based locking
- `BackgroundWorker` - Proper thread lifecycle
- All uses of `wx.CallAfter` for UI marshaling
- Session/state persistence (uses atomic_write_json)

### Potential Issues

- `AppController._loading_lock` (line 105) - Good! Prevents race conditions on loading flags
- Singleton pattern - No explicit threading protection, but Python GIL provides some safety
- `ImageService._bulk_check_worker_active` (line 34) - Should use threading.Lock for flag updates

**Recommendation:**
Add explicit locks for flag modifications:
```python
class ImageService:
    def __init__(self):
        self._bulk_check_lock = threading.Lock()
        self._bulk_check_worker_active = False

    def check_bulk_data_exists(self):
        with self._bulk_check_lock:
            if self._bulk_check_worker_active:
                return
            self._bulk_check_worker_active = True
```

---

## 14. Error Handling Assessment

### Good Patterns

- Consistent use of try/except with logger.error() throughout
- Graceful degradation (stale cache fallback in metagame_repository.py)
- Atomic writes prevent partial file corruption

### Areas for Improvement

- Some bare `Exception` catches could be more specific
- Missing custom exception types for domain-specific errors
- Some error messages could include more context

**Recommendation:**
Define domain exception hierarchy:
```python
# exceptions.py
class MTGOToolsError(Exception):
    """Base exception for all MTGO tools errors"""

class DeckNotFoundError(MTGOToolsError):
    """Deck could not be found or loaded"""

class CollectionLoadError(MTGOToolsError):
    """Collection data could not be loaded"""

class CardDataError(MTGOToolsError):
    """Card database operations failed"""
```

---

## 15. Recommended Next Steps

### Immediate (Next Sprint)

1. **Add Protocol interfaces** for repositories and services
2. **Extract DialogManager** from AppFrame
3. **Add thread locks** to flag modifications in ImageService
4. **Document** the layered architecture in ARCHITECTURE.md

### Short-term (1-2 Months)

1. **Refactor AppFrame** into 4-5 smaller classes
2. **Split AppController** into specialized controllers
3. **Separate DeckRepository** concerns
4. **Add custom exception types**

### Long-term (3-6 Months)

1. **Introduce dependency injection container**
2. **Reduce singleton usage**
3. **Add comprehensive integration tests**
4. **Create architecture decision records (ADRs)**

---

## 16. Final Verdict

**Overall Assessment: B+ (Good, Room for Improvement)**

The codebase demonstrates **solid engineering practices** with a clear layered architecture. The recent refactoring from legacy code has significantly improved maintainability. However, there are **two critical bottlenecks** (AppFrame and AppController) that warrant attention.

**Key Success Metrics:**
- Repository pattern properly implemented
- Service layer separates business logic
- Dependency injection used throughout
- Thread-safe file operations
- Good error handling practices

**Critical Improvements Needed:**
- AppFrame god class requires splitting
- Missing interface abstractions (Protocols)
- Singleton pattern creates hidden dependencies
- Some SRP violations in controllers and repositories

**Risk Level:** MEDIUM

The architecture is sound, but the god classes create maintenance burden and testing challenges. Addressing the Priority 1 and 2 refactorings would elevate this to an A-grade codebase.

---

**Report Generated:** 2026-01-29
**Reviewer:** Claude Code (SOLID Principles Analysis)
**Codebase:** MTGO Tools (Python, wxPython)
