# QCI Plan: Hypergeometric Calculator for Opponent Identifier

**Issue:** #151 - Add hypergeom calculator to Oppo Identifier

## Summary

Add a hypergeometric probability calculator panel to the `MTGOpponentDeckSpy` widget (`widgets/identify_opponent.py`) that allows players to calculate the probability of drawing specific cards during matches. This feature will help players make informed mulligan and strategic decisions by computing draw probabilities based on deck composition. The calculator will integrate naturally below the opponent deck information display using the existing wxPython UI patterns.

## Issues

### Code Quality Concerns
- **Missing utility function**: No existing hypergeometric calculation function in the codebase; needs to be added to utils/
- **UI expansion needed**: Current `MTGOpponentDeckSpy` frame only shows opponent info; needs calculator panel integration
- **Input validation gaps**: Calculator inputs need validation for deck size, card copies, and draw counts
- **Dependencies**: scipy not in requirements.txt; need to implement calculation without it or add dependency

### Code Scale
- **Panel expansion**: Adding ~150-200 LOC for calculator panel, inputs, and results display
- **Utility addition**: ~50-80 LOC for hypergeometric math utility function
- **Net addition**: ~200-280 LOC total (justified by user-facing feature value)

### Type Safety
- **Missing type hints**: New functions need complete type annotations (int inputs/outputs, float probability)
- **Input validation**: Need explicit type checking and range validation for calculator inputs

## Atomic Steps (Low Risk → High Risk)

### Step 1: Add Hypergeometric Calculation Utility

**Objective**: Create a pure Python utility function for hypergeometric probability calculations
**Focus**: code quality, type hints
**Prerequisites**: None
**Files Affected**:
- `utils/math_utils.py` (NEW)

**Actions**:
1. Create `utils/math_utils.py` with hypergeometric calculation function
2. Implement using Python's `math.comb()` (available in Python 3.8+, already meets 3.11+ requirement)
3. Add function signature: `def hypergeometric_probability(population: int, successes_in_pop: int, sample_size: int, successes_in_sample: int) -> float`
4. Add docstring explaining parameters: N (deck size), K (copies in deck), n (cards drawn), k (copies drawn)
5. Include input validation with helpful error messages for invalid ranges
6. Add helper function: `def hypergeometric_at_least(population: int, successes_in_pop: int, sample_size: int, min_successes: int) -> float` for "at least X" probability
7. Add comprehensive type hints (no `Any` types)

**Verification**:
- [ ] Function calculates correct probabilities for test cases (e.g., 4 copies in 60-card deck, 7-card opening hand)
- [ ] Input validation raises ValueError for invalid inputs (negative numbers, sample > population, etc.)
- [ ] Type hints pass mypy/pyright checks
- [ ] Docstrings clearly explain card game context

**Rollback**: Delete `utils/math_utils.py`
**Risk Level**: Low - isolated pure function with no dependencies or side effects

---

### Step 2: Add Unit Tests for Hypergeometric Function

**Objective**: Ensure calculation accuracy with test coverage
**Focus**: code quality, error handling
**Prerequisites**: Step 1
**Files Affected**:
- `tests/test_math_utils.py` (NEW)

**Actions**:
1. Create `tests/test_math_utils.py` with pytest test cases
2. Test exact probability calculations against known values (use online calculators as reference)
3. Test "at least" probability aggregation
4. Test edge cases: 0 copies, drawing entire deck, drawing 0 cards
5. Test input validation: negative numbers, sample > population, successes > available
6. Test floating point precision (probabilities should be 0.0 to 1.0)
7. Add docstrings explaining what each test validates

**Verification**:
- [ ] All tests pass with `pytest tests/test_math_utils.py`
- [ ] Test coverage for math_utils.py is >95%
- [ ] Known probability values match reference calculators

**Rollback**: Delete `tests/test_math_utils.py`
**Risk Level**: Low - tests have no impact on runtime behavior

---

### Step 3: Add Calculator Panel UI Structure

**Objective**: Create collapsible calculator panel in opponent tracker
**Focus**: code quality, code scale
**Prerequisites**: Step 1
**Files Affected**:
- `widgets/identify_opponent.py`

**Actions**:
1. Import `math_utils` in `identify_opponent.py`
2. Add calculator panel to `_build_ui()` method after `status_label`
3. Create `wx.StaticBoxSizer` with label "📊 Hypergeometric Calculator"
4. Add panel initially hidden with `Hide()` call
5. Add toggle button "Show Calculator" / "Hide Calculator" in controls section
6. Wire button to `_toggle_calculator_panel()` method (stub for now)
7. Apply consistent styling: `DARK_BG`, `LIGHT_TEXT`, `OPPONENT_TRACKER_SECTION_PADDING`
8. Ensure panel respects `OPPONENT_TRACKER_FRAME_SIZE` width

**Verification**:
- [ ] Panel structure renders without errors
- [ ] Toggle button appears and responds to clicks
- [ ] Panel initially hidden, shows/hides on button click
- [ ] Styling matches existing opponent tracker aesthetic
- [ ] No layout issues when panel expands/collapses

**Rollback**: Remove calculator panel code from `_build_ui()`, remove toggle button
**Risk Level**: Low - UI-only change, no business logic affected

---

### Step 4: Add Calculator Input Controls

**Objective**: Add input fields for calculator parameters
**Focus**: code quality, type hints
**Prerequisites**: Step 3
**Files Affected**:
- `widgets/identify_opponent.py`

**Actions**:
1. Add four `wx.SpinCtrl` inputs to calculator panel:
   - "Deck Size" (range: 40-250, default: 60)
   - "Copies in Deck" (range: 0-20, default: 4)
   - "Cards Drawn" (range: 1-30, default: 7)
   - "Target Copies" (range: 0-20, default: 1)
2. Add labels for each input using `wx.StaticText` with `LIGHT_TEXT` color
3. Apply consistent spacing using `OPPONENT_TRACKER_SECTION_PADDING`
4. Style `wx.SpinCtrl` with `DARK_ALT` background, `LIGHT_TEXT` foreground
5. Add "Calculate" button styled like existing buttons
6. Add results label `wx.StaticText` for displaying probability (initially empty)
7. Store controls as instance variables: `self.deck_size_input`, etc.

**Verification**:
- [ ] All inputs render correctly with default values
- [ ] SpinCtrl ranges prevent invalid inputs
- [ ] Inputs are keyboard-navigable (tab between fields)
- [ ] Labels are clearly readable with dark theme
- [ ] Layout doesn't overflow frame width

**Rollback**: Remove input controls from calculator panel
**Risk Level**: Low - UI controls only, no calculation logic yet

---

### Step 5: Wire Calculate Button to Probability Function

**Objective**: Connect UI inputs to hypergeometric calculation
**Focus**: error handling, type hints
**Prerequisites**: Steps 1, 4
**Files Affected**:
- `widgets/identify_opponent.py`

**Actions**:
1. Implement `_on_calculate_probability()` event handler
2. Read values from `wx.SpinCtrl` inputs and validate they're valid ints
3. Call `hypergeometric_probability()` from `utils.math_utils`
4. Handle exceptions from validation errors with user-friendly error dialog
5. Calculate both exact probability and "at least" probability
6. Format results as percentage strings with 2 decimal places
7. Display results in results label: "Probability: X.XX% (exact) / Y.YY% (at least)"
8. Add type hints to handler method
9. Add error logging for unexpected failures

**Verification**:
- [ ] Calculate button triggers calculation
- [ ] Results display correctly formatted percentages
- [ ] Invalid inputs show error dialog (e.g., target copies > deck size)
- [ ] Calculation matches reference calculators (aetherhub.com/Apps/HyperGeometric)
- [ ] No crashes on edge case inputs

**Rollback**: Remove `_on_calculate_probability()` implementation, keep as no-op stub
**Risk Level**: Medium - integrates calculation logic with UI, potential for input validation bugs

---

### Step 6: Add Keyboard Shortcuts and UX Improvements

**Objective**: Improve calculator usability with keyboard support
**Focus**: code quality
**Prerequisites**: Step 5
**Files Affected**:
- `widgets/identify_opponent.py`

**Actions**:
1. Bind Enter key in any input field to trigger calculation
2. Add tooltip hints to inputs explaining parameters in MTG context
3. Add "Clear" button to reset inputs to defaults
4. Save calculator panel visibility state in config persistence (`_save_config()`)
5. Restore calculator visibility from config in `_load_config()`
6. Add visual feedback when calculation completes (brief highlight or status update)
7. Ensure tab order flows logically through inputs

**Verification**:
- [ ] Pressing Enter in any input field runs calculation
- [ ] Tooltips appear on hover with helpful text
- [ ] Clear button resets to defaults
- [ ] Calculator panel state persists across app restarts
- [ ] Tab navigation works smoothly

**Rollback**: Remove keyboard bindings, tooltip additions, and config persistence changes
**Risk Level**: Low - UX enhancements only, no core logic changes

---

### Step 7: Add Quick Preset Buttons

**Objective**: Add common scenario buttons for faster calculations
**Focus**: code quality, code scale
**Prerequisites**: Step 5
**Files Affected**:
- `widgets/identify_opponent.py`

**Actions**:
1. Add "Presets" section with common MTG scenarios
2. Create preset buttons:
   - "Opening Hand (60)" - deck=60, draws=7
   - "Opening Hand (40)" - deck=40, draws=7 (limited)
   - "Turn 3 (on play)" - deck=60, draws=9
   - "Turn 3 (on draw)" - deck=60, draws=10
3. Wire buttons to update input fields and auto-calculate
4. Keep "Copies in Deck" and "Target Copies" unchanged (user-specific)
5. Style preset buttons smaller/secondary style (similar to refresh button)
6. Add horizontal button layout to save vertical space

**Verification**:
- [ ] Preset buttons populate inputs correctly
- [ ] Auto-calculation triggers after preset selection
- [ ] Buttons fit within panel width without wrapping
- [ ] User can override preset values manually

**Rollback**: Remove preset buttons section
**Risk Level**: Low - convenience feature, no impact on core calculator logic

---

### Step 8: Update Documentation

**Objective**: Document the new calculator feature
**Focus**: code quality
**Prerequisites**: Steps 1-7
**Files Affected**:
- `CLAUDE.md`
- `README.md` (if exists)

**Actions**:
1. Add hypergeometric calculator to feature list in `CLAUDE.md`
2. Document calculator parameters and usage
3. Add example calculation scenarios
4. Document keyboard shortcuts (Enter to calculate, Clear button)
5. Note mathematical approach (Python math.comb, no scipy dependency)
6. Add to "Key Features" section: "Hypergeometric probability calculator for draw odds"
7. Update any existing opponent tracker documentation sections

**Verification**:
- [ ] Documentation is clear and accurate
- [ ] Examples match actual calculator behavior
- [ ] No markdown syntax errors

**Rollback**: Revert documentation changes
**Risk Level**: Low - documentation only, no code impact

---

## Assessment

**Overall Risk**: Low to Medium

**Key Mitigations**:
1. **Isolated utility function** - Math logic separated from UI (Step 1)
2. **Incremental UI integration** - Panel structure before calculation logic (Steps 3-4 before 5)
3. **Comprehensive input validation** - Prevents invalid calculations from reaching math function
4. **No external dependencies** - Uses Python 3.11+ built-in `math.comb()`, no scipy needed
5. **Type safety** - Full type hints prevent type-related bugs

**Risk Areas**:
- **Floating point precision**: Hypergeometric calculations with large factorials could lose precision (mitigated by using `math.comb` which handles large integers)
- **UI overflow**: Calculator panel could make frame too tall on small screens (mitigated by making panel collapsible)
- **Input validation edge cases**: Need thorough testing of boundary conditions

## Success Metrics

Observable improvements indicating successful feature addition:

1. **Calculator accuracy**: Results match reference calculators (aetherhub.com, cardgamecalculator.com) within 0.01% for test cases
2. **UI integration**: Calculator panel integrates seamlessly without breaking existing opponent tracking functionality
3. **Usability**: Users can complete a calculation in <10 seconds with keyboard-only input
4. **Performance**: Calculation completes instantly (<100ms) for all valid inputs
5. **Code quality**: New code maintains 100% type hint coverage, passes ruff/black formatting
6. **No regressions**: All existing opponent tracker features (caching, polling, deck lookup) continue working
7. **Persistence**: Calculator panel visibility state persists across app restarts
8. **Zero crashes**: No exceptions or crashes with any valid input combination

## Safety Steps

Required precautions for medium risk steps:

### For Step 5 (Wire Calculate Button - Medium Risk):

1. **Add input validation tests before integration**:
   - Create test cases for invalid input combinations
   - Test boundary values (max deck size, 0 copies, etc.)
   - Test mathematical edge cases (P=0, P=1)

2. **Add error recovery**:
   - Wrap calculation in try/except with specific exception handling
   - Show user-friendly error dialog instead of crashing
   - Log errors with context for debugging

3. **Add feature flag (optional)**:
   - Could add config option to disable calculator if bugs discovered
   - `"calculator_enabled": true` in config JSON

4. **Manual testing checklist**:
   - Test with various deck sizes (40, 60, 100, 250)
   - Test with edge cases (0 copies, drawing entire deck)
   - Test keyboard navigation flow
   - Test on different screen sizes/resolutions

### For Step 7 (Quick Presets - Low-Medium Risk):

1. **Verify preset values**:
   - Confirm preset scenarios match actual MTG gameplay
   - Document reasoning for preset values in comments
   - Add test to verify presets populate inputs correctly

## UI Layout Reference

```
┌─────────────────────────────────────┐
│ MTGO Opponent Tracker               │
├─────────────────────────────────────┤
│ [Opponent Deck Information]         │
│ Status: Watching for matches...     │
├─────────────────────────────────────┤
│ [Refresh] [Close] [Show Calculator] │ <- Toggle button
├─────────────────────────────────────┤
│ 📊 Hypergeometric Calculator        │ <- Collapsible panel
│                                     │
│ Deck Size:       [60]               │
│ Copies in Deck:  [4]                │
│ Cards Drawn:     [7]                │
│ Target Copies:   [1]                │
│                                     │
│ Presets: [Opening(60)] [Opening(40)]│
│          [Turn 3 Play] [Turn 3 Draw]│
│                                     │
│ [Calculate] [Clear]                 │
│                                     │
│ Probability: 39.86% (exact)         │
│             59.77% (at least 1)     │
└─────────────────────────────────────┘
```

## Mathematical Approach

The hypergeometric probability formula calculates P(X = k):
```
P(X = k) = [C(K, k) × C(N-K, n-k)] / C(N, n)
```
Where:
- N = population size (deck size)
- K = successes in population (copies in deck)
- n = sample size (cards drawn)
- k = successes in sample (target copies drawn)

Python 3.11+ `math.comb(n, k)` efficiently computes combinations without factorial overflow.
