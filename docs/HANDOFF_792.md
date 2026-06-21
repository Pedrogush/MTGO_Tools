# Handoff — Issue #792: Deckbuilder card art selection (wx UI wiring)

**Status: all 4 parts of #792 are now implemented** on branch
`feat/792-deckbuilder-printing-dropdown-and-normalise` (PR #794).
Parts 3 & 4 landed first; Parts 1 & 2 (board↔inspector art sync + save control)
are done as of the commit that adds this note. Sections below are kept as the
design record; the "what was built for parts 1 & 2" summary is at the very end.

---

## 0. IMPORTANT: everything is verifiable from WSL. Do not skip live verification.

This repo runs and is driven from WSL via the Windows interop bridge (`/init` + `cmd.exe`),
using the Windows venv at `env\Scripts\python.exe`. The full pytest suite, ruff/black,
and the real GUI app (launch + screenshot + drive) all work from this WSL shell.

### Run tests / lint (Windows interpreter, has wx)
```bash
# Full suite (~45s)
/init "$(command -v cmd.exe)" /c "env\\Scripts\\python.exe -m pytest tests/ -q"
# A single file
/init "$(command -v cmd.exe)" /c "env\\Scripts\\python.exe -m pytest tests/test_deck_printing.py -q"
# Lint/format run fine on the WSL (Linux) python — they don't import wx
python -m ruff check <files>
python -m black <files>
```
Note: pure imports like `from services.deck_service import DeckService` pull in
`utils.constants` → `import wx`, so anything touching them must run under the
**Windows** python above, not WSL python.

### Launch + drive + screenshot the real app (the automation/ CLI)
Launch in the background (keep the port consistent), then poll `ping` until ready:
```bash
# 1) Launch (run_in_background). Logs go to the file you redirect to.
/init "$(command -v cmd.exe)" /c "env\\Scripts\\python.exe main.py --automation --automation-port 19853" > /tmp/mtgo_app.log 2>&1

# 2) Wait for readiness
/init "$(command -v cmd.exe)" /c "env\\Scripts\\python.exe -m automation.cli --port 19853 ping"     # -> status: ok

# 3) Useful drive commands
/init "$(command -v cmd.exe)" /c "env\\Scripts\\python.exe -m automation.cli --port 19853 screenshot --path screenshots/x.png"
/init "$(command -v cmd.exe)" /c "env\\Scripts\\python.exe -m automation.cli --port 19853 list-decks"
/init "$(command -v cmd.exe)" /c "env\\Scripts\\python.exe -m automation.cli --port 19853 select-deck --index 0"
/init "$(command -v cmd.exe)" /c "env\\Scripts\\python.exe -m automation.cli --port 19853 load-deck --file _deck.txt"   # inline --text breaks on spaces; use --file
/init "$(command -v cmd.exe)" /c "env\\Scripts\\python.exe -m automation.cli --port 19853 get-zone-cards --zone main"
/init "$(command -v cmd.exe)" /c "env\\Scripts\\python.exe -m automation.cli --port 19853 click --name <button>"
/init "$(command -v cmd.exe)" /c "env\\Scripts\\python.exe -m automation.cli --port 19853 list-widgets"
/init "$(command -v cmd.exe)" /c "env\\Scripts\\python.exe -m automation.cli --port 19853 close-app"
```
Screenshots land under `%TEMP%` (`C:\Users\pedro\AppData\Local\Temp\...`), readable
from WSL at `/mnt/c/Users/pedro/AppData/Local/Temp/...`. Crop+upscale a region with a
tiny PIL script run through the Windows python to read small UI text. Full CLI command
list and video-capture notes are in `automation/README.md`.

Caveat found this session: the `click` command targets named buttons, **not** native
`wx.Menu` popups. To verify a menu-driven action either (a) drive the underlying handler
state and assert via `get-zone-cards`/`get-deck` (what I did for #794), or (b) consider
adding a small automation hook if you need to assert the menu itself. The printing index
loads automatically on app start (the deck that auto-loads already exercises it).

---

## 1. Background — what exists

**#787 (merged) — pure-Python foundation**, all in `services/deck_service/printing.py`
(re-exported from `services.deck_service`, exposed on `DeckService` via
`DeckPrintingMixin` in `printing_service.py`):
- `format_decklist_on_load(text, index)`, `parse_printed_decklist(text, index)`
- `decklist_with_oldest_printings`, `_newest_printings`, `_full_art_printings`,
  `_newest_printings_by(when)`, `_printings_after(when)`, `_printings_to_agnostic`
- **#794 added** `apply_printing_mode(text, index, mode, when=None)` + the mode
  constants `MODE_*`, `PRINTING_MODES`, `DATE_MODES`.

A *printing index* is `name_lower -> [printing, ...]`, each printing a dict with
`id` (Scryfall UUID), `set`, `set_name`, `collector_number`, `released_at`, `full_art`.
It is exactly `ImageService.bulk_data_by_name` (`controller.image_service.bulk_data_by_name`),
built by `services/image_service/printing_index.py`. `PRINTING_INDEX_VERSION = 4`.

**#794 (this branch) — parts 3 & 4 done:**
- Part 3: "Art" dropdown on the mainboard header (`Grid | Table | Pile | Art`) →
  `card_table_panel/frame.py` (`_open_printing_menu`, `_on_printing_choice`,
  `on_printing_mode` ctor param) → wired in `center_panel.py` (`_handle_printing_mode`,
  only for `zone == "main"`).
- Part 4: `_normalize_deck_printings` in
  `widgets/frames/app_frame/handlers/deck_content.py`, called at the top of
  `_on_deck_content_ready`. Guarded so normalisation never drops a card.
- Supporting: `DeckParser._iter_entries` (`services/deck_service/parser.py`) strips a
  trailing UUID printing-id so `analyze_deck`/stats tolerate pointer-carrying lists.
- i18n: `tabs.view.printing*` keys in `utils/i18n/_en_us/tabs.py` and `_pt_br/tabs.py`
  (the locale test requires both to have identical key sets — update both).

---

## 2. Remaining work — Part 1 (art sync) and Part 2 (save control)

The headline feature: the deck zones (mainboard/sideboard board art) should show the
**same printing** the user is looking at in the card inspector, and the user should be
able to **persist** that choice per card.

### The core gap to solve first
The board views look up card images **by name only**, ignoring any chosen printing:
- `widgets/panels/card_table_panel/grid_view.py` — `_image_worker` calls
  `self._get_card_image(candidate_name, "normal")` (candidates from
  `card_render.build_image_name_candidates`).
- `widgets/panels/card_table_panel/pile_view.py` — `_image_worker` calls
  `self._get_card_image(name, "normal")`.

The image cache *can* resolve a specific printing already (used by the inspector):
- `image_cache.get_image_paths_by_uuid(uuid, "normal")`
- `image_cache.get_image_path_for_printing(name, set_code, size)`
(`image_cache = controller.get_image_cache()`).

So Part 1 needs a **per-card printing selection map** threaded into the board image
lookup, plus a request to download a specific printing's image when it isn't cached
(mirror the inspector's `queue_card_image_download` via `CardImageRequest`).

### Suggested design (keep the pure core; isolate wx glue)

**Selection state (single source of truth).** Add a per-deck map
`card_name_lower -> {"uuid": str|None, "set": str|None}` owned by the controller/repo,
e.g. on `deck_repo` alongside the current deck text (see `repositories/deck_repository/ui_state.py`:
`get_current_deck_text`/`set_current_deck_text`). Persist it in the deck `metadata` JSON
(the `decks` table already has a `metadata` column — `repositories/deck_repository/database.py`)
**and/or** keep the decklist text itself as the canonical form using the existing
printing-id pointer format (the parser + `parse_printed_decklist` already round-trip it).
Recommended: derive the map from the loaded deck text on load (via `parse_printed_decklist`
+ resolving pointers), and write choices back into the deck text so save/load is automatic
and matches #787's "extended decklist" intent.

**Part 1a — inspector → board.** The inspector already emits printing changes:
- `widgets/panels/card_inspector_panel/handlers.py`:
  `set_printing_changed_handler(cb)` / `_emit_printing_changed()` fire `cb(printing_dict|None)`
  on prev/next and on async printings load. Today it's wired in
  `widgets/frames/app_frame/frame/right_panel.py:117` to `card_panel.update_printing`.
- Add a second subscriber (or wrap that callback) that records the selection for the
  currently-inspected card (`inspector_current_card_name`) and tells the board to
  refresh just that card's art with the chosen `uuid`/`set`.
- Board refresh hook: `card_table_panel` already has `refresh_card_image(name)` →
  grid view `refresh_image(name)` / `_patch_card_on_canvas(name)`; extend the image
  worker to consult the selection map (or pass the chosen uuid/set into the refresh call).

**Part 1b — board → inspector.** When the user selects a card in a zone, the inspector
is updated via `_handle_card_focus` (`center_panel`/app_frame). Make the inspector open
on the **selected** printing for that card: after `update_card`, set
`inspector_current_printing` to the index of the saved printing (match by `id` in
`inspector_printings`) before `_load_current_printing_image`. Look at
`card_inspector_panel/handlers.py` `update_card` / `_load_card_image_and_printings`.

**Part 2 — save control in the inspector.** Per the issue, two modes:
- a checkmark that **autosaves** the last-scrolled-to printing, or
- an explicit **save button** shown when the checkmark is off.
Build it in `widgets/panels/card_inspector_panel/frame.py` next to the existing
prev/next nav (`nav_panel`, `prev_btn`/`next_btn`, `printing_label` — the wx idiom is
`wx.Button(parent, label=...)` + `stylize_button` + `Bind(wx.EVT_BUTTON, handler)`; for
the checkbox use `wx.CheckBox`). On save (or on printing-change when autosave is on),
call a controller callback that writes the selection into the per-deck map + deck text +
metadata, then triggers the board refresh from Part 1a. Wire the callback in
`right_panel.py` where the other inspector handlers are set
(`set_image_request_handlers`, `set_printings_request_handler`, `set_printing_changed_handler`).

### Keep it testable
Put any non-trivial decision logic (e.g. "given inspector printings + a saved selection,
which index is current", or "merge a selection into deck text") as **pure functions** in
`services/deck_service/printing.py` (or a sibling) and unit-test them in
`tests/test_deck_printing.py` — that file's `INDEX` fixture and the real-fixture test at
`tests/fixtures/card_art_selection/printings_index.json` are the pattern to follow. The
parser already has UUID-strip tests in `tests/test_deck_service.py`.

---

## 3. Verification checklist for the next session (do these live)

1. `ruff check` + `black` the changed files.
2. Full suite via the Windows interop command in §0 — must stay green (currently
   **1493 passed, 5 skipped**; the i18n key-parity test will fail if you add an en-US
   string without the pt-BR mirror).
3. Launch the app (§0), load a deck, then:
   - scroll a card's printing in the inspector → confirm the board art for that card
     follows (screenshot, crop the card cell);
   - select a card on the board → confirm the inspector opens on the saved printing;
   - toggle the save checkmark / press save → reload the deck (`select-deck` again) →
     confirm the chosen printing persists (re-screenshot, and/or `get-deck` to see the
     printing-id pointer survived in the deck text).
4. Update PR #794 (or open a follow-up PR) and reference #792.

---

## 4. Key file map (quick reference)

| Area | File |
|---|---|
| Pure printing helpers + dispatch | `services/deck_service/printing.py`, `printing_service.py` |
| Deck text parser (UUID-strip) | `services/deck_service/parser.py` |
| Printing index (build/shape) | `services/image_service/printing_index.py`, `schemas.py` |
| Deck load/store path (Part 4) | `widgets/frames/app_frame/handlers/deck_content.py` (`_on_deck_content_ready`, `_normalize_deck_printings`) |
| Deck stats re-parse | `widgets/panels/deck_stats_panel/handlers.py` (`update_stats` → `analyze_deck`) |
| Board zones + dropdown (Part 3) | `widgets/panels/card_table_panel/frame.py`, `grid_view.py`, `pile_view.py`, `card_render.py` |
| Zone-table wiring | `widgets/frames/app_frame/frame/center_panel.py` (`_create_zone_table`, `_handle_printing_mode`) |
| Card inspector (Parts 1 & 2) | `widgets/panels/card_inspector_panel/frame.py`, `handlers.py` |
| Inspector ↔ app wiring | `widgets/frames/app_frame/frame/right_panel.py` |
| Image cache (printing-aware lookup) | `controller.get_image_cache()` → `get_image_paths_by_uuid`, `get_image_path_for_printing` |
| Deck repo current-deck state / metadata | `repositories/deck_repository/ui_state.py`, `database.py` |
| i18n (mirror en-US + pt-BR) | `utils/i18n/_en_us/tabs.py`, `utils/i18n/_pt_br/tabs.py` |
| Automation CLI | `automation/cli.py`, `automation/README.md` |

---

## 5. What was built for parts 1 & 2 (this session)

**Pure core (`services/deck_service/printing.py`, tested in `tests/test_deck_printing.py`):**
- `extract_printing_selections(text, index)` → `{name_lower: {"uuid","set"}}` for
  every card that pins a specific printing (the runtime "what art is this card
  showing" map).
- `selected_printing_index(printings, selection)` → which inspector printing
  index to open on (uuid match, then set, else 0).
- `merge_printing_selection(text, index, name, uuid, set_code=None)` → re-point
  one card's line in the decklist text, preserving every other line's pointer.
- All three delegated on `DeckPrintingMixin`.

**Selection map (single source of truth): `AppFrame._printing_selections`**
(`widgets/frames/app_frame/frame/__init__.py`). Populated on every deck load by
`_capture_printing_selections` (`handlers/deck_content.py`) from the *original*
text — before `format_decklist_on_load` normalisation, which forces a uniform
precision and would otherwise strip individual pointers. Cards whose printing
changed vs. the previous deck are tracked in `_changed_printing_names` and their
board art is force-refreshed via `wx.CallAfter(_apply_changed_printing_art)`
(a plain `set_cards` reuses the name-keyed cached bitmap and keeps the old art).

**Part 1 — board art follows the chosen printing.** `CardTablePanel` →
`DeckGridView`/`DeckPileView` take a `get_printing_image` callback; their image
workers try it first (printing-specific path via `image_cache.get_image_by_uuid`
/ `get_image_path_for_printing`, queuing a download if missing) before the
name-based candidates. The resolver is `AppFrame._get_printing_image`
(`handlers/card_tables.py`). Both views gained a force-reload `refresh_image`
used by `refresh_card_image`.
- 1a inspector→board: `set_printing_selected_handler` fires on user prev/next
  (and Save) → `AppFrame._on_inspector_printing_selected` records the selection
  + `_refresh_board_card_art(name)`.
- 1b board→inspector: `_handle_card_focus`/`_flush_hover_preview` pass the saved
  `selection` into `update_card`, and the inspector opens on it via
  `selected_printing_index` (sync + async printing-load paths).

**Part 2 — save control** in the inspector (`card_inspector_panel/frame.py` +
`handlers.py`): an "Auto-save art" checkbox (persists every scrolled-to printing)
and a "Save art" button (shown when auto-save is off). Persistence merges the
chosen printing-id pointer into `current_deck_text` (`_persist_printing_selection`),
so copy/save-to-file/DB carry it (`build_deck_text` reads `current_deck_text`).
The image column's fixed height was extended so the controls aren't clipped.

**Live verification done (WSL automation):** loaded a 2-card deck pinning Island
to two different cached printings (`fbb` vs `eld`); the mainboard grid cell
re-rendered to the matching art (screenshot diff localised to that one cell), and
`get-deck` round-tripped the printing-id pointers. Full suite: 1501 passed.

**Known limitations / follow-ups:** inspector save-control behaviour (autosave +
Save button) was verified by unit tests + code, not by a live click (the
automation CLI can't drive the inspector nav/checkbox or board-card selection).
Inspector strings are hardcoded English to match the rest of that panel (no
`_t`), so no i18n keys were added.
