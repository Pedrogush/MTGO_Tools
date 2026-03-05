# pt-BR Localization Plan

This document catalogs every unlocalized UI string in the codebase (as of `main` after PR #234)
and provides an atomized, context-independent step-by-step plan for completing the pt-BR
translation.

---

## Current State

`utils/i18n.py` contains 24 keys for `en-US` and `pt-BR`.
The following areas already use `translate()` / `self._t()`:

- `app_frame.py`: window title, status "Ready", toolbar button labels, deck-action button labels,
  research panel labels, deck-data-source label, language label, source choice labels.

Everything listed below is **not yet localized**.

---

## Unlocalized Strings Inventory

### `widgets/app_frame.py`

| Line | String | Context |
|------|--------|---------|
| 298 | `"Deck Results"` | `wx.StaticBox` label |
| 342 | `"Card Inspector"` | `wx.StaticBox` label |
| 385 | `"Deck Workspace"` | `wx.StaticBox` label |
| 408 | `"Stats"` | Notebook tab name |
| 421 | `"Sideboard Guide"` | Notebook tab name |
| 431 | `"Deck Notes"` | Notebook tab name |
| 436 | `"Deck Tables"` | Notebook tab name |
| 444 | `"Mainboard"` | Zone notebook tab |
| 445 | `"Sideboard"` | Zone notebook tab |
| 450 | `"Collection inventory not loaded."` | `wx.StaticText` label |
| 526 | `"Loading card database to restore saved deck..."` | status bar message |
| 620 | `"Select an archetype to view decks."` | summary text area |

### `widgets/handlers/app_event_handlers.py`

| Line | String | Context |
|------|--------|---------|
| 177 | `f"Loading deck {name}…"` | status bar |
| 193 | `"No deck to copy."` / `"Copy Deck"` | `wx.MessageBox` |
| 200 | `"Deck copied to clipboard."` | status bar |
| 202 | `"Could not access clipboard."` / `"Copy Deck"` | `wx.MessageBox` |
| 207 | `"Load a deck first."` / `"Save Deck"` | `wx.MessageBox` |
| 213 | `"Deck name:"` / `"Save Deck"` | `wx.TextEntryDialog` |
| 228 | `"Failed to write deck file:\n{exc}"` / `"Save Deck"` | `wx.MessageBox` |
| 231–234 | `"Deck saved to {path}"` / `"Deck Saved"` | `wx.MessageBox` |
| 235 | `"Deck saved successfully."` | status bar |
| 265 | `f"Loaded {count} archetypes for {format}."` | status bar |
| 267 | `f"Select an archetype to view decks.\nLoaded {count} archetypes."` | summary text |
| 274 | `f"Error: {error}"` | status bar |
| 275–277 | `"Unable to load archetypes:\n{error}"` / `"Archetype Error"` | `wx.MessageBox` |
| 285 | `"No decks found."` | deck list item |
| 287 | `f"No decks for {archetype}."` | status bar |
| 288 | `f"{archetype}\n\nNo deck data available."` | summary text |
| 295–297 | `f"Loaded {n} decks for {archetype}. Click a deck to load it."` | status bar |
| 303 | `"Failed to load decks."` | deck list item |
| 304 | `f"Error loading decks: {error}"` | status bar |
| 305 | `"Failed to load deck lists:\n{error}"` / `"Deck Error"` | `wx.MessageBox` |
| 310 | `f"Deck download failed: {error}"` | status bar |
| 311 | `"Failed to download deck:\n{error}"` / `"Deck Download"` | `wx.MessageBox` |
| 334 | `f"Deck ready ({source})."` | status bar |
| 345 | `f"Collection load failed: {exc}"` | `SetLabel` |
| 350 | `f"Collection: {name} ({n} entries)"` | `SetLabel` |
| 355 | `f"Collection fetch failed: {msg}"` | `SetLabel` |
| 364 | `"Ready"` | status bar (bulk data loaded) |
| 376 | `"Ready"` | status bar (bulk data load failed) |
| 380 | `"Card image database downloaded, indexing printings…"` | status bar |
| 388 | `"Ready"` | status bar (bulk data download failed) |
| 403–404 | `"Loading card data… (search will run automatically)"` | builder status label |
| 417 | `"Mana value must be numeric."` | builder status label |
| 484–486 | `"Failed to build daily average:\n{error}"` / `"Daily Average"` | `wx.MessageBox` |
| 487 | `f"Daily average failed: {error}"` | status bar |
| 507–510 | `"Failed to load card database:\n{error}"` / `"Card Data Error"` | `wx.MessageBox` |
| 566–570 | `"Daily Average"` / `"Downloading decks…"` | `wx.ProgressDialog` title/message |
| 583 | `f"Processed {current}/{total} decks…"` | progress dialog update |
| 590 | `wx.MessageBox(message, "Daily Average", ...)` | message box title |
| 598 | `"Deck identifier missing."` / `"Deck Error"` | `wx.MessageBox` |

### `widgets/handlers/sideboard_guide_handlers.py`

| Line | String | Context |
|------|--------|---------|
| ~135 | `wx.MessageBox(...)` export success/error | `wx.MessageBox` |
| ~159 | `wx.MessageBox(...)` import success/error | `wx.MessageBox` |
| 237 | `"Enable double entries"` | `wx.CheckBox` label in inline dialog |
| 246 | `"Import"` | `wx.Button` in inline dialog |
| 249 | `"Cancel"` | `wx.Button` in inline dialog |

### `widgets/panels/deck_builder_panel.py`

| Line | String | Context |
|------|--------|---------|
| 237 | `"Deck Research"` | back button label |
| 243 | `"Deck Builder: search MTG cards by property."` | info `wx.StaticText` |
| ~255 | Property filter labels (Name, Type, Text, etc.) | `wx.StaticText` per filter row |
| 269 | `"Match"` | match-type label |
| 272 | `"Exact symbols"` | `wx.CheckBox` label |
| 287 | `"All"` | color "All" button |
| 298 | `"Mana Value Filter"` | section label |
| 316 | `"Formats"` | section label |
| 321 | Format checkboxes (Modern, Legacy, etc.) | `wx.CheckBox` labels |
| 330 | `"Color Identity Filter"` | section label |
| 350 | Color identity checkboxes (W, U, B, R, G, C) | `wx.CheckBox` labels |
| 360 | `"Clear Filters"` | button label |
| 366 | `"Use Radar Filter"` | `wx.CheckBox` label |
| 381 | `"Open Radar..."` | button label |
| 408 | `"+ Mainboard"` | button label |
| 415 | `"+ Sideboard"` | button label |
| 425 | `"Results update automatically as you type."` | status `wx.StaticText` |
| 552 | `"Filters cleared."` | `SetLabel` on status label |
| 582 | `f"Showing {n} card(s)."` | `SetLabel` on status label |
| 643–647 | `"Please open a radar..."` / `"No Radar Loaded"` | `wx.MessageBox` |
| 680–683 | `f"Radar active: {name} ({mb} MB, {sb} SB cards)"` | `SetLabel` on status label |

### `widgets/panels/deck_stats_panel.py`

| Line | String | Context |
|------|--------|---------|
| 50 | `"No deck loaded."` | initial `wx.StaticText` label |
| 87, 113 | `"No deck loaded."` | `SetLabel` on reset |

### `widgets/panels/sideboard_guide_panel.py`

| Line | String | Context |
|------|--------|---------|
| 80 | `"Add Entry"` | button label |
| 85 | `"Edit Entry"` | button label |
| 90 | `"Remove Entry"` | button label |
| 95 | `"Exclude Archetypes"` | button label |
| 100 | `"Export CSV"` | button label |
| 105 | `"Import CSV"` | button label |
| 113 | `"Exclusions: —"` | initial `wx.StaticText` label |
| 205 | `f"Exclusions: {text}"` | dynamic `SetLabel` |

### `widgets/panels/deck_notes_panel.py`

| Line | String | Context |
|------|--------|---------|
| 71 | `"Save Notes"` | button label |

### `widgets/dialogs/guide_entry_dialog.py`

| Line | String | Context |
|------|--------|---------|
| 34 | `"Sideboard Guide Entry"` | dialog title |
| 46 | `"Archetype/Matchup"` | field label |
| 64 | `"ON THE PLAY"` | section label |
| 83 | `"ON THE DRAW"` | section label |
| 102 | `"Notes (Optional)"` | field label |
| 111 | `"Strategy notes for this matchup"` | text hint |
| 115 | `"Enable double entries"` | `wx.CheckBox` label |
| 127 | `"Save & Continue"` | button label |
| 134 | `"OK"` | button label |
| 140 | `"Cancel"` | button label |

### `widgets/dialogs/image_download_dialog.py`

| Line | String | Context |
|------|--------|---------|
| 39 | `"Download Card Images"` | dialog title |
| 56 | `"Download Card Images from Scryfall"` | title label |
| 65 | `"Image Quality:"` | label |
| 74 | `"Download Amount:"` | label |
| 83–99 | Long info text block | `wx.StaticText` |
| 99 | `"Cancel"` | button |
| 102 | `"Download"` | button |
| 250 | `"Download failed: {msg}"` / `"Download Error"` | `wx.MessageBox` |

### `widgets/identify_opponent.py`

| Line | String | Context |
|------|--------|---------|
| 129 | `"MTGO Opponent Tracker"` | frame title |
| 170 | `"Opponent not detected"` | deck label |
| 175 | `"Watching for MTGO match windows…"` | status label |
| 195 | `"Refresh"` | button |
| 200 | `"Calculator"` | toggle button |
| 205 | `"Radar"` | toggle button |
| 210 | `"Close"` | button |
| 256 | `"Hypergeometric Calculator"` | calc panel title |
| 268 | `"Deck Size:"` | calc label |
| 278 | `"Copies in Deck:"` | calc label |
| 286 | `"Cards Drawn:"` | calc label |
| 294 | `"Target Copies:"` | calc label |
| 312 | Preset button labels (`"Open 60"`, `"Open 40"`, `"T3 Play"`, `"T3 Draw"`) | buttons |
| 325 | `"Calculate"` | button |
| 334 | `"Clear"` | button |
| 368, 371 | `"Hide Calc"` / `"Calculator"` | toggle label |
| 380, 383 | `"Hide Radar"` / `"Radar"` | toggle label |
| 403–412 | `"Error: Copies > Deck Size"` etc. | error labels |
| 422 | Result text (exact/at-least probability) | result label |
| 551 | `"Hide Radar"` | label in radar section |
| 572 | `"Watching for MTGO match windows…"` | reset status |
| 584 | `"Waiting for MTGO match window…"` | poll status |
| 592 | `"No active match detected"` | poll status |
| 612 | `f"Match detected: vs {name}"` | match status |
| 755, 761 | `"Hide Calc"` / `"Hide Radar"` | state restore |

### `widgets/match_history.py`

| Line | String | Context |
|------|--------|---------|
| 34 | `"MTGO Match History (wx)"` | frame title |
| 74 | `"Refresh"` | button |
| 81 | `"Ready"` | initial status label |
| 85 | `"Win-Rate Metrics"` | `wx.StaticBox` label |
| 93 | `"Absolute Match Win Rate: —"` | label |
| 96 | `"Absolute Game Win Rate: —"` | label |
| 99–100 | `"Match Win Rate (filtered): —"` | label |
| 104–105 | `"Game Win Rate (filtered): —"` | label |
| 109 | `"Mulligan Rate: —"` | label |
| 112 | `"Avg Mulligans/Match: —"` | label |
| 120 | `"Start (YYYY-MM-DD):"` | filter label |
| 130 | `"End (YYYY-MM-DD):"` | filter label |
| 139 | `"Apply Date Filter"` | button |
| 308 | `"Deck Lists"` | `wx.MessageDialog` title |
| 316–320 | `"Loading…"` / `"Ready"` | dynamic status |
| 326–328 | Win-rate reset strings | `SetLabel` on clear |

### `widgets/timer_alert.py`

| Line | String | Context |
|------|--------|---------|
| 129 | `"MTGO Timer Alert"` | frame title |
| 166 | `"Alert Thresholds"` | `wx.StaticBox` label |
| 172–173 | `"Enter time in MM:SS format (e.g., 05:00 for 5 minutes)"` | instruction label |
| 190 | `"+ Add Another Threshold"` | button |
| 238 | `"Alert when timer starts counting down"` | checkbox label |
| 245 | `"Repeat alarm at interval"` | checkbox label |
| 255 | `"Start Monitoring"` | button |
| 260 | `"Stop"` | button |
| 265 | `"Test Alert"` | button |
| 281 | `"Active Challenge Timer"` | `wx.StaticBox` label |
| 285–286 | `"No active challenge timer detected."` | initial label |
| 532 | `"No active challenge timer detected."` | dynamic reset |

### `widgets/metagame_analysis.py`

| Line | String | Context |
|------|--------|---------|
| 31 | `"Metagame Analysis"` | frame title |
| 56 | `"Format:"` | label |
| 76 | `"Time Window (days):"` | label |
| 88 | `"Starting from day:"` | label |
| 99 | `"Refresh Data"` | button |
| 106 | `"Ready"` | initial status label |
| 127 | `"Metagame Changes"` | section label |
| 370–374 | `"Loading..."` / `"Ready"` | dynamic status |

### `widgets/splash_frame.py`

| Line | String | Context |
|------|--------|---------|
| 17 | `"Loading MTGO Deck Builder"` | frame title |
| 37 | `"Loading MTGOTools..."` | title label |

### `widgets/panels/card_inspector_panel.py`

| Line | String | Context |
|------|--------|---------|
| 149 | `"Loading printing…"` | nav label |
| 170, 228 | `"Select a card to inspect."` | initial / reset label |

---

## Implementation Plan

Each step is self-contained and can be executed in a fresh context.
After each step: run `python3 -m pytest tests/ -q --ignore=tests/ui`, run `black` + `ruff --fix`,
commit, push, and reset context before proceeding.

---

### Step 1 — Extend `utils/i18n.py` with all new message keys

**File:** `utils/i18n.py`
**What:** Add every new string key to the `MESSAGES` dict for both `en-US` and `pt-BR`.
**Key groups to add:**

```
# app_frame box/tab labels
app.box.deck_results, app.box.card_inspector, app.box.deck_workspace
app.tab.stats, app.tab.sideboard_guide, app.tab.deck_notes, app.tab.deck_tables
app.tab.mainboard, app.tab.sideboard
app.label.collection_not_loaded
app.status.loading_card_db
app.status.select_archetype

# app_event_handlers messages
app.status.loading_deck, app.status.deck_copied, app.status.deck_saved
app.status.archetypes_loaded, app.status.error, app.status.no_decks
app.status.decks_loaded, app.status.deck_ready, app.status.daily_avg_failed
app.status.card_image_indexing, app.status.loading_card_data
app.msg.no_deck_to_copy, app.msg.clipboard_failed, app.msg.load_deck_first
app.msg.deck_name_prompt, app.msg.save_failed, app.msg.deck_saved
app.msg.archetype_error, app.msg.no_decks_found, app.msg.decks_unavailable
app.msg.deck_list_error, app.msg.deck_download_error, app.msg.card_db_error
app.msg.daily_avg_error, app.msg.daily_avg_title, app.msg.downloading_decks
app.msg.deck_id_missing
app.label.collection_loaded, app.label.collection_failed, app.label.collection_load_error
app.label.mana_value_numeric, app.label.builder_loading_card_data
app.progress.decks_processed
app.status.daily_avg_start

# deck_builder_panel labels
builder.btn.back, builder.info, builder.label.match, builder.label.exact_symbols
builder.btn.all, builder.label.mana_value, builder.label.formats
builder.label.color_identity, builder.btn.clear_filters
builder.label.use_radar, builder.btn.open_radar
builder.btn.add_main, builder.btn.add_side, builder.label.results_hint
builder.status.filters_cleared, builder.status.showing_cards
builder.msg.no_radar, builder.label.radar_active

# sideboard_guide_panel labels
guide.btn.add, guide.btn.edit, guide.btn.remove, guide.btn.exclude
guide.btn.export_csv, guide.btn.import_csv, guide.label.exclusions_none
guide.label.exclusions

# deck_stats_panel
stats.no_deck_loaded

# deck_notes_panel
notes.btn.save

# guide_entry_dialog
guide_dialog.title, guide_dialog.label.archetype, guide_dialog.label.on_play
guide_dialog.label.on_draw, guide_dialog.label.notes, guide_dialog.hint.notes
guide_dialog.cb.double_entries, guide_dialog.btn.save_continue
guide_dialog.btn.ok, guide_dialog.btn.cancel

# image_download_dialog
img_dialog.title, img_dialog.label.title, img_dialog.label.quality
img_dialog.label.amount, img_dialog.label.info, img_dialog.btn.cancel
img_dialog.btn.download, img_dialog.msg.failed, img_dialog.msg.failed_title

# sideboard_guide_handlers inline dialog
guide_import.cb.double_entries, guide_import.btn.import, guide_import.btn.cancel

# identify_opponent
tracker.title, tracker.label.no_opponent, tracker.label.watching
tracker.btn.refresh, tracker.btn.calc, tracker.btn.radar, tracker.btn.close
tracker.calc.title, tracker.calc.deck_size, tracker.calc.copies
tracker.calc.drawn, tracker.calc.target, tracker.calc.btn_calculate
tracker.calc.btn_clear, tracker.calc.preset.*
tracker.calc.hide, tracker.calc.show
tracker.radar.hide, tracker.radar.show
tracker.calc.err.copies_gt_deck, tracker.calc.err.drawn_gt_deck
tracker.calc.err.target_gt_copies, tracker.calc.err.target_gt_drawn
tracker.status.waiting, tracker.status.no_match, tracker.status.match_detected

# match_history
history.title, history.btn.refresh, history.label.ready
history.box.metrics, history.label.match_rate, history.label.game_rate
history.label.filtered_match_rate, history.label.filtered_game_rate
history.label.mulligan_rate, history.label.avg_mulligans
history.label.start_date, history.label.end_date, history.btn.apply_filter
history.dialog.deck_lists, history.status.loading

# timer_alert
timer.title, timer.box.thresholds, timer.label.format_hint
timer.btn.add_threshold, timer.cb.alert_on_start, timer.cb.repeat_alarm
timer.btn.start, timer.btn.stop, timer.btn.test
timer.box.active_timer, timer.label.no_timer

# metagame_analysis
meta.title, meta.label.format, meta.label.time_window
meta.label.start_day, meta.btn.refresh, meta.label.ready
meta.label.changes_header, meta.status.loading

# splash_frame
splash.title, splash.label.loading

# card_inspector_panel
inspector.label.select_card, inspector.label.loading_printing
```

**No code logic changes** — pure data entry.
**Tests:** `tests/test_i18n.py` (existing) should pass; add assertions for a sample of new keys.

---

### Step 2 — Localize remaining hardcoded strings in `widgets/app_frame.py`

**File:** `widgets/app_frame.py`
**What:** Replace the 12 hardcoded English strings with `self._t(key)` calls.

Specific changes:
- `_build_deck_results`: `wx.StaticBox(parent, label="Deck Results")` → `self._t("app.box.deck_results")`
- `_build_card_inspector`: `"Card Inspector"` → `self._t("app.box.card_inspector")`
- `_build_deck_workspace`: `"Deck Workspace"` → `self._t("app.box.deck_workspace")`
- `AddPage` calls in `_build_deck_workspace`: `"Stats"`, `"Sideboard Guide"`, `"Deck Notes"`, `"Deck Tables"` → `self._t(...)` variants
- `_build_deck_tables_tab`: `"Mainboard"`, `"Sideboard"` tab names; `"Collection inventory not loaded."` label
- `_restore_session_state`: status message
- `_clear_deck_display`: summary text

**Tests:** Run full test suite; visually verify tabs render correctly if app is running.

---

### Step 3 — Localize `widgets/handlers/app_event_handlers.py`

**File:** `widgets/handlers/app_event_handlers.py`
**What:** Replace ~35 hardcoded strings with `self._t(key)` calls throughout all handler methods.

The handler mixin already inherits `self._t()` from `AppFrame` — no architectural changes needed.

Key methods to update:
- `on_copy_clicked`, `on_save_clicked` — message boxes and status messages
- `_on_archetypes_loaded`, `_on_archetypes_error` — status and summary text
- `_on_decks_loaded`, `_on_decks_error`, `_on_deck_download_error`
- `_on_deck_content_ready` — `"Deck ready ({source})."` (use `self._t("app.status.deck_ready", source=source)`)
- `_on_collection_fetched`, `_on_collection_fetch_failed`
- `_on_bulk_data_loaded`, `_on_bulk_data_load_failed`, `_on_bulk_data_downloaded`, `_on_bulk_data_failed` — `"Ready"` strings
- `_on_builder_search` — builder status messages
- `_on_daily_average_error`, `ensure_card_data_loaded` — error message boxes
- `_start_daily_average_build` — progress dialog strings and `wx.MessageBox`

**Note:** For f-strings with variables, use `self._t("key", var=value)` and include `{var}` placeholders
in the translation strings (already supported by `translate()`).

---

### Step 4 — Localize `widgets/handlers/sideboard_guide_handlers.py`

**File:** `widgets/handlers/sideboard_guide_handlers.py`
**What:** Replace ~5 hardcoded strings in the inline import dialog and message boxes.

The handler mixin inherits `self._t()` from `AppFrame`.

- Inline import dialog button labels: `"Import"`, `"Cancel"`, checkbox `"Enable double entries"`
- `wx.MessageBox` calls for export/import success and error

---

### Step 5 — Localize `widgets/panels/deck_builder_panel.py`

**File:** `widgets/panels/deck_builder_panel.py`
**What:** Localize ~18 strings.

**Architectural change required:** `DeckBuilderPanel.__init__` must accept a `locale: str = "en-US"`
parameter (or a `labels: dict[str, str]` dict like `ToolbarButtons` does).

Recommended approach: add `locale: str = "en-US"` to `__init__`, store as `self._locale`, and
define a `_t(key, **kw)` helper that calls `translate(self._locale, key, **kw)`.

Update `app_frame.py` to pass `locale=self.locale` when constructing `DeckBuilderPanel`.

Strings to replace: back button, info label, all filter section labels, all checkbox/button labels,
status messages, message box.

---

### Step 6 — Localize small panels

**Files:**
- `widgets/panels/deck_stats_panel.py`
- `widgets/panels/deck_notes_panel.py`
- `widgets/panels/sideboard_guide_panel.py`

**What:** Each panel has a small number of hardcoded strings. Add `labels: dict[str, str] | None = None`
parameter to each constructor (same pattern as `DeckResearchPanel` and `ToolbarButtons`), then pass
translated labels from `app_frame.py`.

- `deck_stats_panel.py`: `"No deck loaded."` (initial + reset calls)
- `deck_notes_panel.py`: `"Save Notes"` button
- `sideboard_guide_panel.py`: 6 button labels, `"Exclusions: —"` label, dynamic `"Exclusions: {text}"`
  (the dynamic label needs special handling — pass a `_t` callable or format string)

Update `app_frame.py` `_build_deck_workspace` to pass `labels` dicts to each panel.

---

### Step 7 — Localize dialog files

**Files:**
- `widgets/dialogs/guide_entry_dialog.py`
- `widgets/dialogs/image_download_dialog.py`

**What:** Add `locale: str = "en-US"` parameter to each dialog's `__init__` and use `translate()` locally.

- `guide_entry_dialog.py`: dialog title, 4 field labels, hint text, checkbox, 3 buttons
- `image_download_dialog.py`: dialog title, 3 labels, long info text, 2 buttons, message box error

Update callers in `app_frame.py` and `sideboard_guide_handlers.py` to pass `locale=self.locale`.

---

### Step 8 — Add `get_ui_locale()` utility for standalone widgets

**File:** `utils/i18n.py`
**What:** Add a `get_ui_locale()` function that reads the saved language preference from the app's
settings file without requiring a full `AppController`. This lets the standalone widgets
(Opponent Tracker, Match History, Timer Alert, Metagame Analysis) respect the user's language
preference when opened independently.

Implementation sketch:
```python
def get_ui_locale() -> LocaleCode:
    """Read saved locale from settings; fall back to DEFAULT_LOCALE."""
    try:
        settings_path = Path(CONFIG["settings_path"])   # or derive from constants
        data = fast_load(settings_path)
        return normalize_locale(data.get("language"))
    except Exception:
        return DEFAULT_LOCALE
```

Confirm the exact settings file path by checking `controllers/session_manager.py` or
`controllers/app_controller_helpers.py`.

---

### Step 9 — Localize `widgets/identify_opponent.py`

**File:** `widgets/identify_opponent.py`
**What:** Add `locale = get_ui_locale()` at the top of `MTGOpponentDeckSpy.__init__`, store as
`self._locale`, add `_t()` helper, then replace all ~25 hardcoded strings.

Groups:
- Frame title, static labels, button labels
- Calculator panel: title, 4 input labels, preset buttons, calculate/clear buttons
- All dynamic `SetLabel` calls for: calc toggle, radar toggle, calc errors, match status messages

---

### Step 10 — Localize `widgets/match_history.py`

**File:** `widgets/match_history.py`
**What:** Same locale pattern as Step 9. Replace ~18 strings.

Groups:
- Frame title, refresh button, ready label
- Win-Rate Metrics static box and 6 metric labels
- Date filter labels and button
- Deck Lists dialog title
- Dynamic status `SetLabel` calls

---

### Step 11 — Localize `widgets/timer_alert.py`

**File:** `widgets/timer_alert.py`
**What:** Same locale pattern as Step 9. Replace ~12 strings.

Groups:
- Frame title
- Alert Thresholds box, instruction text, add-threshold button
- Checkboxes: alert-on-start, repeat-alarm
- Buttons: Start Monitoring, Stop, Test Alert
- Active Challenge Timer box and initial/reset label

---

### Step 12 — Localize `widgets/metagame_analysis.py` and `widgets/splash_frame.py`

**Files:** `widgets/metagame_analysis.py`, `widgets/splash_frame.py`
**What:** Small files; same locale pattern.

- `metagame_analysis.py`: frame title, 4 labels, refresh button, ready label, changes header, dynamic status
- `splash_frame.py`: frame title, loading label

---

### Step 13 — Localize `widgets/panels/card_inspector_panel.py`

**File:** `widgets/panels/card_inspector_panel.py`
**What:** Add `labels: dict[str, str] | None = None` constructor parameter (same pattern as other panels).
Replace `"Select a card to inspect."` (initial + reset) and `"Loading printing…"`.

Update `app_frame.py` `_build_card_inspector` to pass `labels` dict.

---

## After All Steps Complete

1. Verify all `MESSAGES` keys have matching `en-US` and `pt-BR` entries.
2. Run `tests/test_i18n.py` — add a completeness check that both locales have identical key sets.
3. Switch app language to `pt-BR` via the language selector and manually verify each widget.
4. Confirm standalone widgets (`mtgo-opponent-tracker`, `mtgo-match-history`, etc.) display pt-BR
   when the saved language is `pt-BR`.
5. Open a PR targeting `main`.
