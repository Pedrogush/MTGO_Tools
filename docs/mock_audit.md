# Test Mock Audit

This document inventories every test file that uses mocking (via `unittest.mock`, `pytest`'s `monkeypatch`, or `MagicMock`) and notes what is mocked, why it is a concern, and what a no-mock replacement would look like.

The goal is to migrate tests toward exercising real code paths ("hot paths") so that requirements are validated end-to-end.

---

## Summary Table

| File | Mock mechanism | What is mocked | Risk level |
|---|---|---|---|
| `test_radar_service.py` | `MagicMock` | Entire `MetagameRepository` + `DeckService` | HIGH — no real logic exercised |
| `test_search_service.py` | `Mock` / `SimpleNamespace` | Entire `CardRepository` | HIGH — filters tested against fake cards |
| `test_card_repository.py` | `Mock` | Entire `CardDataManager` | HIGH — adapter layer never touches real data |
| `test_collection_service.py` | `Mock` | Entire `CardRepository` | HIGH — service tested against fake repo |
| `test_archetype_resolver.py` | `MagicMock` | Entire `MetagameRepository` | MEDIUM — resolver logic OK but repo seam is fake |
| `test_identify_opponent_radar.py` | `MagicMock` / `patch` | `wx`, `RadarService`, `MetagameRepository`, `find_archetype_by_name` | HIGH — GUI tests test nothing real |
| `test_mtggoldfish.py` | `Mock` / `patch` | `requests.get`, `fetch_deck_text`, `ARCHETYPE_LIST_CACHE_FILE` | MEDIUM — network unavoidable; file path patch is fine |
| `test_metagame_repository.py` | `monkeypatch` | `get_archetypes_from_web`, `_get_mtgo_decks_from_db` | MEDIUM — bypasses network; DB seam is reasonable |
| `test_card_data_refresh.py` | `monkeypatch` | `requests.head`, `requests.get` | LOW — network stub; real parse logic runs |
| `test_card_images_cache.py` | `monkeypatch` | `BULK_DATA_CACHE`, `_fetch_bulk_metadata`, `_get_image_path_from_db` | LOW — path/IO stubs; cache logic runs |
| `test_card_images_aliases.py` | `monkeypatch` | `IMAGE_CACHE_DIR`, `BULK_DATA_CACHE`, `PRINTING_INDEX_CACHE` | LOW — path redirect only |
| `test_opponent_detection.py` | `monkeypatch` | `pygetwindow.getAllTitles` | LOW — OS API stub; parsing logic runs |
| `test_mtgo_bridge_client.py` | `monkeypatch` | `MTGO_BRIDGE_PATH` env var | LOW — env redirect only |
| `test_store_service.py` | `monkeypatch` | `Path.read_text`, `atomic_write_json` | LOW — IO error simulation |
| `test_mana_icon_factory.py` | `monkeypatch` | `wx.Image` constructor | LOW — wx unavailable in CI |
| `test_card_box_panel_logic.py` | `MagicMock` | `wx` module stub | LOW — logic under test doesn't touch wx |
| `test_image_service.py` | `monkeypatch` | `time.sleep`, `time.monotonic` | LOW — time control; HTTP logic runs |
| `test_perf.py` | `patch` | `utils.perf.logger` | TRIVIAL — verifying log calls |

---

## HIGH-Priority Files (replace mocks with real implementations)

### `tests/test_radar_service.py` (LOC 1–340)

**What is mocked:**
- Lines 11–27: `MetagameRepository` — fully replaced with `MagicMock()`. Methods `get_decks_for_archetype`, `download_deck_content` are faked.
- Lines 18–27: `DeckService` — fully replaced with `MagicMock()`. Method `analyze_deck` is faked.
- Lines 95–135: Test `test_calculate_radar_success` seeds mock return values for all repo/service calls.
- Line 317: `download_deck_content.return_value = "4 Lightning Bolt"` — never exercises real deck parsing.

**Why it is a problem:** `RadarService` is instantiated against fake collaborators. The test validates that `RadarService` wires calls together correctly, but never exercises `MetagameRepository` fetching real archetype data or `DeckService` analyzing a real deck.

**Replacement approach:** Build a small in-memory `MetagameRepository` stub that holds fixture deck text (real MTGO-format strings). Wire a real `DeckService`. Integration test at the `RadarService.calculate_radar()` level with fixture archetypes.

---

### `tests/test_search_service.py` (LOC 1–444)

**What is mocked:**
- Lines 34–35, 44–46, 55–57, 78–79, 96–97, 113–114, 131–132, 148–149, 164–165, 182–183, 199–200, 242–243, 252–254, 265–266, 274–275, 291–292, 305–306, 321–322, 342–343, 357–358, 371–372, 390–391, 402–403, 414–415, 428–429, 441–442: `mock_repo = SimpleNamespace()` with `Mock(return_value=...)` for `is_card_data_loaded`, `search_cards`.
- Lines 9–31: `create_mock_card()` helper fabricates card dicts; no real `CardEntry` objects are used.

**Why it is a problem:** Filter logic (`SearchService.filter_by_color`, `filter_by_type`, etc.) is tested against hand-crafted dicts rather than real `CardEntry` / `CardIndex` objects. If the schema changes, tests won't catch it.

**Replacement approach:** Load a small real card index fixture from `tests/fixtures/` (a subset of AtomicCards JSON with ~20 real cards). Instantiate a real `CardRepository` + `CardDataManager` pointing at the fixture. Test filters against real `CardEntry` structs.

---

### `tests/test_card_repository.py` (LOC 1–350)

**What is mocked:**
- Lines 13–30: `mock_card_manager` fixture replaces `CardDataManager` with a `Mock`. Methods `get_card`, `search_cards`, `get_printings`, `ensure_latest` are all stubbed.
- Lines 43–346: Every test calls `card_repository` (backed by mock manager) and asserts delegation behavior.

**Why it is a problem:** `CardRepository` is an adapter around `CardDataManager`. Tests confirm the adapter delegates calls — but never exercise the actual `CardDataManager` loading, parsing, or schema validation.

**Replacement approach:** Use a real `CardDataManager` pointed at a small fixture JSON file (same fixture as `test_card_data_refresh.py` uses). Test `CardRepository` against the real manager so that schema regressions surface.

---

### `tests/test_collection_service.py` (LOC 1–310)

**What is mocked:**
- Lines 13–37: `mock_card_repo` fixture builds a `Mock()` with `get_collection_cache_path`, `load_collection_from_file`, and `get_card_metadata` all stubbed.
- Lines 56–95: `load_collection_from_file` re-mocked per test with different return values.
- Line 163, 170, 172, 175, 86, 94: Mock reassignment inside tests.

**Why it is a problem:** `CollectionService` logic is tested but the actual file-loading and card-lookup code paths in `CardRepository` are never exercised. Integration edge cases (malformed JSON, schema mismatch) are invisible.

**Replacement approach:** Use a real `CardRepository` with a small fixture collection JSON. Tests write a temp collection file and load it through the real service stack.

---

### `tests/test_identify_opponent_radar.py` (LOC 1–145)

**What is mocked:**
- Lines 11–26: `wx` module is fully replaced with `MagicMock`. Classes `Frame`, `Panel`, `StaticText`, `Button`, `Timer`, `BoxSizer` are all mocked.
- Lines 30–47: `RadarService` replaced with `MagicMock`.
- Lines 45–47: `MetagameRepository` replaced with `MagicMock`.
- Lines 62–63: `find_archetype_by_name` patched out.
- Lines 80–84, 101–112, 114–119: Tests that "test" behavior by calling mocks and asserting mock calls.

**Why it is a problem:** These tests do not exercise any real code path in `identify_opponent.py`. They primarily verify mock call signatures. The three tests that exist are currently pre-existing failures in CI (the `test_identify_opponent_radar` group).

**Replacement approach:** Move pure-logic unit tests (radar calculation, archetype resolution) to their own test files without wx dependency. GUI behavior (clear on opponent change, etc.) should be covered by `automation/e2e_tests.py` instead.

---

### `tests/test_archetype_resolver.py` (LOC 1–65)

**What is mocked:**
- Lines 26–27: `mock_repo` fixture creates `MagicMock()` for `MetagameRepository`.
- Lines 35–61: All tests call `find_archetype_by_name(..., mock_repo)` where `mock_repo.get_archetypes_for_format.return_value` is a hardcoded list.

**Why it is a problem:** `find_archetype_by_name` logic is tested against a fake list — this is actually reasonable for pure-function tests, but the archetype list is trivial and doesn't reflect real archetype name formats from MTGGoldfish.

**Replacement approach:** Keep the pure-function logic tests. Add a small fixture with ~10 real archetype names scraped from MTGGoldfish (stored in `tests/fixtures/archetypes_modern.json`) to ensure the fuzzy matching handles real data. Remove `MagicMock` in favor of a plain list passed directly.

---

## MEDIUM-Priority Files (network stubs are acceptable; other mocks need review)

### `tests/test_mtggoldfish.py` (LOC 1–460)

**What is mocked:**
- Lines 7: `from unittest.mock import Mock, patch`
- Lines 145–241: `patch("navigators.mtggoldfish.ARCHETYPE_LIST_CACHE_FILE", temp_archetype_list_file)` — redirects cache file path. This is acceptable (path redirect to tmp_path).
- Lines 245–451: `@patch("navigators.mtggoldfish.requests.get")` — stubs HTTP. `mock_response.text = SAMPLE_METAGAME_HTML` (large HTML fixtures defined in file). `fetch_deck_text` is patched in `test_download_deck`.

**Assessment:** Network mocking is acceptable in isolation (we can't hit MTGGoldfish in CI). The HTML fixtures are realistic and the parsing logic runs against them. The `fetch_deck_text` patch in `test_download_deck` is unnecessary — the function is in the same module and could be tested with a real response fixture instead.

**Improvement:** Extract fixture HTML to `tests/fixtures/` files. Remove the `fetch_deck_text` mock and test via a fixture file.

---

### `tests/test_metagame_repository.py` (LOC 200–370)

**What is mocked:**
- Lines 225, 257, 275, 296, 357: `monkeypatch.setattr(repo, "get_archetypes_from_web", ...)` — stubs network call.
- Lines 229, 299, 367: `monkeypatch.setattr(repo, "_get_mtgo_decks_from_db", ...)` — stubs MongoDB query.

**Assessment:** Network and DB stubs are reasonable for unit tests. The repository's cache logic is exercised. Consider adding a separate integration test (skipped by default) that hits MongoDB directly.

---

## LOW-Priority Files (stubs are justified)

### `tests/test_card_data_refresh.py` (LOC 44–400)

`monkeypatch.setattr(card_data.requests, "head"/"get", ...)` — stubs HTTP. Real JSON parsing, file writing, and cache metadata checks all run. Acceptable.

### `tests/test_card_images_cache.py` (LOC 102–363)

`monkeypatch.setattr(card_images, "BULK_DATA_CACHE", bulk_path)` — path redirects. `monkeypatch.setattr(cache, "_get_image_path_from_db", counting_from_db)` — counts DB calls. Cache deduplication logic runs. Acceptable.

### `tests/test_card_images_aliases.py` (LOC 10–40)

Path redirects only. Acceptable.

### `tests/test_opponent_detection.py` (LOC 27–54)

`monkeypatch.setattr(pygetwindow, "getAllTitles", ...)` — OS API stub. Parsing logic is real. Acceptable.

### `tests/test_mtgo_bridge_client.py` (LOC 14–17)

`monkeypatch.setenv("MTGO_BRIDGE_PATH", ...)` — env stub. Acceptable.

### `tests/test_store_service.py` (LOC 56–102)

`monkeypatch.setattr(Path.read_text, ...)` and `atomic_write_json` — IO error simulation. Acceptable; tests error paths that can't be triggered otherwise.

### `tests/test_mana_icon_factory.py` (LOC 9–11)

`monkeypatch.setattr(wx.Image, ...)` — wx unavailable in CI (Linux/WSL). Acceptable until a Windows-only test runner is configured.

### `tests/test_card_box_panel_logic.py` (LOC 14–25)

`MagicMock()` wx stub — the logic under test (`CardBoxPanelLogic`) does not call wx methods; the stub is just to satisfy the constructor. Refactor the constructor to not require a wx panel to test logic, or use a lightweight dataclass.

### `tests/test_image_service.py` (LOC 89–114)

`monkeypatch.setattr(image_service.time, "sleep"/"monotonic", ...)` — time control for retry/backoff tests. Acceptable.

### `tests/test_perf.py` (LOC 69–91)

`patch("utils.perf.logger")` — verifies that a log call was made. Acceptable.

---

## Recommended Action Plan

1. **Create `tests/fixtures/` directory** with:
   - `atomic_cards_mini.json` — ~20 real card objects in AtomicCards format
   - `collection_mini.json` — matching collection entries
   - `archetypes_modern.json` — ~10 real Modern archetype names from MTGGoldfish

2. **Rewrite `test_card_repository.py`** to use a real `CardDataManager` backed by `atomic_cards_mini.json`. Remove all `Mock`.

3. **Rewrite `test_collection_service.py`** to use a real `CardRepository` + fixture files. Remove `Mock`.

4. **Rewrite `test_search_service.py`** to use real `CardEntry` structs from the fixture. Remove `SimpleNamespace` / `Mock`. Keep parametrize-style tests.

5. **Rewrite `test_radar_service.py`** with a minimal in-process `MetagameRepository` that holds fixture deck text strings. Keep `DeckService` real.

6. **Delete `test_identify_opponent_radar.py`** — the tests don't cover real code. Move archetype-resolution cases into `test_archetype_resolver.py`. GUI coverage goes to `automation/e2e_tests.py`.

7. **Improve `test_archetype_resolver.py`** — replace `MagicMock` repo with a plain list argument (the function signature already supports this — pass a list directly, remove `MagicMock` usage).
