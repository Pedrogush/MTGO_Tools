# AppController Refactoring Plan - Extract Specialized Controllers

## Executive Summary

The `AppController` class currently handles 10+ distinct concerns in a 555-line class that violates the Single Responsibility Principle. This refactoring will split it into focused controllers while maintaining `AppController` as a lightweight facade. The refactoring will proceed through 22 atomic steps ordered from low-risk foundational changes to higher-risk integration work.

**Estimated Total Effort:** 16-20 hours
**Number of Steps:** 22
**Risk Level:** Medium (mitigated through incremental approach)

## Issues Identified

### SOLID Principle Violations

**1. Single Responsibility Principle (SRP) - SEVERE**
`AppController` currently handles:
- Archetype fetching and caching (lines 173-210)
- Deck list management (lines 212-249)
- Deck download/save operations (lines 251-292)
- Daily average deck computation (lines 293-342)
- Collection management (lines 344-398)
- Bulk data coordination (lines 400-412)
- MTGO bridge status monitoring (lines 346-370)
- Session settings persistence (lines 414-424)
- UI callback registration (lines 118, 520)
- Frame factory (lines 512-532)
- Background worker lifecycle (lines 534-538)

**2. Open/Closed Principle (OCP) - MODERATE**
- Adding new data sources (MTGO decklists, etc.) requires modifying controller core
- New archetype providers need changes to fetch logic
- Extending bulk data flows requires editing the controller

**3. Dependency Inversion Principle (DIP) - MODERATE**
- Direct coupling to concrete `BackgroundWorker` implementation
- Direct imports of specific services rather than abstractions
- Frame creation directly instantiates `AppFrame`

### DRY Violations

**1. Duplicate Threading Patterns** (lines 155-171, 189-210, 229-249, 317-340)
- Repeated pattern: acquire lock -> set flag -> submit to worker -> handlers update flag
- Nearly identical success/error handler structures across 4+ methods
- Lock management duplicated in each async operation

**2. Duplicate Callback Patterns** (lines 384-398, 486-502)
- Repeated pattern: get callback from dict -> check if exists -> call with CallAfter
- Status update boilerplate duplicated across methods

**3. Source Filter Propagation** (lines 227, 267, 315, 448)
- `get_deck_data_source()` called repeatedly in similar contexts
- Source filter passed to workflow service in 4 different places

### Maintainability Issues

**1. High Coupling**
- AppFrame directly accesses 8+ controller attributes (repos, services, stores)
- Changes to repository interfaces require controller updates
- Helper classes (`BulkDataHelpers`, `MtgoBackgroundHelpers`) tightly coupled to controller

**2. Mixed Abstraction Levels**
- High-level orchestration (`run_initial_loads`) mixed with low-level state management
- Business logic (`build_deck_text`) mixed with infrastructure (`create_frame`)
- Data access (stores) mixed with coordination logic

**3. Testing Barriers**
- Cannot test archetype fetching without mocking 5+ dependencies
- Background worker makes unit testing difficult
- Frame creation coupled to controller initialization

**4. Unclear Boundaries**
- "Helpers" are actually feature coordinators but lack clear ownership
- Session manager overlaps with settings methods in controller
- Workflow service duplicates orchestration concerns

### Nomenclature Issues

**1. Naming Inconsistency**
- "Helpers" suffix used for coordinator classes (should be "Coordinator" or "Manager")
- `_ui_callbacks` is state, not configuration
- `ensure_card_data_loaded` is async but doesn't indicate so in name

**2. File Organization**
- All controllers in flat `/controllers` directory
- Helpers mixed with main controller
- No clear grouping by domain (deck, collection, bulk data, session)

## Target Architecture

### New Controller Structure

```
controllers/
├── app_controller.py           # Thin facade (150 lines)
├── archetype_controller.py     # NEW - Archetype fetching/caching
├── deck_controller.py          # NEW - Deck operations
├── collection_controller.py    # NEW - Collection & MTGO bridge
├── session_controller.py       # NEW - Settings persistence
├── bulk_data_coordinator.py    # RENAMED from bulk_data_helpers.py
├── mtgo_coordinator.py         # RENAMED from mtgo_background_helpers.py
└── ui_callbacks.py             # RENAMED from app_controller_helpers.py
```

### Responsibility Distribution

**ArchetypeController** (~120 lines)
- `fetch_archetypes(format, on_success, on_error, on_status, force)`
- `load_decks_for_archetype(archetype, on_success, on_error, on_status)`
- `filter_archetypes(query)`
- State: `archetypes`, `filtered_archetypes`, `loading_archetypes`

**DeckController** (~180 lines)
- `download_deck(deck, on_success, on_error, on_status)`
- `save_deck(name, content, format, metadata)`
- `build_daily_average(on_success, on_error, on_status, on_progress)`
- `build_deck_text(zone_cards)`
- State: `zone_cards`, `loading_daily_average`

**CollectionController** (~140 lines)
- `load_collection_from_cache(directory)`
- `refresh_collection_from_bridge(directory, force)`
- `check_mtgo_bridge_status()`
- `start_status_monitoring()`
- State: MTGO connection status, collection cache info

**SessionController** (~100 lines)
- `save_settings(format, mode, source, zone_cards, window_size, screen_pos)`
- `restore_session_state(zone_cards)`
- `get_current_format() / set_current_format()`
- `get_deck_data_source() / set_deck_data_source()`
- State: All session/settings state

**AppController (Facade)** (~150 lines)
- Holds references to specialized controllers
- Delegates to appropriate controller
- Provides unified interface for UI
- Manages shared resources (worker, stores)
- Frame factory

## Refactoring Steps

### Phase 1: Foundation - Extract Pure Logic (Low Risk)

---

## Step 1: Extract SessionController

**Objective:** Move all settings/session management to dedicated controller

**Principle Addressed:** SRP - Settings persistence is a distinct concern

**Prerequisites:** None

**Files Affected:**
- `controllers/session_controller.py` (NEW)
- `controllers/app_controller.py`

**Actions:**
1. Create `controllers/session_controller.py`
2. Move `DeckSelectorSessionManager` integration and settings methods from `AppController` (lines 80, 88-102, 414-437, 457-479)
3. Add methods:
   - `get_current_format() / set_current_format()`
   - `get_deck_data_source() / set_deck_data_source()`
   - `get_left_mode() / set_left_mode()`
   - `save_settings(format, mode, source, zone_cards, window_size, screen_pos)`
   - `restore_session_state(zone_cards)`
4. Encapsulate `session_manager`, `current_format`, `_deck_data_source`, `left_mode` as private
5. Update `AppController.__init__` to create `SessionController` instance
6. Replace direct session manager calls in `AppController` with delegation to `SessionController`

**Verification:**
- [ ] All tests pass
- [ ] Session saves/restores correctly on app restart
- [ ] Format switching works
- [ ] Deck data source filter changes persist

**Rollback:** Git revert the commit

**Risk Level:** Low - Pure extraction with no behavior change, well-isolated concern

---

## Step 2: Create Abstract Base for Async Controllers

**Objective:** Establish common pattern for controllers with background operations

**Principle Addressed:** DRY - Eliminate duplicate threading patterns

**Prerequisites:** None

**Files Affected:**
- `controllers/base_async_controller.py` (NEW)

**Actions:**
1. Create `controllers/base_async_controller.py`
2. Define `BaseAsyncController` abstract class with:
   - `_worker: BackgroundWorker` (injected)
   - `_loading_lock: threading.Lock`
   - `submit_task(worker_fn, on_success, on_error)` - Common pattern for async tasks
   - `_with_loading_flag(flag_name, operation)` - Context manager for loading flags
3. Add common callback handling utilities:
   - `_call_if_exists(callbacks_dict, key, *args)` - Safe callback invocation

**Verification:**
- [ ] File compiles without errors
- [ ] Can be imported successfully
- [ ] Docstrings explain usage pattern

**Rollback:** Delete the new file

**Risk Level:** Low - New abstraction, no existing code changes

---

## Step 3: Extract ArchetypeController

**Objective:** Move archetype and deck list fetching to dedicated controller

**Principle Addressed:** SRP - Archetype/deck list management is a cohesive concern

**Prerequisites:** Step 2 (uses BaseAsyncController)

**Files Affected:**
- `controllers/archetype_controller.py` (NEW)
- `controllers/app_controller.py`

**Actions:**
1. Create `controllers/archetype_controller.py`
2. Inherit from `BaseAsyncController`
3. Move archetype-related methods from `AppController`:
   - `fetch_archetypes()` (lines 173-210)
   - `load_decks_for_archetype()` (lines 212-249)
4. Move state: `archetypes`, `filtered_archetypes`, `loading_archetypes`, `loading_decks`
5. Add state accessors:
   - `get_archetypes() / get_filtered_archetypes() / set_filtered_archetypes()`
6. Inject dependencies: `workflow_service`, `worker`, `session_controller` (for format)
7. Update `AppController.__init__` to create `ArchetypeController` instance
8. Delegate `fetch_archetypes()` and `load_decks_for_archetype()` calls to new controller
9. Update `app_frame.py` to call controller methods through facade

**Verification:**
- [ ] All tests pass
- [ ] Archetype list loads correctly
- [ ] Deck list loads when selecting archetype
- [ ] Loading states work (spinners, disabled buttons)
- [ ] Errors display properly

**Rollback:** Git revert the commit

**Risk Level:** Low-Medium - Pure extraction, but touches UI integration points

---

## Step 4: Extract DeckController

**Objective:** Move deck operations (download, save, average) to dedicated controller

**Principle Addressed:** SRP - Deck manipulation is a cohesive concern

**Prerequisites:** Step 2 (uses BaseAsyncController)

**Files Affected:**
- `controllers/deck_controller.py` (NEW)
- `controllers/app_controller.py`

**Actions:**
1. Create `controllers/deck_controller.py`
2. Inherit from `BaseAsyncController`
3. Move deck-related methods from `AppController`:
   - `download_and_display_deck()` (lines 253-272)
   - `download_deck()` (lines 440-453) - Consolidate with above
   - `build_deck_text()` (lines 274-276)
   - `save_deck()` (lines 278-291)
   - `build_daily_average_deck()` (lines 293-342)
4. Move state: `zone_cards`, `loading_daily_average`
5. Add methods:
   - `get_zone_cards() -> dict`
   - `set_zone_cards(zone_cards)`
6. Inject dependencies: `workflow_service`, `deck_repo`, `worker`, `session_controller` (for source/dir)
7. Update `AppController.__init__` to create `DeckController` instance
8. Delegate all deck operations to new controller
9. Update `app_frame.py` references

**Verification:**
- [ ] Deck download works
- [ ] Deck save to file and DB works
- [ ] Daily average deck computation works
- [ ] Progress indicators display correctly
- [ ] Zone cards state persists

**Rollback:** Git revert the commit

**Risk Level:** Medium - Multiple complex operations, involves background tasks

---

## Step 5: Rename bulk_data_helpers.py to bulk_data_coordinator.py

**Objective:** Use consistent nomenclature ("Coordinator" not "Helpers")

**Principle Addressed:** Nomenclature consistency

**Prerequisites:** None

**Files Affected:**
- `controllers/bulk_data_helpers.py` -> `bulk_data_coordinator.py`
- `controllers/app_controller.py`

**Actions:**
1. Rename file: `bulk_data_helpers.py` -> `bulk_data_coordinator.py`
2. Rename class: `BulkDataHelpers` -> `BulkDataCoordinator`
3. Update import in `app_controller.py` (line 25)
4. Update instantiation in `app_controller.py` (line 123)
5. Update variable name: `_bulk_data_helpers` -> `_bulk_data_coordinator`

**Verification:**
- [ ] All imports resolve correctly
- [ ] Application starts without errors
- [ ] Bulk data check runs on startup

**Rollback:** Git revert (simple rename)

**Risk Level:** Low - Mechanical rename

---

## Step 6: Rename mtgo_background_helpers.py to mtgo_coordinator.py

**Objective:** Use consistent nomenclature ("Coordinator" not "Helpers")

**Principle Addressed:** Nomenclature consistency

**Prerequisites:** None

**Files Affected:**
- `controllers/mtgo_background_helpers.py` -> `mtgo_coordinator.py`
- `controllers/app_controller.py`

**Actions:**
1. Rename file: `mtgo_background_helpers.py` -> `mtgo_coordinator.py`
2. Rename class: `MtgoBackgroundHelpers` -> `MtgoCoordinator`
3. Update import in `app_controller.py` (line 26)
4. Update instantiation in `app_controller.py` (line 128)
5. Update variable name: `_mtgo_background_helpers` -> `_mtgo_coordinator`

**Verification:**
- [ ] All imports resolve correctly
- [ ] Application starts without errors
- [ ] MTGO background fetch runs (if enabled)
- [ ] Status monitoring works

**Rollback:** Git revert (simple rename)

**Risk Level:** Low - Mechanical rename

---

## Step 7: Rename app_controller_helpers.py to ui_callbacks.py

**Objective:** More descriptive name for UI callback builder

**Principle Addressed:** Nomenclature clarity

**Prerequisites:** None

**Files Affected:**
- `controllers/app_controller_helpers.py` -> `ui_callbacks.py`
- `controllers/app_controller.py`

**Actions:**
1. Rename file: `app_controller_helpers.py` -> `ui_callbacks.py`
2. Rename class: `AppControllerUIHelpers` -> `UICallbackBuilder`
3. Update import in `app_controller.py` (line 24)
4. Update usage in `app_controller.py` (line 520)

**Verification:**
- [ ] All imports resolve correctly
- [ ] UI callbacks work (status updates, errors, etc.)

**Rollback:** Git revert (simple rename)

**Risk Level:** Low - Mechanical rename

---

### Phase 2: Extract Complex Concerns (Medium Risk)

---

## Step 8: Extract CollectionController - Part 1 (Core Logic)

**Objective:** Move collection loading and caching logic to dedicated controller

**Principle Addressed:** SRP - Collection management is a distinct concern

**Prerequisites:** Step 2 (uses BaseAsyncController)

**Files Affected:**
- `controllers/collection_controller.py` (NEW)
- `controllers/app_controller.py`

**Actions:**
1. Create `controllers/collection_controller.py`
2. Inherit from `BaseAsyncController`
3. Move collection methods from `AppController`:
   - `load_collection_from_cache()` (lines 372-378)
   - `refresh_collection_from_bridge()` (lines 380-398)
4. Inject dependencies: `collection_service`, `worker`, `session_controller` (for deck_save_dir)
5. Add state: collection cache info, last refresh timestamp
6. Update `AppController.__init__` to create `CollectionController` instance
7. Delegate collection operations to new controller
8. Update `run_initial_loads()` to use delegated methods

**Verification:**
- [ ] Collection loads from cache on startup
- [ ] Collection refresh from MTGO works
- [ ] Error messages display correctly
- [ ] UI updates after collection load

**Rollback:** Git revert the commit

**Risk Level:** Medium - Involves async operations and UI callbacks

---

## Step 9: Extract CollectionController - Part 2 (MTGO Bridge Status)

**Objective:** Move MTGO bridge status checking to CollectionController

**Principle Addressed:** SRP - MTGO bridge is collection infrastructure

**Prerequisites:** Step 8

**Files Affected:**
- `controllers/collection_controller.py`
- `controllers/mtgo_coordinator.py`
- `controllers/app_controller.py`

**Actions:**
1. Move `check_mtgo_bridge_status()` from `AppController` (lines 346-370) to `CollectionController`
2. Update `MtgoCoordinator.__init__` to accept `collection_controller` instead of `status_check` callback
3. Update `MtgoCoordinator.start_status_monitoring()` to call `collection_controller.check_mtgo_bridge_status()`
4. Update `AppController.__init__` to inject `collection_controller` into `MtgoCoordinator`
5. Remove `check_mtgo_bridge_status()` from `AppController`

**Verification:**
- [ ] MTGO status checks run periodically
- [ ] UI buttons enable/disable based on MTGO status
- [ ] No crashes when MTGO not running

**Rollback:** Git revert the commit

**Risk Level:** Medium - Cross-coordinator dependency, background threading

---

## Step 10: Consolidate BulkDataCoordinator into CardRepository

**Objective:** Simplify by moving bulk data coordination closer to card data ownership

**Principle Addressed:** Cohesion - Bulk data is card repository's concern

**Prerequisites:** Step 5 (renamed to coordinator)

**Files Affected:**
- `controllers/bulk_data_coordinator.py` (DELETE)
- `repositories/card_repository.py`
- `controllers/app_controller.py`

**Actions:**
1. Move `BulkDataCoordinator` methods to `CardRepository` as:
   - `check_and_download_bulk_data(worker, callbacks, frame_provider)`
   - `force_bulk_data_update(worker, callbacks)`
   - `load_bulk_data_into_memory(worker, on_status, force, frame_provider)`
2. Update `CardRepository` to accept `image_service` in constructor
3. Update `AppController.__init__` to remove `_bulk_data_coordinator`
4. Update `AppController` methods to delegate to `card_repo.check_and_download_bulk_data(...)` etc.
5. Delete `bulk_data_coordinator.py`

**Verification:**
- [ ] Bulk data check runs on startup
- [ ] Force update from toolbar works
- [ ] Progress indicators display
- [ ] Bulk data loads into memory correctly

**Rollback:** Git revert the commit

**Risk Level:** Medium - Changes data layer, involves background tasks

---

## Step 11: Add Async Method Naming Convention

**Objective:** Clarify which methods are async/background operations

**Principle Addressed:** Nomenclature clarity

**Prerequisites:** Steps 3, 4, 8, 9 (all controllers extracted)

**Files Affected:**
- `controllers/archetype_controller.py`
- `controllers/deck_controller.py`
- `controllers/collection_controller.py`

**Actions:**
1. Rename async methods to include `_async` suffix:
   - `fetch_archetypes()` -> `fetch_archetypes_async()`
   - `load_decks_for_archetype()` -> `load_decks_for_archetype_async()`
   - `download_deck()` -> `download_deck_async()`
   - `build_daily_average_deck()` -> `build_daily_average_async()`
   - `refresh_collection_from_bridge()` -> `refresh_collection_async()`
2. Update all call sites in `AppController` facade
3. Update all call sites in `app_frame.py`

**Verification:**
- [ ] All renamed methods still work
- [ ] No broken references

**Rollback:** Git revert the commit

**Risk Level:** Low-Medium - Mechanical rename but many call sites

---

### Phase 3: Refactor AppController as Facade (Medium-High Risk)

---

## Step 12: Create AppController Facade Structure

**Objective:** Transform AppController into thin delegation layer

**Principle Addressed:** SRP - AppController becomes coordinator, not implementer

**Prerequisites:** Steps 1, 3, 4, 8, 9 (all controllers extracted)

**Files Affected:**
- `controllers/app_controller.py`

**Actions:**
1. Remove all moved methods from `AppController`
2. Keep only:
   - `__init__()` - Creates sub-controllers
   - Delegation methods (thin wrappers to sub-controllers)
   - `create_frame()` - Frame factory
   - `run_initial_loads()` - Orchestration
   - `shutdown()` - Lifecycle
3. Add controller references:
   - `self.session_ctrl: SessionController`
   - `self.archetype_ctrl: ArchetypeController`
   - `self.deck_ctrl: DeckController`
   - `self.collection_ctrl: CollectionController`
4. Implement delegation methods:
   ```python
   def fetch_archetypes_async(self, on_success, on_error, on_status, force=False):
       return self.archetype_ctrl.fetch_archetypes_async(
           on_success=on_success,
           on_error=on_error,
           on_status=on_status,
           force=force
       )
   ```
5. Update `run_initial_loads()` to orchestrate across controllers

**Verification:**
- [ ] All existing functionality works
- [ ] AppController is under 200 lines
- [ ] No business logic remains in AppController
- [ ] Startup sequence works correctly

**Rollback:** Git revert the commit

**Risk Level:** Medium-High - Major refactoring of central class

---

## Step 13: Simplify AppController Constructor

**Objective:** Reduce constructor complexity by using factory pattern for sub-controllers

**Principle Addressed:** DIP - Depend on abstractions, reduce coupling

**Prerequisites:** Step 12

**Files Affected:**
- `controllers/app_controller.py`
- `controllers/session_controller.py`
- `controllers/archetype_controller.py`
- `controllers/deck_controller.py`
- `controllers/collection_controller.py`

**Actions:**
1. Add factory functions to each controller module:
   - `get_session_controller(deck_repo)`
   - `get_archetype_controller(workflow_service, worker, session_ctrl)`
   - `get_deck_controller(workflow_service, deck_repo, worker, session_ctrl)`
   - `get_collection_controller(collection_service, worker, session_ctrl)`
2. Update `AppController.__init__` to use factories instead of direct instantiation
3. Keep dependency injection optional (for testing):
   ```python
   self.session_ctrl = session_controller or get_session_controller(self.deck_repo)
   ```

**Verification:**
- [ ] Application starts correctly
- [ ] All controllers initialize properly
- [ ] Dependency injection still works for tests

**Rollback:** Git revert the commit

**Risk Level:** Low-Medium - Simplification, but changes initialization

---

## Step 14: Extract Stores Management to SessionController

**Objective:** Move store loading to session controller (settings concern)

**Principle Addressed:** SRP - Stores are configuration/session data

**Prerequisites:** Step 1 (SessionController exists)

**Files Affected:**
- `controllers/session_controller.py`
- `controllers/app_controller.py`

**Actions:**
1. Move store loading from `AppController.__init__` (lines 110-116) to `SessionController`
2. Add methods to `SessionController`:
   - `load_stores()` - Loads notes, outboard, guide stores
   - `get_deck_notes_store() / get_outboard_store() / get_guide_store()`
   - `get_notes_store_path()` etc.
3. Inject `store_service` into `SessionController`
4. Update `AppController.__init__` to get stores from `session_ctrl`
5. Update `app_frame.py` to access stores through `controller.session_ctrl`

**Verification:**
- [ ] Deck notes load correctly
- [ ] Outboard cards persist
- [ ] Sideboard guides save/restore

**Rollback:** Git revert the commit

**Risk Level:** Low-Medium - Move data, but straightforward delegation

---

## Step 15: Move Zone Cards State to DeckController

**Objective:** Consolidate deck-related state in one place

**Principle Addressed:** Cohesion - Zone cards are deck workspace state

**Prerequisites:** Step 4 (DeckController exists)

**Files Affected:**
- `controllers/deck_controller.py`
- `controllers/app_controller.py`
- `controllers/session_controller.py`

**Actions:**
1. Move `zone_cards` state from `AppController` (line 99) to `DeckController`
2. Move `sideboard_guide_entries` and `sideboard_exclusions` (lines 100-101) to `DeckController`
3. Update `SessionController.save()` to accept `zone_cards` from `DeckController`
4. Update `SessionController.restore_session_state()` to return zone cards for injection
5. Update `AppController` to delegate zone card access to `deck_ctrl`
6. Update `app_frame.py` to access zone cards through `controller.deck_ctrl`

**Verification:**
- [ ] Zone cards save/restore on app restart
- [ ] Deck builder grid updates correctly
- [ ] Sideboard guide persists

**Rollback:** Git revert the commit

**Risk Level:** Medium - Touches session persistence and UI integration

---

### Phase 4: Cleanup and Optimization (Low-Medium Risk)

---

## Step 16: Remove Duplicate Worker Submission Code

**Objective:** Use BaseAsyncController pattern consistently

**Principle Addressed:** DRY - Eliminate duplicate threading code

**Prerequisites:** Step 2 (BaseAsyncController exists), Steps 3-4, 8-9 (controllers extracted)

**Files Affected:**
- `controllers/base_async_controller.py`
- `controllers/archetype_controller.py`
- `controllers/deck_controller.py`
- `controllers/collection_controller.py`

**Actions:**
1. Enhance `BaseAsyncController.submit_task()` to handle loading flags:
   ```python
   def submit_task(self, flag_name, worker_fn, on_success, on_error):
       with self._loading_lock:
           if getattr(self, flag_name):
               return
           setattr(self, flag_name, True)

       def _success_handler(result):
           with self._loading_lock:
               setattr(self, flag_name, False)
           on_success(result)

       def _error_handler(error):
           with self._loading_lock:
               setattr(self, flag_name, False)
           on_error(error)

       self._worker.submit(worker_fn, on_success=_success_handler, on_error=_error_handler)
   ```
2. Refactor all async methods in controllers to use `submit_task()`
3. Remove duplicate lock/flag management code

**Verification:**
- [ ] All async operations still work
- [ ] Loading flags prevent duplicate submissions
- [ ] Error handlers reset flags correctly

**Rollback:** Git revert the commit

**Risk Level:** Medium - Changes threading logic, potential race conditions

---

## Step 17: Consolidate Callback Registration

**Objective:** Simplify how UI callbacks are registered with controllers

**Principle Addressed:** DRY - Single callback registration pattern

**Prerequisites:** Step 12 (AppController is facade)

**Files Affected:**
- `controllers/app_controller.py`
- `controllers/ui_callbacks.py`

**Actions:**
1. Add `register_ui_callbacks(callbacks: dict)` to `AppController`
2. Distribute callbacks to sub-controllers:
   ```python
   def register_ui_callbacks(self, callbacks: dict):
       self.archetype_ctrl.set_callbacks(callbacks)
       self.deck_ctrl.set_callbacks(callbacks)
       self.collection_ctrl.set_callbacks(callbacks)
       self._ui_callbacks = callbacks
   ```
3. Update sub-controllers to have `set_callbacks()` method
4. Update `create_frame()` to call `register_ui_callbacks()` once
5. Remove scattered callback passing in method signatures

**Verification:**
- [ ] All UI updates work (status, errors, success messages)
- [ ] Callbacks registered correctly
- [ ] No null reference errors

**Rollback:** Git revert the commit

**Risk Level:** Medium - Changes callback mechanism, many integration points

---

## Step 18: Add Type Hints to All Controller Interfaces

**Objective:** Improve IDE support and catch type errors

**Principle Addressed:** Maintainability - Clear contracts

**Prerequisites:** Steps 1, 3, 4, 8, 9 (all controllers exist)

**Files Affected:**
- All controller files in `controllers/`

**Actions:**
1. Add `from __future__ import annotations` to all controller files
2. Add complete type hints to:
   - All method signatures
   - All constructor parameters
   - All return types
3. Use `typing.Protocol` for callback types:
   ```python
   from typing import Protocol

   class StatusCallback(Protocol):
       def __call__(self, message: str) -> None: ...
   ```
4. Add type hints to state variables
5. Run mypy to verify type correctness

**Verification:**
- [ ] mypy passes (or shows only acceptable warnings)
- [ ] IDE autocomplete works
- [ ] No runtime errors from type hints

**Rollback:** Git revert the commit

**Risk Level:** Low - Non-functional improvement

---

## Step 19: Add Controller Documentation

**Objective:** Document responsibility and usage of each controller

**Principle Addressed:** Maintainability - Clear documentation

**Prerequisites:** Steps 1, 3, 4, 8, 9 (all controllers exist)

**Files Affected:**
- All controller files in `controllers/`
- `docs/ARCHITECTURE.md` (NEW)

**Actions:**
1. Add module-level docstrings to all controllers explaining:
   - Responsibility
   - Key methods
   - State managed
   - Dependencies
2. Add class-level docstrings with usage examples
3. Add method docstrings with parameter descriptions
4. Create `/docs/ARCHITECTURE.md` documenting:
   - Controller architecture diagram
   - Responsibility matrix
   - Data flow diagrams
   - Usage examples

**Verification:**
- [ ] All public methods documented
- [ ] Architecture doc is accurate
- [ ] Examples are runnable

**Rollback:** Git revert the commit

**Risk Level:** Low - Documentation only

---

## Step 20: Extract UI Callback Types to Shared Module

**Objective:** Centralize callback type definitions

**Principle Addressed:** DRY - Single source of truth for callback signatures

**Prerequisites:** Step 18 (type hints added)

**Files Affected:**
- `controllers/callback_types.py` (NEW)
- All controller files

**Actions:**
1. Create `controllers/callback_types.py`
2. Define callback protocols:
   ```python
   class OnStatus(Protocol):
       def __call__(self, message: str) -> None: ...

   class OnSuccess[T](Protocol):
       def __call__(self, result: T) -> None: ...

   class OnError(Protocol):
       def __call__(self, error: Exception) -> None: ...

   class OnProgress(Protocol):
       def __call__(self, current: int, total: int) -> None: ...
   ```
3. Update all controllers to import and use these types
4. Update `UICallbackBuilder` to use these types

**Verification:**
- [ ] All imports resolve
- [ ] Type checking passes
- [ ] Callback signatures are consistent

**Rollback:** Git revert the commit

**Risk Level:** Low - Type definition consolidation

---

### Phase 5: Integration and Testing (Medium Risk)

---

## Step 21: Update AppFrame to Use Facade Pattern

**Objective:** Simplify AppFrame by using AppController facade exclusively

**Principle Addressed:** DIP - Depend on facade abstraction, not individual controllers

**Prerequisites:** Step 12 (AppController is facade)

**Files Affected:**
- `widgets/app_frame.py`

**Actions:**
1. Audit all `self.controller.*` references in `app_frame.py`
2. Replace direct sub-controller access with facade methods:
   - `self.controller.session_ctrl.get_current_format()` -> `self.controller.get_current_format()`
   - `self.controller.deck_ctrl.get_zone_cards()` -> `self.controller.get_zone_cards()`
3. Add facade delegation methods to `AppController` as needed
4. Keep repository/service access as-is (data layer can be accessed directly)

**Verification:**
- [ ] All UI functionality works
- [ ] No direct sub-controller access from UI (except repos/services)
- [ ] Code is more readable

**Rollback:** Git revert the commit

**Risk Level:** Medium - Many UI integration points

---

## Step 22: Add Integration Tests for Controllers

**Objective:** Prevent regression and document usage

**Principle Addressed:** Maintainability - Automated verification

**Prerequisites:** All previous steps

**Files Affected:**
- `tests/test_session_controller.py` (NEW)
- `tests/test_archetype_controller.py` (NEW)
- `tests/test_deck_controller.py` (NEW)
- `tests/test_collection_controller.py` (NEW)
- `tests/test_app_controller_integration.py` (NEW)

**Actions:**
1. Create test file for each controller
2. Test key scenarios:
   - **SessionController:** Save/restore settings, format switching
   - **ArchetypeController:** Fetch archetypes, load decks, error handling
   - **DeckController:** Download deck, save deck, daily average
   - **CollectionController:** Cache load, bridge refresh, status check
   - **AppController:** Integration test of full startup sequence
3. Use mocks for external dependencies (network, file I/O)
4. Test async operations complete correctly
5. Test error paths

**Verification:**
- [ ] All tests pass
- [ ] Test coverage > 80% for controllers
- [ ] Tests run in < 10 seconds

**Rollback:** Git revert the commit (tests only)

**Risk Level:** Low - New tests, no production code changes

---

## Risk Assessment

### Overall Risk Level: Medium

**Mitigation Strategies:**

1. **Incremental Commits:** Each step is a separate commit that can be reverted
2. **Feature Freeze:** No new features during refactoring
3. **Continuous Testing:** Run full test suite after each step
4. **Parallel Branch:** Perform refactoring in feature branch, merge when complete
5. **Code Review:** Each phase reviewed before proceeding to next
6. **Manual Testing:** Test key user workflows after each phase

**Specific Risks:**

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Breaking UI integration | Medium | High | Thorough testing of app_frame after each controller extraction |
| Race conditions in async code | Low | High | Careful review of BaseAsyncController pattern, add threading tests |
| Session restore failures | Low | Medium | Test session save/restore explicitly in Step 1 |
| Callback registration errors | Medium | Medium | Consolidate callbacks early (Step 17) |
| Import circular dependencies | Low | Medium | Controllers depend on repos/services, never on each other |

## Success Metrics

**Quantitative:**
- [ ] AppController reduced from 555 lines to < 200 lines
- [ ] Each specialized controller < 200 lines
- [ ] Test coverage for controllers > 80%
- [ ] No increase in cyclomatic complexity in any file
- [ ] All existing tests pass

**Qualitative:**
- [ ] Each controller has single, clear responsibility
- [ ] New features can be added to single controller
- [ ] UI can be tested by mocking AppController facade
- [ ] Controllers can be unit tested independently
- [ ] Code is more navigable (find functionality by domain)

**Behavioral:**
- [ ] Application starts correctly
- [ ] All user workflows function identically
- [ ] No performance degradation
- [ ] No new error messages in logs
- [ ] Session save/restore works
- [ ] Background tasks continue running

## Files Summary

**New Files (7):**
- `controllers/base_async_controller.py`
- `controllers/session_controller.py`
- `controllers/archetype_controller.py`
- `controllers/deck_controller.py`
- `controllers/collection_controller.py`
- `controllers/callback_types.py`
- `docs/ARCHITECTURE.md`

**Renamed Files (3):**
- `bulk_data_helpers.py` -> `bulk_data_coordinator.py`
- `mtgo_background_helpers.py` -> `mtgo_coordinator.py`
- `app_controller_helpers.py` -> `ui_callbacks.py`

**Deleted Files (1):**
- `bulk_data_coordinator.py` (consolidated into CardRepository in Step 10)

**Modified Files (5+):**
- `controllers/app_controller.py` (major refactoring)
- `repositories/card_repository.py` (absorbs bulk data coordination)
- `widgets/app_frame.py` (updated integration)
- All controller files (documentation, type hints)
- Test files (new tests)

## Implementation Timeline

**Phase 1 (Foundation):** 4-5 hours
- Steps 1-4: Controller extraction
- Steps 5-7: Nomenclature cleanup

**Phase 2 (Complex Concerns):** 3-4 hours
- Steps 8-11: Collection controller and naming

**Phase 3 (Facade):** 4-5 hours
- Steps 12-15: AppController transformation

**Phase 4 (Cleanup):** 2-3 hours
- Steps 16-20: DRY elimination and documentation

**Phase 5 (Integration):** 3-4 hours
- Steps 21-22: UI integration and testing

**Total Estimated Time:** 16-21 hours

## Conclusion

This refactoring transforms a monolithic 555-line controller into a clean, modular architecture with specialized controllers, each under 200 lines and with a single responsibility. The incremental approach minimizes risk while achieving significant improvements in maintainability, testability, and code clarity.

The refactored architecture will support future enhancements more easily, such as:
- Alternative archetype sources (17Lands, etc.)
- Additional collection providers (MTG Arena, etc.)
- New deck analysis features
- Extended session management (user profiles, etc.)

Each step is atomic, reversible, and independently verifiable, ensuring the codebase remains stable throughout the refactoring process.
