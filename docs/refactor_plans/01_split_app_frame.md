# Refactoring Plan: AppFrame God Class Decomposition

## Executive Summary

**Objective:** Break down the `AppFrame` god class (562 lines) into smaller, focused classes following Single Responsibility Principle while maintaining all functionality and testability.

**Current State:**
- `AppFrame` inherits from 3 mixins (`AppEventHandlers`, `SideboardGuideHandlers`, `CardTablePanelHandler`) + `wx.Frame`
- Contains 50+ methods across 6 different responsibility areas
- Manages UI construction, event coordination, deck operations, state persistence, dialog lifecycle, and card inspection
- Heavy coupling to controller and numerous wxPython widgets

**Target State:**
- 4-5 focused classes with clear responsibilities
- Thin `AppFrame` coordinator that delegates to specialized components
- Improved testability through dependency injection
- Maintained backward compatibility during transition
- Zero breaking changes to external callers (controller, tests)

**Total Effort:** ~15-20 steps, estimated 12-16 hours of implementation time

---

## Issues Identified

### SOLID Principle Violations

**1. Single Responsibility Principle (SRP) - CRITICAL**
- `AppFrame` has 6+ distinct responsibilities:
  - UI widget construction and layout (lines 94-384)
  - Event handling and callbacks (via `AppEventHandlers` mixin)
  - Window state persistence (lines 453-488)
  - Dialog lifecycle management (lines 74-79, 460-494 in handlers)
  - Deck zone manipulation (via `CardTablePanelHandler` mixin)
  - Sideboard guide management (via `SideboardGuideHandlers` mixin)

**2. Open/Closed Principle (OCP) - MEDIUM**
- Adding new panels/tabs requires modifying `_build_deck_workspace()` and `_build_left_panel()`
- New dialog types require adding new `*_window` attributes to `__init__`
- No extension points for custom UI sections

**3. Dependency Inversion Principle (DIP) - MEDIUM**
- Direct instantiation of panels, dialogs, and widgets throughout construction
- Hard-coded dependencies on specific panel classes
- No abstraction layer for child window management

### DRY Violations

**1. Repeated Dialog Management Pattern**
- Lines 74-79: `tracker_window`, `timer_window`, `history_window`, `metagame_window`, `mana_keyboard_window` all follow same pattern
- Lines 204-211 in `on_close()`: Duplicated cleanup logic for each dialog
- Similar pattern in `open_*` handlers (lines 460-494 in `app_event_handlers.py`)

**2. Repeated wx.CallAfter Marshalling**
- Every async callback wraps UI updates in `wx.CallAfter`
- Pattern repeated 20+ times across event handlers

**3. State Persistence Duplication**
- Window settings save logic (lines 453-488)
- Deck state save logic (via `_schedule_settings_save()` called from multiple locations)

### Maintainability Issues

**1. High Coupling**
- `AppFrame` directly references 15+ panel/widget classes
- Deep knowledge of controller internal structure
- Tight binding to wxPython event system

**2. Low Cohesion**
- UI construction methods mixed with event handlers
- Dialog management scattered across frame and mixins
- State restoration logic interleaved with UI construction

**3. Testability Barriers**
- Cannot test UI construction without creating full wxPython app
- Cannot test event coordination without full widget tree
- Hard to mock dependencies due to direct instantiation

### Nomenclature Issues

**1. Inconsistent Naming**
- `left_stack` vs `zone_notebook` vs `deck_tabs` (all notebooks but different names)
- `research_panel` vs `builder_panel` vs `sideboard_guide_panel` (inconsistent `_panel` suffix)
- `tracker_window` vs `timer_window` (all dialogs but called windows)

**2. Missing Abstractions**
- No clear naming for "child dialog management" concept
- "Workspace" used only once in `_build_deck_workspace()` but concept exists elsewhere

---

## Refactoring Steps

### Phase 1: Extract Dialog Manager (Low Risk)

#### Step 1: Create DialogManager class

**Objective:** Extract all child window lifecycle management into a dedicated class.

**Principle Addressed:** Single Responsibility Principle (SRP) - Separate dialog management from frame responsibilities.

**Prerequisites:** None

**Files Affected:**
- `widgets/managers/dialog_manager.py` (NEW)

**Actions:**
1. Create `widgets/managers/dialog_manager.py`
2. Define `DialogManager` class with methods:
   - `__init__(parent: wx.Window)`
   - `open_window(attr_name: str, window_class: type, title: str, on_close: Callable) -> wx.Window`
   - `close_all() -> None`
   - `get_window(attr_name: str) -> wx.Window | None`
3. Add internal `_windows: dict[str, wx.Window]` to track managed windows
4. Implement cleanup logic for destroying windows

**Verification:**
- [ ] `DialogManager` class compiles and imports successfully
- [ ] Type hints are correct and mypy passes
- [ ] No runtime dependencies on wxPython (except type hints)

**Rollback:** Delete `widgets/managers/dialog_manager.py`

**Risk Level:** Low - New file, no existing code modified

---

#### Step 2: Implement DialogManager core functionality

**Objective:** Add window lifecycle methods to DialogManager with proper event binding.

**Principle Addressed:** SRP - Complete dialog management abstraction.

**Prerequisites:** Step 1

**Files Affected:**
- `widgets/managers/dialog_manager.py`

**Actions:**
1. Implement `open_window()`:
   - Check if window already exists and is shown
   - Create new window instance if needed
   - Bind close event to cleanup callback
   - Store in `_windows` dict
   - Call `Show()` and `Raise()`
2. Implement `close_all()`:
   - Iterate through `_windows`
   - Check if widget still exists using `widget_exists()` helper
   - Call `Destroy()` on each window
   - Clear `_windows` dict
3. Implement `get_window()` to retrieve existing window references

**Verification:**
- [ ] Unit tests pass for `DialogManager` (create new test file)
- [ ] Memory leaks checked - windows properly destroyed
- [ ] No circular references between parent and dialogs

**Rollback:** Revert changes to `widgets/managers/dialog_manager.py`

**Risk Level:** Low - Still isolated, no integration yet

---

#### Step 3: Integrate DialogManager into AppFrame

**Objective:** Replace manual dialog tracking with DialogManager instance.

**Principle Addressed:** DRY - Eliminate duplicated dialog management code.

**Prerequisites:** Step 2

**Files Affected:**
- `widgets/app_frame.py` (lines 74-79, 88-91, 200-214)
- `widgets/handlers/app_event_handlers.py` (lines 460-494)

**Actions:**
1. In `AppFrame.__init__()`:
   - Add `from widgets.managers.dialog_manager import DialogManager`
   - Replace individual `*_window` attributes with: `self._dialog_manager = DialogManager(self)`
   - Keep attributes as properties for backward compatibility:
     ```python
     @property
     def tracker_window(self):
         return self._dialog_manager.get_window('tracker_window')
     ```
2. Update `open_opponent_tracker()`, `open_timer_alert()`, `open_match_history()`, `open_metagame_analysis()`:
   - Replace `open_child_window()` calls with `self._dialog_manager.open_window()`
3. Update `on_close()`:
   - Replace manual window cleanup with `self._dialog_manager.close_all()`
4. Update `_on_mana_keyboard_closed()` and `_open_full_mana_keyboard()`:
   - Integrate mana keyboard into dialog manager

**Verification:**
- [ ] All dialog windows open correctly
- [ ] Dialogs close properly when frame closes
- [ ] No memory leaks or hanging windows
- [ ] Existing tests still pass

**Rollback:** Revert changes, restore manual window tracking

**Risk Level:** Medium - Modifies core frame functionality, but well-contained change

---

### Phase 2: Extract UI Builder (Medium Risk)

#### Step 4: Create AppFrameBuilder class skeleton

**Objective:** Create a builder class responsible for all UI construction.

**Principle Addressed:** SRP - Separate UI construction from frame coordination.

**Prerequisites:** Step 3

**Files Affected:**
- `widgets/builders/app_frame_builder.py` (NEW)

**Actions:**
1. Create `widgets/builders/app_frame_builder.py`
2. Define `AppFrameBuilder` class:
   ```python
   class AppFrameBuilder:
       def __init__(
           self,
           frame: wx.Frame,
           controller: AppController,
           mana_icons: ManaIconFactory,
       ):
           self.frame = frame
           self.controller = controller
           self.mana_icons = mana_icons
   ```
3. Add type hints and imports
4. Add placeholder methods for each UI section (no implementation yet):
   - `build_status_bar() -> wx.StatusBar`
   - `build_left_panel(parent: wx.Window) -> wx.Panel`
   - `build_right_panel(parent: wx.Window) -> wx.Panel`
   - `build_toolbar(parent: wx.Window) -> ToolbarButtons`
   - `build_card_data_controls(parent: wx.Window) -> wx.Panel`
   - `build_deck_workspace(parent: wx.Window) -> wx.StaticBoxSizer`
   - `build_card_inspector(parent: wx.Window) -> wx.StaticBoxSizer`
   - `build_deck_results(parent: wx.Window) -> wx.StaticBoxSizer`

**Verification:**
- [ ] File compiles without errors
- [ ] Type hints are correct
- [ ] No runtime impact (class not used yet)

**Rollback:** Delete `widgets/builders/app_frame_builder.py`

**Risk Level:** Low - New file, no integration

---

#### Step 5: Move UI construction methods to AppFrameBuilder

**Objective:** Migrate all UI construction logic from AppFrame to AppFrameBuilder.

**Principle Addressed:** SRP - Complete separation of UI construction responsibility.

**Prerequisites:** Step 4

**Files Affected:**
- `widgets/builders/app_frame_builder.py`
- `widgets/app_frame.py` (lines 94-384)

**Actions:**
1. Copy method implementations from `AppFrame` to `AppFrameBuilder`:
   - `_setup_status_bar()` -> `build_status_bar()`
   - `_build_left_panel()` -> `build_left_panel()`
   - `_build_right_panel()` -> `build_right_panel()`
   - `_build_toolbar()` -> `build_toolbar()`
   - `_build_card_data_controls()` -> `build_card_data_controls()`
   - `_build_deck_workspace()` -> `build_deck_workspace()`
   - `_build_card_inspector()` -> `build_card_inspector()`
   - `_build_deck_results()` -> `build_deck_results()`
   - `_build_deck_tables_tab()` -> `build_deck_tables_tab()`
   - `_create_zone_table()` -> `create_zone_table()`
   - `_create_notebook()` -> `create_notebook()`
2. Update method signatures to accept required callbacks as parameters
3. Add return type hints with constructed widget references
4. Create a `BuildResult` dataclass to return all widget references:
   ```python
   @dataclass
   class AppFrameWidgets:
       status_bar: wx.StatusBar
       left_stack: wx.Simplebook
       research_panel: DeckResearchPanel
       builder_panel: DeckBuilderPanel
       toolbar: ToolbarButtons
       deck_source_choice: wx.Choice
       zone_notebook: fnb.FlatNotebook
       main_table: CardTablePanel
       side_table: CardTablePanel
       out_table: CardTablePanel | None
       deck_tabs: fnb.FlatNotebook
       deck_stats_panel: DeckStatsPanel
       sideboard_guide_panel: SideboardGuidePanel
       deck_notes_panel: DeckNotesPanel
       card_inspector_panel: CardInspectorPanel
       summary_text: wx.TextCtrl
       deck_list: wx.ListBox
       deck_action_buttons: DeckActionButtons
       collection_status_label: wx.StaticText
   ```
5. Implement `build_all() -> AppFrameWidgets` method that orchestrates entire UI build

**Verification:**
- [ ] All UI methods exist in AppFrameBuilder
- [ ] Methods compile without errors
- [ ] Type hints match original implementations
- [ ] No runtime changes yet (methods not called)

**Rollback:** Revert changes to `app_frame_builder.py`

**Risk Level:** Low - Code duplication, no behavior change yet

---

#### Step 6: Wire AppFrameBuilder into AppFrame

**Objective:** Replace AppFrame's UI construction with builder delegation.

**Principle Addressed:** Open/Closed Principle - Frame now delegates to builder, extensible through builder subclassing.

**Prerequisites:** Step 5

**Files Affected:**
- `widgets/app_frame.py` (lines 83-84, 94-384)

**Actions:**
1. In `AppFrame.__init__()`:
   - Create builder: `builder = AppFrameBuilder(self, controller, self.mana_icons)`
   - Replace `self._build_ui()` with: `widgets = builder.build_all()`
   - Store widget references: `self._widgets = widgets`
   - Create properties for backward compatibility:
     ```python
     @property
     def research_panel(self):
         return self._widgets.research_panel
     # ... repeat for all widgets
     ```
2. Delete original `_build_ui()` and all `_build_*()` methods from `AppFrame`
3. Update any direct references to use properties instead

**Verification:**
- [ ] Application launches successfully
- [ ] All UI elements display correctly
- [ ] All interactions work (button clicks, selections, etc.)
- [ ] No visual regressions
- [ ] Memory usage similar to before

**Rollback:** Revert `AppFrame.__init__()`, restore original `_build_ui()` methods

**Risk Level:** Medium-High - Major architectural change, but behavior should be identical

---

### Phase 3: Extract Event Coordinator (Medium Risk)

#### Step 7: Create AppEventCoordinator class skeleton

**Objective:** Create coordinator class for event handling and marshalling.

**Principle Addressed:** SRP - Separate event coordination from UI and frame management.

**Prerequisites:** Step 6

**Files Affected:**
- `widgets/coordinators/app_event_coordinator.py` (NEW)

**Actions:**
1. Create `widgets/coordinators/app_event_coordinator.py`
2. Define `AppEventCoordinator` class:
   ```python
   class AppEventCoordinator:
       def __init__(
           self,
           frame: AppFrame,
           controller: AppController,
           widgets: AppFrameWidgets,
       ):
           self.frame = frame
           self.controller = controller
           self.widgets = widgets
   ```
3. Add placeholder methods for each event handler category:
   - `setup_event_bindings() -> None`
   - `on_format_changed() -> None`
   - `on_archetype_filter() -> None`
   - `on_deck_selected(event) -> None`
   - ... (all event handlers from `AppEventHandlers`)
4. Add helper methods for async marshalling:
   - `call_after(callback, *args) -> None` - Wraps `wx.CallAfter`
   - `run_in_background(work_fn, on_success, on_error) -> None`

**Verification:**
- [ ] File compiles without errors
- [ ] Type hints are correct
- [ ] No runtime impact yet

**Rollback:** Delete `widgets/coordinators/app_event_coordinator.py`

**Risk Level:** Low - New file, no integration

---

#### Step 8: Move event handlers to AppEventCoordinator

**Objective:** Migrate all event handling logic from mixins to coordinator.

**Principle Addressed:** SRP - Centralize event coordination in single class.

**Prerequisites:** Step 7

**Files Affected:**
- `widgets/coordinators/app_event_coordinator.py`
- `widgets/handlers/app_event_handlers.py` (entire file)

**Actions:**
1. Copy all event handler methods from `AppEventHandlers` to `AppEventCoordinator`:
   - `on_format_changed()`
   - `on_archetype_filter()`
   - `on_archetype_selected()`
   - `on_deck_selected()`
   - `on_daily_average_clicked()`
   - `on_copy_clicked()`
   - `on_save_clicked()`
   - `on_window_change()`
   - `on_close()`
   - All `_on_*` async callback handlers
   - All builder panel handlers
2. Update references from `self` to `self.frame` or `self.widgets` as appropriate
3. Replace `self.controller` references with direct controller access
4. Implement `setup_event_bindings()` to bind all wx events:
   ```python
   def setup_event_bindings(self):
       self.frame.Bind(wx.EVT_CLOSE, self.on_close)
       self.frame.Bind(wx.EVT_SIZE, self.on_window_change)
       self.frame.Bind(wx.EVT_MOVE, self.on_window_change)
       self.frame.Bind(wx.EVT_CHAR_HOOK, self._on_hotkey)
       self.widgets.deck_list.Bind(wx.EVT_LISTBOX, self.on_deck_selected)
       # ... etc
   ```

**Verification:**
- [ ] All event handlers exist in coordinator
- [ ] Methods compile without errors
- [ ] Type hints are correct
- [ ] No runtime changes yet (not integrated)

**Rollback:** Revert changes to coordinator file

**Risk Level:** Low - Code duplication, no behavior change

---

#### Step 9: Wire AppEventCoordinator into AppFrame

**Objective:** Replace mixin inheritance with coordinator delegation.

**Principle Addressed:** Dependency Inversion - Frame depends on coordinator abstraction instead of inheriting implementation.

**Prerequisites:** Step 8

**Files Affected:**
- `widgets/app_frame.py` (line 49, throughout event handlers)
- `widgets/handlers/app_event_handlers.py` (mark as deprecated)

**Actions:**
1. In `AppFrame`:
   - Remove `AppEventHandlers` from class inheritance list
   - In `__init__()` after builder: `self._event_coordinator = AppEventCoordinator(self, controller, widgets)`
   - Call `self._event_coordinator.setup_event_bindings()`
   - Create delegation properties for methods called from controller:
     ```python
     def _on_archetypes_loaded(self, archetypes):
         return self._event_coordinator._on_archetypes_loaded(archetypes)
     ```
2. Update `AppControllerUIHelpers` to call coordinator methods directly if possible
3. Keep `AppEventHandlers` file but add deprecation comment

**Verification:**
- [ ] All events trigger correctly
- [ ] Button clicks, selections, window events work
- [ ] Async callbacks execute properly
- [ ] No regression in event handling behavior

**Rollback:** Restore mixin inheritance, remove coordinator instantiation

**Risk Level:** Medium-High - Changes event flow, requires thorough testing

---

### Phase 4: Extract Remaining Mixins (Medium Risk)

#### Step 10: Move CardTablePanelHandler to coordinator

**Objective:** Consolidate zone editing logic into event coordinator.

**Principle Addressed:** SRP - Zone manipulation is event-driven coordination.

**Prerequisites:** Step 9

**Files Affected:**
- `widgets/coordinators/app_event_coordinator.py`
- `widgets/handlers/card_table_panel_handler.py`
- `widgets/app_frame.py` (line 49)

**Actions:**
1. Copy all methods from `CardTablePanelHandler` to `AppEventCoordinator`:
   - `_after_zone_change()`
   - `_handle_zone_delta()`
   - `_handle_zone_remove()`
   - `_handle_zone_add()`
   - `_on_hotkey()`
   - All keyboard shortcut handlers
   - Card focus/hover handlers
2. Update `AppFrame`:
   - Remove `CardTablePanelHandler` from inheritance
   - Update zone table creation to pass coordinator callbacks
3. Keep original file with deprecation notice

**Verification:**
- [ ] Zone operations work (add/remove cards, +/- buttons)
- [ ] Keyboard shortcuts function (Ctrl+1, Ctrl+2, Ctrl+D, Ctrl+R)
- [ ] Card focus and hover still trigger inspector updates
- [ ] Undo/redo operations work correctly

**Rollback:** Restore mixin inheritance

**Risk Level:** Medium - Complex interactions with multiple tables

---

#### Step 11: Move SideboardGuideHandlers to coordinator

**Objective:** Consolidate sideboard guide logic into event coordinator.

**Principle Addressed:** SRP - Sideboard guide management is event coordination.

**Prerequisites:** Step 10

**Files Affected:**
- `widgets/coordinators/app_event_coordinator.py`
- `widgets/handlers/sideboard_guide_handlers.py`
- `widgets/app_frame.py` (line 49)

**Actions:**
1. Copy all methods from `SideboardGuideHandlers` to `AppEventCoordinator`:
   - `_persist_outboard_for_current()`
   - `_load_outboard_for_current()`
   - `_load_guide_for_current()`
   - `_persist_guide_for_current()`
   - `_refresh_guide_view()`
   - All guide entry dialog handlers
   - CSV import/export handlers
2. Update `AppFrame`:
   - Remove `SideboardGuideHandlers` from inheritance
   - Now inherits only from `wx.Frame`!
3. Update sideboard panel callbacks to use coordinator
4. Keep original file with deprecation notice

**Verification:**
- [ ] Sideboard guide CRUD operations work (add/edit/remove entries)
- [ ] Exclusions editor functions correctly
- [ ] CSV import/export works
- [ ] Guide persists and loads correctly with deck changes
- [ ] Outboard tab functions properly

**Rollback:** Restore mixin inheritance

**Risk Level:** Medium - Complex state management, CSV parsing

---

### Phase 5: Extract State Manager (Low-Medium Risk)

#### Step 12: Create AppStateManager class

**Objective:** Extract window state persistence and session restoration.

**Principle Addressed:** SRP - Separate state management from frame and coordination.

**Prerequisites:** Step 11

**Files Affected:**
- `widgets/managers/app_state_manager.py` (NEW)

**Actions:**
1. Create `widgets/managers/app_state_manager.py`
2. Define `AppStateManager` class:
   ```python
   class AppStateManager:
       def __init__(
           self,
           frame: wx.Frame,
           controller: AppController,
           widgets: AppFrameWidgets,
       ):
           self.frame = frame
           self.controller = controller
           self.widgets = widgets
           self._save_timer: wx.Timer | None = None
   ```
3. Add methods:
   - `save_window_settings() -> None`
   - `apply_window_preferences() -> None`
   - `restore_session_state() -> None`
   - `schedule_settings_save() -> None`
   - `_flush_pending_settings(event) -> None`
4. Move timer management logic into state manager

**Verification:**
- [ ] File compiles without errors
- [ ] Type hints are correct
- [ ] No runtime impact yet

**Rollback:** Delete file

**Risk Level:** Low - New file, no integration

---

#### Step 13: Integrate AppStateManager into AppFrame

**Objective:** Replace direct state management with manager delegation.

**Principle Addressed:** SRP - Frame delegates state concerns to manager.

**Prerequisites:** Step 12

**Files Affected:**
- `widgets/app_frame.py` (lines 72, 84-86, 420-488, 479-488)

**Actions:**
1. In `AppFrame.__init__()`:
   - Create state manager: `self._state_manager = AppStateManager(self, controller, widgets)`
   - Replace `self._apply_window_preferences()` with `self._state_manager.apply_window_preferences()`
   - Replace session restore call with: `wx.CallAfter(self._state_manager.restore_session_state)`
2. Update `_schedule_settings_save()` calls throughout:
   - Replace with `self._state_manager.schedule_settings_save()`
3. Delete original methods from `AppFrame`:
   - `_save_window_settings()`
   - `_apply_window_preferences()`
   - `_schedule_settings_save()`
   - `_flush_pending_settings()`
   - `_restore_session_state()`
4. Move `_pending_deck_restore` flag to state manager
5. Move timer attribute to state manager

**Verification:**
- [ ] Window size persists across sessions
- [ ] Window position persists across sessions
- [ ] Deck state restores on launch
- [ ] Left panel mode (research/builder) restores
- [ ] Debounced save timer works (600ms delay)

**Rollback:** Restore original methods in AppFrame

**Risk Level:** Medium - Affects session persistence, but isolated change

---

### Phase 6: Refactor AppFrame into Thin Coordinator (Low Risk)

#### Step 14: Create facade properties in AppFrame

**Objective:** Ensure backward compatibility with minimal delegation layer.

**Principle Addressed:** Open/Closed - Old interface preserved, new implementation underneath.

**Prerequisites:** Step 13

**Files Affected:**
- `widgets/app_frame.py` (throughout)

**Actions:**
1. Audit all public methods still on `AppFrame`
2. For each method that should be in coordinator/manager:
   - Create delegation method: `def method(self, *args): return self._coordinator.method(*args)`
   - Or create property: `@property def attr(self): return self._widgets.attr`
3. Document which methods are delegated vs owned by AppFrame
4. Add docstrings indicating delegation targets
5. Organize AppFrame into clear sections:
   ```python
   class AppFrame(wx.Frame):
       """Thin coordinator that delegates to specialized components."""

       # ===== Initialization =====
       def __init__(self, controller, parent=None): ...

       # ===== Public API (for controller callbacks) =====
       def fetch_archetypes(self, force=False): ...
       def ensure_card_data_loaded(self): ...

       # ===== Widget Access Properties (backward compat) =====
       @property
       def research_panel(self): return self._widgets.research_panel

       # ===== Delegation Properties (backward compat) =====
       @property
       def zone_cards(self): return self.controller.zone_cards

       # ===== Helper Properties =====
       @property
       def current_format(self): return self.controller.current_format
   ```

**Verification:**
- [ ] All external callers (controller) still work
- [ ] All internal references resolve correctly
- [ ] No missing method/attribute errors
- [ ] Type hints still accurate

**Rollback:** Remove delegation methods, restore originals

**Risk Level:** Low - Additive changes, no deletions yet

---

#### Step 15: Clean up AppFrame - remove redundant code

**Objective:** Delete methods that are now fully delegated to other components.

**Principle Addressed:** DRY - Eliminate code duplication after delegation.

**Prerequisites:** Step 14

**Files Affected:**
- `widgets/app_frame.py` (final cleanup)
- `widgets/handlers/app_event_handlers.py` (delete or archive)
- `widgets/handlers/card_table_panel_handler.py` (delete or archive)
- `widgets/handlers/sideboard_guide_handlers.py` (delete or archive)

**Actions:**
1. Remove all methods from `AppFrame` that are pure delegation (no additional logic)
2. Keep only:
   - `__init__()` - coordinator creation and setup
   - Public API methods called by controller
   - Essential wx.Frame overrides (if any)
3. Move handler files to `widgets/handlers/deprecated/` directory
4. Update imports throughout codebase:
   - Replace `from widgets.handlers.app_event_handlers import AppEventHandlers`
   - With `from widgets.coordinators.app_event_coordinator import AppEventCoordinator`
5. Run full test suite to ensure nothing broke
6. Update any documentation/comments

**Verification:**
- [ ] AppFrame is now < 200 lines (down from 562)
- [ ] All tests pass
- [ ] No import errors
- [ ] Application runs without errors
- [ ] No performance regression

**Rollback:** Restore deleted methods and handler files

**Risk Level:** Medium - Deletes code, but should be safe after previous steps

---

### Phase 7: Finalization and Documentation (Low Risk)

#### Step 16: Update type hints and add comprehensive docstrings

**Objective:** Document new architecture and ensure type safety.

**Principle Addressed:** Maintainability - Clear documentation aids future development.

**Prerequisites:** Step 15

**Files Affected:**
- `widgets/app_frame.py`
- `widgets/managers/dialog_manager.py`
- `widgets/managers/app_state_manager.py`
- `widgets/builders/app_frame_builder.py`
- `widgets/coordinators/app_event_coordinator.py`

**Actions:**
1. Add comprehensive module-level docstrings to all new files:
   ```python
   """
   Dialog Manager - Lifecycle management for child windows.

   Responsibilities:
   - Opening and showing child dialogs (opponent tracker, timer, etc.)
   - Tracking open windows to prevent duplicates
   - Cleanup on parent close

   Usage:
       manager = DialogManager(parent_frame)
       manager.open_window('tracker', MTGOpponentDeckSpy, "Tracker", on_close)
       manager.close_all()
   """
   ```
2. Add class-level docstrings explaining responsibilities
3. Add method docstrings for all public methods
4. Run mypy and fix any type hint issues
5. Add type annotations to callback parameters
6. Document architectural decisions in docstrings

**Verification:**
- [ ] mypy passes with no errors
- [ ] All public methods have docstrings
- [ ] Architecture is documented
- [ ] IDEs show helpful tooltips

**Rollback:** Remove added documentation (non-functional change)

**Risk Level:** Low - Documentation only, no behavior changes

---

#### Step 17: Create architectural documentation

**Objective:** Document the new architecture for future maintainers.

**Principle Addressed:** Maintainability - Knowledge transfer and onboarding.

**Prerequisites:** Step 16

**Files Affected:**
- `docs/ARCHITECTURE.md` (NEW)
- `CLAUDE.md` (update)

**Actions:**
1. Create `docs/ARCHITECTURE.md` with:
   - Architecture diagram showing component relationships
   - Responsibility matrix (what each class does)
   - Data flow diagrams (how events/data move through system)
   - Extension guide (how to add new panels, dialogs, events)
2. Update `CLAUDE.md` with refactoring summary:
   ```markdown
   # AppFrame Architecture Refactoring (2026-01-29)

   ## Problem
   The AppFrame class was a god class with 562 lines handling 6+ distinct responsibilities...

   ## Solution
   Split into 5 focused classes:
   - `AppFrame` - Thin coordinator (< 200 lines)
   - `AppFrameBuilder` - UI construction
   - `AppEventCoordinator` - Event handling and marshalling
   - `DialogManager` - Child window lifecycle
   - `AppStateManager` - Session persistence

   ## Benefits
   - Improved testability (can test components in isolation)
   - Better separation of concerns
   - Easier to extend (add new panels without modifying frame)
   - Reduced coupling between UI and business logic
   ```
3. Add code examples showing common tasks:
   - How to add a new panel
   - How to add a new dialog
   - How to add a new event handler
   - How to add state persistence for new features

**Verification:**
- [ ] Documentation is clear and comprehensive
- [ ] Examples are accurate and runnable
- [ ] Diagrams are helpful and correct
- [ ] Future developers can understand architecture

**Rollback:** Delete documentation (non-functional)

**Risk Level:** Low - Documentation only

---

## Success Metrics

### Quantitative Metrics
1. **Line Count Reduction:**
   - `AppFrame`: 562 lines -> < 200 lines (65%+ reduction)
   - Total codebase: Similar or slightly higher (acceptable for better organization)

2. **Responsibility Count:**
   - `AppFrame`: 6+ responsibilities -> 2-3 responsibilities
   - Each new class: 1 clear responsibility

3. **Test Coverage:**
   - New components: > 80% code coverage
   - Integration tests: All existing tests pass
   - Unit tests: Can test components in isolation

4. **Coupling Metrics:**
   - `AppFrame` direct dependencies: 15+ classes -> < 8 classes
   - Circular dependencies: 0
   - Import depth: Reduced

5. **Type Safety:**
   - mypy errors: 0
   - Type hint coverage: > 95% of public APIs

### Qualitative Metrics
1. **Maintainability:**
   - New developer can understand architecture in < 30 minutes
   - Adding new panel takes < 1 hour (vs 2+ hours before)
   - Bug fixes require changes to 1 file instead of 3+

2. **Testability:**
   - Can mock dependencies easily
   - Can test UI construction without full app
   - Can test event handling without wx runtime

3. **Extensibility:**
   - Can subclass builder for custom layouts
   - Can add new dialogs without modifying frame
   - Can add new events without touching existing handlers

---

## Safety Considerations

### Backward Compatibility
- **Controller Interface:** All methods called by `AppController` must remain available
- **Widget References:** All widgets accessed externally must remain accessible (via properties if needed)
- **Event Signatures:** Event handler signatures cannot change
- **State Format:** Session state files must remain compatible

### Testing Strategy
1. **Before Each Step:**
   - Run full test suite
   - Note baseline memory usage
   - Document current behavior

2. **After Each Step:**
   - Run full test suite (must pass)
   - Check memory usage (should be similar)
   - Manual smoke test (launch app, open dialogs, load deck)
   - Git commit with clear message

3. **Integration Testing:**
   - Test all dialogs open/close correctly
   - Test all events trigger properly
   - Test state persists across sessions
   - Test deck operations work end-to-end
   - Test keyboard shortcuts function

### Rollback Strategy
- Each step includes explicit rollback instructions
- Git commits after each step for easy reversion
- Feature flag option: Add `USE_NEW_ARCHITECTURE = True` constant to toggle
- Parallel implementation possible: Keep old mixins alongside new coordinators temporarily

### Risk Mitigation
1. **Incremental Approach:** Small, testable steps instead of big-bang rewrite
2. **Low-to-High Risk Ordering:** Start with isolated components, end with core changes
3. **Property Delegation:** Maintain backward compat while refactoring internals
4. **Comprehensive Testing:** Test after every step, not just at end
5. **Documentation:** Clear architecture docs for future maintainers

---

## Dependencies Between Steps

```
Step 1 (DialogManager) -> Step 2 -> Step 3
                                     |
Step 4 (AppFrameBuilder) -> Step 5 -> Step 6
                                     |
Step 7 (EventCoordinator) -> Step 8 -> Step 9
                                     |
                           Step 10 -> Step 11
                                     |
Step 12 (StateManager) -> Step 13
                                     |
                     Step 14 -> Step 15
                                     |
                Step 16 (Docs) -> Step 17
```

**Critical Path:** Steps 1-3, 4-6, 7-9, 12-13, 14-15 must be done in order.
**Parallel Opportunities:** Steps 1-3 and 4-6 can be done in parallel if needed.

---

## Estimated Effort

- **Phase 1 (DialogManager):** 2-3 hours
- **Phase 2 (AppFrameBuilder):** 3-4 hours
- **Phase 3 (EventCoordinator):** 3-4 hours
- **Phase 4 (Remaining Mixins):** 2-3 hours
- **Phase 5 (StateManager):** 1-2 hours
- **Phase 6 (Cleanup):** 1-2 hours
- **Phase 7 (Documentation):** 1-2 hours

**Total: 13-20 hours** of focused development time, spread across multiple sessions for proper testing.

---

## Final Architecture Overview

After completion, the architecture will look like:

```
AppFrame (< 200 lines)
├── DialogManager - Child window lifecycle
├── AppFrameBuilder - UI construction
├── AppEventCoordinator - Event handling
│   ├── Zone operations (from CardTablePanelHandler)
│   ├── Sideboard guide (from SideboardGuideHandlers)
│   └── Async callbacks (from AppEventHandlers)
└── AppStateManager - Session persistence

AppController
└── Creates AppFrame and provides business logic

Panel Classes (unchanged)
├── DeckResearchPanel
├── DeckBuilderPanel
├── CardTablePanel
├── SideboardGuidePanel
└── ... (all other panels)
```

**Key Improvement:** Each class has exactly one reason to change, making the codebase more maintainable, testable, and extensible.
