# Refactoring Plan: Add Protocol Interfaces for DIP Compliance

## Executive Summary

**Objective:** Add Protocol interface definitions for all major repositories and services to enable proper Dependency Inversion Principle (DIP) compliance, improve testability, and document contracts explicitly.

**Current State:**
- No explicit interface definitions for repositories or services
- High-level modules depend on concrete implementations via `get_*()` factory functions
- Cannot easily swap implementations or mock for testing
- Violates DIP (Dependency Inversion Principle)

**Target State:**
- Protocol classes for all major abstractions
- Type hints throughout using protocols instead of concrete classes
- Easier testing with protocol-based mocks
- Flexible architecture that can swap implementations

**Total Effort:** 18 atomic steps, estimated 8-13 hours
**Risk Level:** Low-Medium (mostly additive changes)

---

## Issues Identified

### SOLID Principle Violations

**1. Dependency Inversion Principle (DIP) - MODERATE**
- `AppController` depends on concrete `DeckRepository`, `CardRepository`, `MetagameRepository`
- Services depend on concrete implementations rather than abstractions
- Factory functions return concrete types, not interfaces
- No way to substitute implementations without modifying consumers

**2. Interface Segregation Principle (ISP) - MINOR**
- Large repository classes with many methods
- Consumers may only need subset of methods
- No focused interfaces for specific use cases

### Maintainability Issues

**1. Testing Barriers**
- Must mock concrete classes with all their methods
- No clear contract for what methods need to be mocked
- Difficult to create minimal test doubles

**2. Documentation Gaps**
- Interface contracts are implicit in implementation
- No single source of truth for required methods
- New developers must read implementations to understand APIs

**3. Flexibility Limitations**
- Cannot easily add alternative implementations (e.g., file-based vs MongoDB)
- Cannot create decorator/wrapper implementations
- Tight coupling makes refactoring risky

---

## Target Architecture

### Protocol Definitions

```
protocols/
├── __init__.py
├── repositories.py      # Repository protocols
└── services.py          # Service protocols
```

Or inline in existing files:

```
repositories/
├── protocols.py         # All repository protocols
├── deck_repository.py   # Implements DeckRepositoryProtocol
├── card_repository.py   # Implements CardRepositoryProtocol
└── metagame_repository.py  # Implements MetagameRepositoryProtocol

services/
├── protocols.py         # All service protocols
├── deck_service.py      # Implements DeckServiceProtocol
├── image_service.py     # Implements ImageServiceProtocol
└── collection_service.py  # Implements CollectionServiceProtocol
```

### Protocol Definitions

**DeckRepositoryProtocol** (~16 methods)
```python
class DeckRepositoryProtocol(Protocol):
    def save_to_db(self, deck_name: str, deck_content: str, ...) -> Any: ...
    def get_decks(self, format_type: str | None = None, ...) -> list[dict]: ...
    def load_from_db(self, deck_id: str) -> dict | None: ...
    def delete_from_db(self, deck_id: str) -> bool: ...
    def save_deck_to_file(self, deck_content: str, deck_name: str) -> Path | None: ...
    # ... etc
```

**CardRepositoryProtocol** (~11 methods)
```python
class CardRepositoryProtocol(Protocol):
    def get_card_manager(self) -> CardDataManager: ...
    def get_printing_index(self) -> dict[str, Any]: ...
    def load_collection_from_file(self, filepath: Path) -> list[dict]: ...
    # ... etc
```

**MetagameRepositoryProtocol** (~4 methods)
```python
class MetagameRepositoryProtocol(Protocol):
    def get_archetypes_for_format(self, format_type: str, ...) -> list[dict]: ...
    def get_decks_for_archetype(self, archetype: dict, ...) -> list[dict]: ...
    def download_deck_content(self, deck: dict) -> str | None: ...
    def clear_cache(self, format_type: str | None = None) -> None: ...
```

---

## Refactoring Steps

### Phase 1: Create Protocol Infrastructure (Low Risk)

---

## Step 1: Create repositories/protocols.py with DeckRepositoryProtocol

**Objective:** Define the interface contract for DeckRepository

**Principle Addressed:** DIP - Define abstraction for deck persistence

**Prerequisites:** None

**Files Affected:**
- `repositories/protocols.py` (NEW)

**Actions:**
1. Create `repositories/protocols.py`
2. Add imports:
   ```python
   from __future__ import annotations
   from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
   from pathlib import Path

   if TYPE_CHECKING:
       from bson import ObjectId
   ```
3. Define `DeckRepositoryProtocol`:
   ```python
   @runtime_checkable
   class DeckRepositoryProtocol(Protocol):
       """Protocol for deck persistence operations."""

       # Database operations
       def save_to_db(
           self,
           deck_name: str,
           deck_content: str,
           format_type: str | None = None,
           archetype: str | None = None,
           player: str | None = None,
           source: str = "manual",
           metadata: dict | None = None,
       ) -> ObjectId | None: ...

       def get_decks(
           self,
           format_type: str | None = None,
           archetype: str | None = None,
           sort_by: str = "date_saved",
           limit: int = 100,
       ) -> list[dict]: ...

       def load_from_db(self, deck_id: str | ObjectId) -> dict | None: ...

       def delete_from_db(self, deck_id: str | ObjectId) -> bool: ...

       def update_in_db(
           self,
           deck_id: str | ObjectId,
           deck_content: str | None = None,
           deck_name: str | None = None,
           metadata: dict | None = None,
       ) -> bool: ...

       # File operations
       def save_deck_to_file(
           self,
           deck_content: str,
           deck_name: str,
       ) -> Path | None: ...

       def list_deck_files(self) -> list[Path]: ...

       # Store operations (notes, guides, outboard)
       def load_notes(self, deck_key: str) -> str: ...
       def save_notes(self, deck_key: str, notes: str) -> None: ...
       def load_outboard(self, deck_key: str) -> dict[str, int]: ...
       def save_outboard(self, deck_key: str, outboard: dict[str, int]) -> None: ...
       def load_guide(self, deck_key: str) -> list[dict]: ...
       def save_guide(self, deck_key: str, entries: list[dict]) -> None: ...

       # State management (consider moving to separate protocol)
       def get_current_deck(self) -> dict | None: ...
       def set_current_deck(self, deck: dict | None) -> None: ...
       def get_deck_buffer(self) -> list[dict[str, int]]: ...
       def add_to_buffer(self, deck: dict[str, int]) -> None: ...
       def clear_buffer(self) -> None: ...
   ```

**Verification:**
- [ ] File compiles without errors
- [ ] Protocol can be imported
- [ ] `isinstance(DeckRepository(), DeckRepositoryProtocol)` returns True

**Rollback:** Delete `repositories/protocols.py`

**Risk Level:** Low - New file, no existing code changes

---

## Step 2: Add CardRepositoryProtocol to protocols.py

**Objective:** Define the interface contract for CardRepository

**Principle Addressed:** DIP - Define abstraction for card data access

**Prerequisites:** Step 1

**Files Affected:**
- `repositories/protocols.py`

**Actions:**
1. Add `CardRepositoryProtocol` to `repositories/protocols.py`:
   ```python
   @runtime_checkable
   class CardRepositoryProtocol(Protocol):
       """Protocol for card data and bulk data operations."""

       # Card data access
       def get_card_manager(self) -> CardDataManager: ...

       def get_printing_index(self) -> dict[str, Any]: ...

       def is_bulk_data_loaded(self) -> bool: ...

       # Bulk data operations
       def check_bulk_data_exists(self) -> tuple[bool, str]: ...

       def check_bulk_data_freshness(self, max_age_days: int = 7) -> tuple[bool, str]: ...

       def download_bulk_data(self, force: bool = False) -> tuple[bool, str]: ...

       def load_bulk_data(self) -> tuple[bool, str]: ...

       # Collection operations
       def load_collection_from_file(self, filepath: Path) -> list[dict]: ...

       # Image cache access
       @property
       def image_cache(self) -> ImageCache: ...
   ```
2. Add necessary imports for `CardDataManager`, `ImageCache`

**Verification:**
- [ ] Protocol compiles without errors
- [ ] `isinstance(CardRepository(), CardRepositoryProtocol)` returns True
- [ ] All methods match CardRepository implementation

**Rollback:** Remove CardRepositoryProtocol from protocols.py

**Risk Level:** Low - Additive change to new file

---

## Step 3: Add MetagameRepositoryProtocol to protocols.py

**Objective:** Define the interface contract for MetagameRepository

**Principle Addressed:** DIP - Define abstraction for metagame data fetching

**Prerequisites:** Step 1

**Files Affected:**
- `repositories/protocols.py`

**Actions:**
1. Add `MetagameRepositoryProtocol` to `repositories/protocols.py`:
   ```python
   @runtime_checkable
   class MetagameRepositoryProtocol(Protocol):
       """Protocol for metagame and archetype data operations."""

       def get_archetypes_for_format(
           self,
           format_type: str,
           force_refresh: bool = False,
           max_cache_age: int | None = None,
       ) -> list[dict]: ...

       def get_decks_for_archetype(
           self,
           archetype: dict,
           force_refresh: bool = False,
           max_cache_age: int | None = None,
       ) -> list[dict]: ...

       def download_deck_content(self, deck: dict) -> str | None: ...

       def clear_cache(self, format_type: str | None = None) -> None: ...
   ```

**Verification:**
- [ ] Protocol compiles without errors
- [ ] `isinstance(MetagameRepository(), MetagameRepositoryProtocol)` returns True
- [ ] All methods match MetagameRepository implementation

**Rollback:** Remove MetagameRepositoryProtocol from protocols.py

**Risk Level:** Low - Additive change to new file

---

## Step 4: Create services/protocols.py with ImageServiceProtocol

**Objective:** Define the interface contract for ImageService

**Principle Addressed:** DIP - Define abstraction for image/bulk data service

**Prerequisites:** None

**Files Affected:**
- `services/protocols.py` (NEW)

**Actions:**
1. Create `services/protocols.py`
2. Add imports and `ImageServiceProtocol`:
   ```python
   from __future__ import annotations
   from typing import TYPE_CHECKING, Any, Callable, Protocol, runtime_checkable

   if TYPE_CHECKING:
       from utils.card_images import ImageCache

   @runtime_checkable
   class ImageServiceProtocol(Protocol):
       """Protocol for image and bulk data management."""

       @property
       def image_cache(self) -> ImageCache: ...

       @property
       def printing_index(self) -> dict[str, Any]: ...

       def check_bulk_data_exists(
           self,
           on_exists: Callable[[bool, str], None],
           on_error: Callable[[str], None],
       ) -> None: ...

       def ensure_data_ready(
           self,
           force_cached: bool,
           max_age_days: int,
           on_load_success: Callable[[], None],
           on_load_error: Callable[[str], None],
           on_download_success: Callable[[], None],
           on_download_error: Callable[[str], None],
           on_check_failed: Callable[[str], None],
           set_status: Callable[[str], None],
       ) -> None: ...

       def download_bulk_data(
           self,
           force: bool,
           on_success: Callable[[], None],
           on_error: Callable[[str], None],
           set_status: Callable[[str], None],
       ) -> None: ...

       def load_printing_index(
           self,
           on_success: Callable[[], None],
           on_error: Callable[[str], None],
           set_status: Callable[[str], None],
           force: bool = False,
       ) -> None: ...

       def is_bulk_data_loaded(self) -> bool: ...

       def get_card_image_url(self, card_name: str, set_code: str | None = None) -> str | None: ...
   ```

**Verification:**
- [ ] File compiles without errors
- [ ] Protocol can be imported
- [ ] `isinstance(ImageService(), ImageServiceProtocol)` returns True

**Rollback:** Delete `services/protocols.py`

**Risk Level:** Low - New file, no existing code changes

---

## Step 5: Add DeckServiceProtocol to services/protocols.py

**Objective:** Define the interface contract for DeckService

**Principle Addressed:** DIP - Define abstraction for deck business logic

**Prerequisites:** Step 4

**Files Affected:**
- `services/protocols.py`

**Actions:**
1. Add `DeckServiceProtocol` to `services/protocols.py`:
   ```python
   @runtime_checkable
   class DeckServiceProtocol(Protocol):
       """Protocol for deck manipulation and analysis operations."""

       def parse_deck_text(self, deck_text: str) -> dict[str, dict[str, int]]: ...

       def build_deck_text(
           self,
           zone_cards: dict[str, dict[str, int]],
           include_sideboard: bool = True,
       ) -> str: ...

       def average_decks(self, decks: list[dict[str, int]]) -> dict[str, float]: ...

       def update_zone(
           self,
           zone_cards: dict[str, dict[str, int]],
           zone: str,
           card_name: str,
           delta: int,
       ) -> ZoneUpdateResult: ...

       def remove_from_zone(
           self,
           zone_cards: dict[str, dict[str, int]],
           zone: str,
           card_name: str,
       ) -> ZoneUpdateResult: ...

       def add_to_zone(
           self,
           zone_cards: dict[str, dict[str, int]],
           zone: str,
           card_name: str,
           quantity: int = 1,
       ) -> ZoneUpdateResult: ...

       def move_between_zones(
           self,
           zone_cards: dict[str, dict[str, int]],
           from_zone: str,
           to_zone: str,
           card_name: str,
           quantity: int = 1,
       ) -> ZoneUpdateResult: ...

       def analyze_deck(self, deck_content: str) -> dict[str, Any]: ...
   ```
2. Import `ZoneUpdateResult` from deck_service or define inline

**Verification:**
- [ ] Protocol compiles without errors
- [ ] `isinstance(DeckService(), DeckServiceProtocol)` returns True
- [ ] All methods match DeckService implementation

**Rollback:** Remove DeckServiceProtocol from services/protocols.py

**Risk Level:** Low - Additive change to new file

---

## Step 6: Add CollectionServiceProtocol to services/protocols.py

**Objective:** Define the interface contract for CollectionService

**Principle Addressed:** DIP - Define abstraction for collection management

**Prerequisites:** Step 4

**Files Affected:**
- `services/protocols.py`

**Actions:**
1. Add `CollectionServiceProtocol` to `services/protocols.py`:
   ```python
   @runtime_checkable
   class CollectionServiceProtocol(Protocol):
       """Protocol for MTGO collection operations."""

       def load_collection_from_cache(
           self,
           cache_directory: Path,
       ) -> CollectionStatus: ...

       def refresh_collection_from_bridge(
           self,
           output_directory: Path,
           force: bool = False,
       ) -> CollectionStatus: ...

       def get_collection_cards(self) -> list[dict]: ...

       def check_card_ownership(self, card_name: str, quantity: int = 1) -> bool: ...

       def get_missing_cards(
           self,
           deck_cards: dict[str, int],
       ) -> dict[str, int]: ...
   ```
2. Import `CollectionStatus` from collection_service or use forward reference

**Verification:**
- [ ] Protocol compiles without errors
- [ ] `isinstance(CollectionService(), CollectionServiceProtocol)` returns True

**Rollback:** Remove CollectionServiceProtocol from services/protocols.py

**Risk Level:** Low - Additive change to new file

---

## Step 7: Export all protocols from __init__.py files

**Objective:** Make protocols easily importable

**Principle Addressed:** Maintainability - Clean import paths

**Prerequisites:** Steps 1-6

**Files Affected:**
- `repositories/__init__.py` (NEW or UPDATE)
- `services/__init__.py` (NEW or UPDATE)

**Actions:**
1. Create or update `repositories/__init__.py`:
   ```python
   from .protocols import (
       DeckRepositoryProtocol,
       CardRepositoryProtocol,
       MetagameRepositoryProtocol,
   )

   __all__ = [
       "DeckRepositoryProtocol",
       "CardRepositoryProtocol",
       "MetagameRepositoryProtocol",
   ]
   ```
2. Create or update `services/__init__.py`:
   ```python
   from .protocols import (
       ImageServiceProtocol,
       DeckServiceProtocol,
       CollectionServiceProtocol,
   )

   __all__ = [
       "ImageServiceProtocol",
       "DeckServiceProtocol",
       "CollectionServiceProtocol",
   ]
   ```

**Verification:**
- [ ] `from repositories import DeckRepositoryProtocol` works
- [ ] `from services import ImageServiceProtocol` works
- [ ] No circular import errors

**Rollback:** Remove __init__.py exports

**Risk Level:** Low - Import organization

---

### Phase 2: Update Type Hints in Services (Low-Medium Risk)

---

## Step 8: Update DeckService to use repository protocol in type hints

**Objective:** DeckService depends on protocol, not concrete repository

**Principle Addressed:** DIP - High-level module depends on abstraction

**Prerequisites:** Steps 1, 5

**Files Affected:**
- `services/deck_service.py`

**Actions:**
1. Update imports:
   ```python
   from repositories.protocols import DeckRepositoryProtocol
   ```
2. Update constructor type hint:
   ```python
   def __init__(
       self,
       deck_repo: DeckRepositoryProtocol | None = None,
       ...
   ):
   ```
3. Update any method parameters that accept repository
4. Keep default factory function unchanged (still returns concrete type)

**Verification:**
- [ ] Type checker passes (mypy/pyright)
- [ ] All tests pass
- [ ] Application runs correctly
- [ ] IDE autocomplete still works

**Rollback:** Revert type hint changes

**Risk Level:** Low - Type hint only, no runtime behavior change

---

## Step 9: Update ImageService to use protocol in type hints

**Objective:** ImageService internal types use protocols where applicable

**Principle Addressed:** DIP - Consistent abstraction usage

**Prerequisites:** Step 4

**Files Affected:**
- `services/image_service.py`

**Actions:**
1. Verify ImageService implements ImageServiceProtocol fully
2. Add any missing methods to make implementation complete
3. Update any internal type hints to use protocols
4. Add `# implements ImageServiceProtocol` comment for documentation

**Verification:**
- [ ] `isinstance(ImageService(), ImageServiceProtocol)` returns True
- [ ] All protocol methods exist in implementation
- [ ] No missing method errors

**Rollback:** Revert changes

**Risk Level:** Low - Verification and documentation

---

## Step 10: Update CollectionService to use protocols

**Objective:** CollectionService uses protocol type hints

**Principle Addressed:** DIP - Consistent abstraction usage

**Prerequisites:** Step 6

**Files Affected:**
- `services/collection_service.py`

**Actions:**
1. Verify CollectionService implements CollectionServiceProtocol fully
2. Update constructor to accept protocol types:
   ```python
   def __init__(
       self,
       card_repo: CardRepositoryProtocol | None = None,
       ...
   ):
   ```
3. Add any missing methods to satisfy protocol

**Verification:**
- [ ] `isinstance(CollectionService(), CollectionServiceProtocol)` returns True
- [ ] Type checker passes
- [ ] All tests pass

**Rollback:** Revert changes

**Risk Level:** Low - Type hints and verification

---

## Step 11: Update AppController to use protocol type hints

**Objective:** AppController depends on protocol abstractions

**Principle Addressed:** DIP - Controller depends on abstractions, not concretions

**Prerequisites:** Steps 1-6

**Files Affected:**
- `controllers/app_controller.py`

**Actions:**
1. Update imports:
   ```python
   from repositories.protocols import (
       DeckRepositoryProtocol,
       CardRepositoryProtocol,
       MetagameRepositoryProtocol,
   )
   from services.protocols import (
       ImageServiceProtocol,
       DeckServiceProtocol,
       CollectionServiceProtocol,
   )
   ```
2. Update constructor type hints:
   ```python
   def __init__(
       self,
       deck_repo: DeckRepositoryProtocol | None = None,
       card_repo: CardRepositoryProtocol | None = None,
       metagame_repo: MetagameRepositoryProtocol | None = None,
       image_service: ImageServiceProtocol | None = None,
       deck_service: DeckServiceProtocol | None = None,
       collection_service: CollectionServiceProtocol | None = None,
       ...
   ):
   ```
3. Update instance variable type hints in class body
4. Keep factory function defaults (return concrete types)

**Verification:**
- [ ] Type checker passes
- [ ] All tests pass
- [ ] Application runs correctly
- [ ] Dependency injection still works

**Rollback:** Revert type hint changes

**Risk Level:** Medium - Central class, many type hints to update

---

### Phase 3: Update Factory Functions (Low Risk)

---

## Step 12: Update factory function return types to protocols

**Objective:** Factory functions return protocol types for flexibility

**Principle Addressed:** DIP - Factories return abstractions

**Prerequisites:** Steps 1-6

**Files Affected:**
- `repositories/deck_repository.py`
- `repositories/card_repository.py`
- `repositories/metagame_repository.py`
- `services/image_service.py`
- `services/deck_service.py`
- `services/collection_service.py`

**Actions:**
1. Update each `get_*()` factory function return type:
   ```python
   # In deck_repository.py
   def get_deck_repository() -> DeckRepositoryProtocol:
       global _deck_repository
       if _deck_repository is None:
           _deck_repository = DeckRepository()
       return _deck_repository
   ```
2. Repeat for all factory functions:
   - `get_deck_repository() -> DeckRepositoryProtocol`
   - `get_card_repository() -> CardRepositoryProtocol`
   - `get_metagame_repository() -> MetagameRepositoryProtocol`
   - `get_image_service() -> ImageServiceProtocol`
   - `get_deck_service() -> DeckServiceProtocol`
   - `get_collection_service() -> CollectionServiceProtocol`

**Verification:**
- [ ] Type checker passes
- [ ] All factory functions return correct type
- [ ] Singleton behavior unchanged
- [ ] All tests pass

**Rollback:** Revert return type annotations

**Risk Level:** Low - Return type annotations only

---

## Step 13: Update reset functions to use protocols

**Objective:** Reset functions accept protocol types for testing

**Principle Addressed:** Testability - Can inject mock implementations

**Prerequisites:** Step 12

**Files Affected:**
- All repository and service files with reset functions

**Actions:**
1. Update `reset_*()` functions to accept protocol types:
   ```python
   def reset_deck_repository(
       instance: DeckRepositoryProtocol | None = None
   ) -> None:
       global _deck_repository
       _deck_repository = instance
   ```
2. This allows injecting mock implementations in tests:
   ```python
   # In test
   class MockDeckRepo:
       def save_to_db(self, ...): ...
       # Only implement methods needed for test

   reset_deck_repository(MockDeckRepo())
   ```

**Verification:**
- [ ] Reset functions accept protocol-compliant objects
- [ ] Tests can inject mock implementations
- [ ] Type checker passes

**Rollback:** Revert parameter type changes

**Risk Level:** Low - Test infrastructure improvement

---

### Phase 4: Create Protocol-Based Test Fixtures (Low Risk)

---

## Step 14: Create test fixture protocols in tests/

**Objective:** Provide minimal mock implementations for testing

**Principle Addressed:** Testability - Easy mock creation

**Prerequisites:** Steps 1-6

**Files Affected:**
- `tests/fixtures/mock_repositories.py` (NEW)
- `tests/fixtures/mock_services.py` (NEW)

**Actions:**
1. Create `tests/fixtures/mock_repositories.py`:
   ```python
   from repositories.protocols import DeckRepositoryProtocol

   class MockDeckRepository:
       """Minimal mock for DeckRepository in tests."""

       def __init__(self):
           self._decks: list[dict] = []
           self._current_deck: dict | None = None
           self._buffer: list[dict] = []

       def save_to_db(self, deck_name, deck_content, **kwargs):
           deck = {"name": deck_name, "content": deck_content, **kwargs}
           self._decks.append(deck)
           return "mock_id"

       def get_decks(self, **kwargs):
           return self._decks

       # ... minimal implementations for other methods

       # For methods not needed in most tests, raise NotImplementedError
       def load_from_db(self, deck_id):
           raise NotImplementedError("Mock not configured for load_from_db")
   ```
2. Create similar mocks for other repositories and services
3. Add `__all__` exports

**Verification:**
- [ ] Mock classes satisfy protocols (isinstance check passes)
- [ ] Mocks can be used in tests
- [ ] Type checker accepts mocks where protocols expected

**Rollback:** Delete fixture files

**Risk Level:** Low - Test infrastructure only

---

## Step 15: Update existing tests to use protocol-based mocks

**Objective:** Demonstrate protocol usage in tests

**Principle Addressed:** Testability - Clean test architecture

**Prerequisites:** Step 14

**Files Affected:**
- `tests/test_deck_service.py` (if exists)
- `tests/test_store_service.py`
- Other test files as appropriate

**Actions:**
1. Update tests to use mock fixtures:
   ```python
   from tests.fixtures.mock_repositories import MockDeckRepository

   def test_deck_service_uses_repository():
       mock_repo = MockDeckRepository()
       service = DeckService(deck_repo=mock_repo)

       # Test service behavior
       service.save_deck("test", "4 Lightning Bolt")

       assert len(mock_repo._decks) == 1
   ```
2. Verify tests pass with mock implementations
3. Document pattern for future tests

**Verification:**
- [ ] Updated tests pass
- [ ] Tests are cleaner and more focused
- [ ] Mock injection works correctly

**Rollback:** Revert test changes

**Risk Level:** Low - Test improvements only

---

### Phase 5: Documentation and Remaining Protocols (Low Risk)

---

## Step 16: Add docstrings to all protocols

**Objective:** Document protocol contracts clearly

**Principle Addressed:** Maintainability - Clear documentation

**Prerequisites:** Steps 1-6

**Files Affected:**
- `repositories/protocols.py`
- `services/protocols.py`

**Actions:**
1. Add comprehensive docstrings to each protocol:
   ```python
   @runtime_checkable
   class DeckRepositoryProtocol(Protocol):
       """
       Protocol for deck persistence operations.

       Implementations handle storing and retrieving deck data from
       various backends (MongoDB, filesystem, etc.).

       Required Methods:
           save_to_db: Persist deck to database
           get_decks: Retrieve deck list with optional filters
           load_from_db: Load single deck by ID
           delete_from_db: Remove deck from database

       State Methods (may be moved to separate protocol):
           get_current_deck: Get currently selected deck
           set_current_deck: Set currently selected deck

       Example:
           repo: DeckRepositoryProtocol = get_deck_repository()
           decks = repo.get_decks(format_type="Modern")
       """
   ```
2. Add docstrings to each method in protocol
3. Include parameter descriptions and return types

**Verification:**
- [ ] All protocols have docstrings
- [ ] All methods have docstrings
- [ ] Documentation renders correctly in IDE

**Rollback:** Remove docstrings (non-functional)

**Risk Level:** Low - Documentation only

---

## Step 17: Add StoreServiceProtocol

**Objective:** Define protocol for JSON store operations

**Principle Addressed:** DIP - Complete abstraction coverage

**Prerequisites:** Step 4

**Files Affected:**
- `services/protocols.py`

**Actions:**
1. Add `StoreServiceProtocol`:
   ```python
   @runtime_checkable
   class StoreServiceProtocol(Protocol):
       """Protocol for JSON store operations."""

       def load_store(self, store_path: Path) -> dict[str, Any]: ...

       def save_store(self, store_path: Path, data: dict[str, Any]) -> None: ...

       def get_value(
           self,
           store_path: Path,
           key: str,
           default: Any = None,
       ) -> Any: ...

       def set_value(
           self,
           store_path: Path,
           key: str,
           value: Any,
       ) -> None: ...
   ```
2. Verify StoreService implements protocol
3. Update exports

**Verification:**
- [ ] Protocol defined correctly
- [ ] StoreService satisfies protocol
- [ ] Exports updated

**Rollback:** Remove StoreServiceProtocol

**Risk Level:** Low - Additive change

---

## Step 18: Add SearchServiceProtocol (if applicable)

**Objective:** Define protocol for card search operations

**Principle Addressed:** DIP - Complete abstraction coverage

**Prerequisites:** Step 4

**Files Affected:**
- `services/protocols.py`

**Actions:**
1. Review if search functionality exists as separate service
2. If yes, add `SearchServiceProtocol`:
   ```python
   @runtime_checkable
   class SearchServiceProtocol(Protocol):
       """Protocol for card search operations."""

       def search_cards(
           self,
           query: str,
           filters: dict | None = None,
           limit: int = 50,
       ) -> list[dict]: ...

       def get_card_by_name(self, name: str) -> dict | None: ...

       def get_cards_by_set(self, set_code: str) -> list[dict]: ...
   ```
3. If no separate search service, skip this step

**Verification:**
- [ ] Protocol matches existing search functionality
- [ ] Or step skipped if not applicable

**Rollback:** Remove SearchServiceProtocol

**Risk Level:** Low - Additive or skip

---

## Risk Assessment

### Overall Risk Level: Low-Medium

**Mitigation Strategies:**

1. **No Runtime Changes:** Protocols are type hints only, no runtime behavior change
2. **Incremental Addition:** Each step adds new code, doesn't modify existing logic
3. **Backward Compatible:** Existing code continues to work unchanged
4. **Easy Rollback:** Each step can be reverted independently
5. **Type Checker Validation:** mypy/pyright catches issues before runtime

**Specific Risks:**

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Type hint conflicts | Low | Low | Run type checker after each step |
| Import cycles | Low | Medium | Protocols in separate files, use TYPE_CHECKING |
| Missing protocol methods | Low | Low | isinstance checks verify completeness |
| IDE confusion | Low | Low | @runtime_checkable enables isinstance |

---

## Success Metrics

**Quantitative:**
- [ ] 6+ protocol definitions created
- [ ] All repositories implement their protocols (isinstance passes)
- [ ] All services implement their protocols (isinstance passes)
- [ ] Type checker passes with no errors
- [ ] All existing tests pass

**Qualitative:**
- [ ] Can inject mock repositories in tests easily
- [ ] IDE autocomplete works with protocol types
- [ ] New developers understand interfaces from protocol docs
- [ ] Could add alternative implementations without modifying consumers

**Behavioral:**
- [ ] Application runs identically to before
- [ ] No new runtime errors
- [ ] Tests can use simplified mocks
- [ ] Type hints provide better IDE support

---

## Files Summary

**New Files (4):**
- `repositories/protocols.py` - Repository protocols
- `services/protocols.py` - Service protocols
- `tests/fixtures/mock_repositories.py` - Test mocks
- `tests/fixtures/mock_services.py` - Test mocks

**Modified Files (8+):**
- `repositories/__init__.py` - Exports
- `services/__init__.py` - Exports
- `services/deck_service.py` - Type hints
- `services/image_service.py` - Type hints
- `services/collection_service.py` - Type hints
- `controllers/app_controller.py` - Type hints
- Factory functions in all repository/service files

---

## Implementation Timeline

**Phase 1 (Infrastructure):** 2-3 hours
- Steps 1-7: Create all protocol definitions

**Phase 2 (Type Hints):** 2-3 hours
- Steps 8-11: Update services and controllers

**Phase 3 (Factories):** 1 hour
- Steps 12-13: Update factory functions

**Phase 4 (Testing):** 1-2 hours
- Steps 14-15: Create test fixtures

**Phase 5 (Documentation):** 1-2 hours
- Steps 16-18: Complete documentation

**Total Estimated Time:** 8-13 hours

---

## Conclusion

This refactoring introduces explicit interface definitions throughout the codebase, enabling:

1. **Better Testing:** Mock implementations are easy to create and inject
2. **Clearer Contracts:** Protocol docstrings document expected behavior
3. **Flexible Architecture:** Can swap implementations without modifying consumers
4. **SOLID Compliance:** Proper DIP and ISP adherence
5. **IDE Support:** Type hints improve autocomplete and error detection

The incremental approach ensures the codebase remains stable throughout, with each step independently verifiable and reversible. The protocols provide a foundation for future architectural improvements like:

- Alternative repository backends (SQLite, file-based)
- Decorator/wrapper implementations for caching, logging
- Test doubles that only implement needed methods
- Plugin architecture for custom implementations
