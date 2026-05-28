# Database Usage Report — SQL (SQLite) and MongoDB

Report for issue #473. Inventories every place SQL (SQLite) and MongoDB are
used in the codebase so we can decide whether to consolidate on a single
persistence layer and how to make MongoDB fail fast when it is absent.

## Summary

- **SQLite** is the dominant local-persistence layer. It is used for four
  separate caches/repositories (deck text, format card pool, radar,
  card images), all stored under `cache/`.
- **MongoDB** is used by exactly one feature: the optional "save deck to
  database" path in `DeckRepository.save_to_db` (plus its sibling
  load/update/delete methods). It is declared optional by the README but
  the default client (`MongoClient("mongodb://localhost:27017/")`) uses
  PyMongo's default server-selection timeout, so the first DB use blocks
  for ~30 seconds before raising when MongoDB is not running.
- MongoDB has only **one** call site in product code
  (`DeckWorkflowService.save_deck` -> `deck_repo.save_to_db`). Read/
  update/delete methods on `DatabaseMixin` are not called anywhere outside
  of the class itself or the tests.

Counts (rough, `grep -c` on `*.py`, excluding `__pycache__`):
- `MongoClient` / `pymongo` references: **7**
- `sqlite3` references: **53**

## MongoDB Usage

### Code

| File | Purpose |
| --- | --- |
| `repositories/deck_repository/database.py` | `DatabaseMixin` — CRUD for saved decks (`save_to_db`, `get_decks`, `load_from_db`, `delete_from_db`, `update_in_db`). Creates the default `pymongo.MongoClient("mongodb://localhost:27017/")` lazily inside `_get_db()`. |
| `repositories/deck_repository/repository.py` | `DeckRepository.__init__` accepts an optional `pymongo.MongoClient` and stores it on `self._client`. |
| `repositories/deck_repository/protocol.py` | Typing-only protocol declaring `_client: pymongo.MongoClient \| None`. |
| `repositories/deck_repository/__init__.py` | Docstring referencing the MongoDB mixin. |

### Call sites (product code)

| Caller | Method |
| --- | --- |
| `services/deck_workflow_service.py::DeckWorkflowService.save_deck` | `self.deck_repo.save_to_db(...)` — wrapped in `try/except`; failures are logged as a warning ("Deck saved to file but not database"). |

`load_from_db`, `delete_from_db`, `update_in_db`, and `get_decks` (the
Mongo flavour) have **no callers outside `DatabaseMixin` and the unit
tests** — i.e. they are effectively dead code in the running app today.

### Dependencies / docs

- `requirements.txt`: `pymongo==4.16.0`
- `README.md`: lists MongoDB as an *optional* prerequisite "for deck
  persistence".
- `ATTRIBUTIONS.md`: mentions PyMongo and "MongoDB storage instead of
  SQLite" (carry-over note from an adapted upstream project).
- `ARCHITECTURE.md`: does not call out MongoDB; only the SQLite-backed
  caches appear in the architecture diagram.

### Failure mode (the bug behind this issue)

`_get_db()` constructs `MongoClient("mongodb://localhost:27017/")` without
overriding `serverSelectionTimeoutMS`. PyMongo's default is 30 seconds,
so the first call to any DB op (e.g. `db.decks.insert_one(...)` from
`save_deck`) blocks the calling thread for ~30s and then raises
`ServerSelectionTimeoutError` when MongoDB is not running. In
`DeckWorkflowService.save_deck` this happens *after* the deck has already
been written to disk, so the user sees a multi-second hang on save with
no UI feedback before the warning is logged.

## SQLite Usage

SQLite is used by four independent components, each owning its own
database file under `cache/`.

### Repositories / services

| File | DB file (logical) | Role |
| --- | --- | --- |
| `repositories/deck_text_cache.py` (`DeckTextCache`) | `cache/deck_cache.db` (`DECK_CACHE_DB_FILE`) | Cache of MTGGoldfish deck text bodies; WAL mode, configurable busy timeout. |
| `repositories/format_card_pool_repository/schema.py` + `reads.py` / `writes.py` | `cache/format_card_pool.db` (`FORMAT_CARD_POOL_DB_FILE`) | Per-format aggregated card pool stats. Schema mixin manages connection + DDL. |
| `repositories/format_card_pool_repository/protocol.py` | n/a (typing) | Declares the SchemaMixin/connect protocol. |
| `repositories/radar_repository/schema.py` + `reads.py` / `writes.py` | `cache/radar_cache.db` (`RADAR_CACHE_DB_FILE`) | Cached per-archetype "radar" card-frequency analytics. |
| `repositories/radar_repository/protocol.py` | n/a (typing) | Connect protocol for the radar repository. |
| `services/image_service/disk_cache.py` (`CardImageCache`) | `cache/...` (`IMAGE_DB_PATH` from `services/image_service/schemas.py`) | Metadata index over downloaded card-image files (`card_images` + `bulk_data_meta` tables) with online schema migration for `face_index`. |
| `services/image_service/downloader.py` | same as `CardImageCache.db_path` | Writes new rows during downloads using the cache's connection settings. |
| `services/image_service/path_resolver.py` | n/a (docstring) | References the SQLite-stored `file_path` formats. |
| `scripts/check_card_face_images.py` | uses `IMAGE_DB_PATH` | Diagnostic script that reads the image-cache DB directly. |

### Tests

| File | Touches |
| --- | --- |
| `tests/test_card_images_cache.py` | Opens the image-cache DB via `sqlite3.connect` to assert schema/contents. |

### Configuration / constants

- `utils/constants/timing.py`:
  - `SQLITE_CONNECTION_TIMEOUT_SECONDS = 30.0`
  - `SQLITE_BUSY_TIMEOUT_MS = 30000`
- `utils/constants/paths.py` declares all four cache DB paths under
  `CACHE_DIR`:
  `DECK_CACHE_DB_FILE`, `FORMAT_CARD_POOL_DB_FILE`,
  `RADAR_CACHE_DB_FILE` (and the image DB path is defined in
  `services/image_service/schemas.py`).

### Conventions

All four SQLite stores share a consistent pattern:
- module-level `import sqlite3`
- a `schema.py` (or `_init_database`) bootstrap that calls
  `sqlite3.connect(self.db_path, timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS)`
- WAL / busy-timeout PRAGMAs (deck text cache and image cache)
- Schema is created/migrated in place; no external migration tool.

## Observations relevant to the issue

1. **MongoDB is the outlier.** Four real persistence paths use SQLite;
   one optional path uses MongoDB. The MongoDB path is also the *only*
   one that needs a running external server, and the only one whose
   failure mode is a multi-second hang.
2. **Most of `DatabaseMixin` is unused.** Only `save_to_db` has a real
   caller. `get_decks`, `load_from_db`, `update_in_db`, and
   `delete_from_db` exist only for tests.
3. **Default client has no fast-fail timeout.** A one-line fix
   (`serverSelectionTimeoutMS=...`, plus optionally `connectTimeoutMS`)
   would convert the 30s hang into a sub-second failure that the
   existing `try/except` already handles.
4. **A SQLite-backed `saved_decks` table** would slot in next to the
   four existing caches without adding any new infrastructure, satisfy
   the "pick one and stick to it" goal from the issue, and remove the
   `pymongo` dependency entirely.

## Suggested next steps (not in scope for this report)

- Short term: pass `serverSelectionTimeoutMS=500` (or similar) to the
  default `MongoClient` so optional persistence fails fast.
- Medium term: migrate `DatabaseMixin` to a SQLite-backed
  `SavedDeckRepository` under `cache/saved_decks.db`, drop `pymongo`,
  and remove the MongoDB prerequisite from the README and
  `ATTRIBUTIONS.md`.
