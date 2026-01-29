# AppFrame Refactoring - Architecture Documentation

## Overview

This document describes the refactoring of `AppFrame` from a 562-line god class into a clean, modular architecture following SOLID principles.

## Goals Achieved

- **Line Count Reduction**: 562 → 343 lines (39% reduction)
- **Single Responsibility**: Each component has one clear purpose
- **Testability**: Components can be tested in isolation
- **Maintainability**: Changes to one component don't affect others
- **Readability**: Clear separation of concerns

## New Architecture

```
AppFrame (343 lines - thin coordinator)
├── AppFrameBuilder (495 lines)
│   └── Responsibility: UI construction
├── AppEventCoordinator (186 lines)
│   └── Responsibility: Event handling
├── DialogManager (140 lines)
│   └── Responsibility: Child window lifecycle
└── AppStateManager (111 lines)
    └── Responsibility: Window state persistence
```

## Component Breakdown

### 1. AppFrame (widgets/app_frame.py)

**Role**: Thin orchestration layer

**Responsibilities**:
- Initialize all managers and coordinators
- Delegate UI construction to builder
- Route events through coordinator
- Provide backward-compatible interface

**Does NOT**:
- Build UI widgets directly
- Handle events directly
- Manage state persistence
- Control child windows

**Key Methods**:
- `__init__()`: Initialize components
- `_build_ui()`: Delegate to AppFrameBuilder
- `_create_builder_callbacks()`: Wire callbacks to coordinator

### 2. AppFrameBuilder (widgets/builders/app_frame_builder.py)

**Role**: UI construction specialist

**Responsibilities**:
- Create all panels, widgets, and controls
- Set up layout and styling
- Wire callbacks to event coordinator
- Return structured widget container

**Does NOT**:
- Handle events
- Manage state
- Contain business logic

**Key Methods**:
- `build_all()`: Orchestrate complete UI construction
- `build_left_panel()`: Research/builder modes
- `build_right_panel()`: Deck workspace and inspector
- `build_toolbar()`: Action buttons
- `build_deck_workspace()`: Main workspace with tabs
- `create_zone_table()`: Card zone tables

**Returns**: `AppFrameWidgets` dataclass with all widget references

### 3. AppEventCoordinator (widgets/coordinators/app_event_coordinator.py)

**Role**: Event handling coordinator

**Responsibilities**:
- Handle all user interactions
- Delegate to AppController for business logic
- Update UI state after operations
- Coordinate workflows across components

**Does NOT**:
- Contain business logic
- Build UI
- Manage state persistence

**Key Methods**:
- Research events: `on_format_changed()`, `on_archetype_selected()`
- Deck events: `on_deck_selected()`, `on_copy_clicked()`, `on_save_clicked()`
- Window events: `open_opponent_tracker()`, `open_timer_alert()`
- Builder events: `on_builder_search()`, `on_builder_result_selected()`
- Table events: `handle_zone_delta()`, `handle_card_focus()`

**Current Implementation**: Facade pattern - delegates to AppFrame's existing mixin methods. Future refactoring could move logic from mixins into coordinator.

### 4. DialogManager (widgets/managers/dialog_manager.py)

**Role**: Child window lifecycle manager

**Responsibilities**:
- Opening and showing child dialogs
- Tracking open windows to prevent duplicates
- Cleanup on parent close
- Event binding for child windows

**Does NOT**:
- Handle dialog content/logic
- Manage dialog state
- Contain business logic

**Key Methods**:
- `open_window()`: Create or focus window
- `close_all()`: Cleanup all managed windows
- `get_window()`: Retrieve existing window

**Features**:
- Duplicate detection
- Automatic cleanup on close
- Error handling with user feedback

### 5. AppStateManager (widgets/managers/app_state_manager.py)

**Role**: Window state persistence

**Responsibilities**:
- Loading window position/size preferences
- Saving window position/size on change
- Debounced save to avoid excessive writes
- Managing preferences JSON file

**Does NOT**:
- Handle application state (delegated to AppController)
- Handle UI events
- Build UI

**Key Methods**:
- `load_window_preferences()`: Restore saved state
- `save_window_settings()`: Persist current state
- `schedule_settings_save()`: Debounced save
- `cleanup()`: Final save and timer cleanup

**Features**:
- 500ms debounce timer
- JSON persistence
- Graceful error handling

## Design Patterns Used

### 1. Builder Pattern
`AppFrameBuilder` constructs complex UI hierarchies step-by-step, returning a structured container of all widgets.

### 2. Facade Pattern
`AppEventCoordinator` provides a simplified interface to complex event handling logic, delegating to existing implementations.

### 3. Manager Pattern
`DialogManager` and `AppStateManager` encapsulate specific management responsibilities.

### 4. Dependency Injection
All components receive dependencies through constructor injection, enabling testing and flexibility.

## Benefits

### Before Refactoring
```python
class AppFrame(Mixins, wx.Frame):
    def __init__(self):
        # 100+ lines of UI construction
        self._build_left_panel()
        self._build_right_panel()
        self._build_toolbar()
        # ... many more methods

    def _build_left_panel(self):
        # 30+ lines of widget creation

    def on_deck_selected(self):
        # Event handling mixed with UI updates
```

**Problems**:
- 562 lines in one file
- Multiple responsibilities
- Hard to test
- Difficult to modify
- Unclear dependencies

### After Refactoring
```python
class AppFrame(Mixins, wx.Frame):
    def __init__(self, controller):
        self._dialog_manager = DialogManager(self)
        self._event_coordinator = AppEventCoordinator(self, controller)
        self._state_manager = AppStateManager(self, preferences_path)

        builder = AppFrameBuilder(self, controller, mana_icons, callbacks)
        widgets = builder.build_all()
```

**Benefits**:
- 343 lines (39% smaller)
- Single responsibility per class
- Easy to test each component
- Clear, explicit dependencies
- Modular and maintainable

## Testing Strategy

### Unit Testing Each Component

**AppFrameBuilder**:
```python
def test_build_toolbar():
    builder = AppFrameBuilder(mock_frame, mock_controller, icons, callbacks)
    toolbar = builder.build_toolbar(parent)
    assert isinstance(toolbar, ToolbarButtons)
```

**DialogManager**:
```python
def test_open_window_duplicate_detection():
    manager = DialogManager(mock_frame)
    window1 = manager.open_window("test", MockWindow, "Test")
    window2 = manager.open_window("test", MockWindow, "Test")
    assert window1 is window2  # Same instance
```

**AppEventCoordinator**:
```python
def test_on_deck_selected():
    coordinator = AppEventCoordinator(mock_frame, mock_controller)
    coordinator.on_deck_selected(mock_event)
    mock_frame.on_deck_selected.assert_called_once()
```

**AppStateManager**:
```python
def test_save_window_settings(tmp_path):
    prefs_file = tmp_path / "prefs.json"
    manager = AppStateManager(mock_frame, prefs_file)
    manager.save_window_settings()
    assert prefs_file.exists()
```

## Migration Guide

### For Code That Uses AppFrame

**Good news**: No changes needed! All existing interfaces are preserved through:
- Backward-compatible properties (`tracker_window`, `timer_window`, etc.)
- Public method signatures unchanged
- Event handling still works the same

**Example**:
```python
# Still works exactly the same
frame = AppFrame(controller)
frame.open_opponent_tracker()  # Routed through coordinator
if frame.tracker_window:       # Property delegates to dialog manager
    frame.tracker_window.Show()
```

### For Future Enhancements

**Adding a new dialog**:
```python
# In AppEventCoordinator
def open_new_dialog(self) -> None:
    self._dialog_manager.open_window(
        "new_dialog",
        NewDialogClass,
        "New Dialog",
    )
```

**Adding a new UI panel**:
```python
# In AppFrameBuilder
def build_new_panel(self, parent: wx.Window) -> NewPanel:
    panel = NewPanel(
        parent,
        on_action=self.callbacks["on_new_action"],
    )
    return panel
```

**Adding a new event handler**:
```python
# In AppEventCoordinator
def on_new_action(self) -> None:
    # Handle event
    self.controller.do_something()
    self.frame.update_ui()
```

## Future Improvements

### Potential Next Steps

1. **Move Logic from Mixins to Coordinator**
   - Currently: Coordinator delegates to AppFrame mixins
   - Future: Move actual implementation into coordinator
   - Benefit: Further separation of concerns

2. **Extract Remaining Orchestration**
   - Move deck rendering logic to a dedicated component
   - Extract archetype list management
   - Create search result handler component

3. **Simplify AppFrame Further**
   - Target: Under 200 lines
   - Make it purely a thin coordinator
   - All logic in specialized components

4. **Add More Managers**
   - CardInspectorManager for hover/focus logic
   - SearchManager for builder search functionality
   - DeckRenderer for deck display logic

## Conclusion

This refactoring demonstrates how a large, complex class can be decomposed into focused, maintainable components while preserving all existing functionality. The new architecture:

- **Follows SOLID principles**
- **Improves testability**
- **Enhances maintainability**
- **Maintains backward compatibility**
- **Provides clear separation of concerns**

Each component has a single, well-defined responsibility, making the codebase easier to understand, test, and modify.

---

**Refactoring Statistics**:
- Original: 562 lines
- Final: 343 lines (AppFrame) + 4 new components
- Reduction: 39% smaller main file
- Components: 4 new focused classes
- Test coverage: Each component independently testable
- Breaking changes: 0 (full backward compatibility)

**Time Investment**: Worth it for long-term maintainability and developer productivity.
