"""Cards MTGO names by their *printing's* name rather than the card's name.

Scryfall's MTGO-only Omenpaths ("Universes Within") reprints keep the Universes
Beyond ``name`` — "Superior Spider-Man" — and carry the name MTGO actually
prints in ``printed_name`` — "Kavaero, Mind-Bitten". MTGO writes decklists with
the printed name, and neither ``/cards/named?exact=`` nor the ``/cards/collection``
name identifiers match it, so before issue #986 those cards resolved nowhere and
the download queue logged a permanent 404.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import types
from typing import Any


class _WxStub(types.ModuleType):
    """A permissive ``wx`` stand-in fabricating attributes on demand."""

    def __getattr__(self, name: str) -> Any:  # noqa: D401 - simple stub
        value: Any = type(name, (), {})
        setattr(self, name, value)
        return value


def _install_wx_stub() -> None:
    """Install a ``wx`` stub only when the real module is unavailable."""
    try:
        import wx  # noqa: F401
    except Exception:
        sys.modules["wx"] = _WxStub("wx")


_install_wx_stub()

import pytest  # noqa: E402

from services import image_service as card_images  # noqa: E402
from services.image_service import local_resolver as local_resolver_module  # noqa: E402
from services.image_service import schemas as card_images_schemas  # noqa: E402
from services.image_service.batch_resolver import (  # noqa: E402
    ScryfallBatchResolver,
    _build_card_index,
    _Entry,
)
from services.image_service.downloader import BulkImageDownloader  # noqa: E402

ORACLE_NAME = "Superior Spider-Man"
PRINTED_NAME = "Kavaero, Mind-Bitten"


def _omenpaths_record(**overrides: Any) -> dict[str, Any]:
    """The shape of the Scryfall record for the Omenpaths printing."""
    record = {
        "name": ORACLE_NAME,
        "printed_name": PRINTED_NAME,
        "id": "uuid-om1-140",
        "set": "om1",
        "set_name": "Omenpaths",
        "collector_number": "140",
        "released_at": "2025-09-23",
        "image_uris": {"normal": "https://cards.example/om1-140.jpg"},
    }
    record.update(overrides)
    return record


def _paper_record() -> dict[str, Any]:
    return {
        "name": ORACLE_NAME,
        "id": "uuid-spm-155",
        "set": "spm",
        "set_name": "Marvel's Spider-Man",
        "collector_number": "155",
        "released_at": "2025-09-26",
        "image_uris": {"normal": "https://cards.example/spm-155.jpg"},
    }


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------


def test_printing_index_aliases_the_printed_name_to_that_printing_only(tmp_path, monkeypatch):
    """The MTGO name must yield printings — and only the printing that shows it."""
    cache_dir = tmp_path / "card_images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    bulk_path = cache_dir / "bulk_data.json"
    bulk_path.write_text(json.dumps([_omenpaths_record(), _paper_record()]), encoding="utf-8")

    monkeypatch.setattr(card_images_schemas, "IMAGE_CACHE_DIR", cache_dir, raising=False)
    monkeypatch.setattr(card_images_schemas, "BULK_DATA_CACHE", bulk_path, raising=False)
    monkeypatch.setattr(
        card_images_schemas, "PRINTING_INDEX_CACHE", cache_dir / "printings.json", raising=False
    )

    data = card_images.ensure_printing_index_cache(force=True)["data"]

    assert [entry["id"] for entry in data[PRINTED_NAME.lower()]] == ["uuid-om1-140"]
    # The oracle name still lists every printing, the Omenpaths one included.
    assert {entry["id"] for entry in data[ORACLE_NAME.lower()]} == {
        "uuid-om1-140",
        "uuid-spm-155",
    }


def test_printed_name_alias_never_shadows_a_real_card_of_that_name(tmp_path, monkeypatch):
    """A printed name that is also a genuine card must not steal that card's key."""
    cache_dir = tmp_path / "card_images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    bulk_path = cache_dir / "bulk_data.json"
    real_card = {
        "name": PRINTED_NAME,
        "id": "uuid-real",
        "set": "xxx",
        "set_name": "Somewhere",
        "collector_number": "1",
        "released_at": "2020-01-01",
    }
    bulk_path.write_text(json.dumps([_omenpaths_record(), real_card]), encoding="utf-8")

    monkeypatch.setattr(card_images_schemas, "IMAGE_CACHE_DIR", cache_dir, raising=False)
    monkeypatch.setattr(card_images_schemas, "BULK_DATA_CACHE", bulk_path, raising=False)
    monkeypatch.setattr(
        card_images_schemas, "PRINTING_INDEX_CACHE", cache_dir / "printings.json", raising=False
    )

    data = card_images.ensure_printing_index_cache(force=True)["data"]

    assert [entry["id"] for entry in data[PRINTED_NAME.lower()]] == ["uuid-real"]


def test_local_bulk_index_resolves_by_printed_name(tmp_path, monkeypatch):
    """The steady-state path must resolve the MTGO name without any API call."""
    cache_dir = tmp_path / "card_images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    bulk_path = cache_dir / "bulk_data.json"
    bulk_path.write_text(json.dumps([_omenpaths_record()]), encoding="utf-8")

    monkeypatch.setattr(card_images_schemas, "IMAGE_CACHE_DIR", cache_dir, raising=False)
    monkeypatch.setattr(card_images_schemas, "BULK_DATA_CACHE", bulk_path, raising=False)

    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=cache_dir / "images.db")
    downloader = BulkImageDownloader(cache)

    resolved = downloader._resolve_card_locally(PRINTED_NAME)

    assert resolved is not None
    assert resolved.id == "uuid-om1-140"


def test_batch_collection_index_keys_the_printed_name():
    """A batched /cards/collection answer must be findable under the MTGO name."""
    index = _build_card_index([_omenpaths_record()])

    assert index[f"name:{PRINTED_NAME.lower()}"]["id"] == "uuid-om1-140"


# ---------------------------------------------------------------------------
# Scryfall fallbacks
# ---------------------------------------------------------------------------


class _Response:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"{self.status_code} Client Error")

    def json(self) -> dict[str, Any]:
        return self._payload


class _NamedThenSearchSession:
    """``/cards/named`` 404s (as Scryfall does) and ``/cards/search`` answers."""

    def __init__(self, search_payload: dict[str, Any], search_status: int = 200) -> None:
        self.search_payload = search_payload
        self.search_status = search_status
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params or {}))
        if url == card_images_schemas.SCRYFALL_CARD_NAMED_URL:
            return _Response(404, {"object": "error", "code": "not_found"})
        return _Response(self.search_status, self.search_payload)


def _downloader_with_session(session: Any) -> BulkImageDownloader:
    downloader = BulkImageDownloader.__new__(BulkImageDownloader)
    downloader.session = session
    return downloader


def test_fetch_card_by_name_falls_back_to_printed_name_search():
    """A 404 from the exact endpoint retries via the search endpoint's ! operator."""
    session = _NamedThenSearchSession({"data": [_paper_record(), _omenpaths_record()]})
    downloader = _downloader_with_session(session)

    card = downloader.fetch_card_by_name(PRINTED_NAME)

    assert card["id"] == "uuid-om1-140"
    search_url, search_params = session.calls[-1]
    assert search_url == card_images_schemas.SCRYFALL_CARD_SEARCH_URL
    assert search_params["q"] == f'!"{PRINTED_NAME}"'


def test_fetch_card_by_name_search_fallback_prefers_the_requested_set():
    """With several printed-name matches, the requested set decides."""
    other_set = _omenpaths_record(id="uuid-other", set="om2", collector_number="7")
    session = _NamedThenSearchSession({"data": [other_set, _omenpaths_record()]})
    downloader = _downloader_with_session(session)

    card = downloader.fetch_card_by_name(PRINTED_NAME, set_code="OM1")

    assert card["id"] == "uuid-om1-140"


def test_fetch_card_by_name_still_raises_when_nothing_matches():
    """A genuinely unknown name keeps its 404: the queue treats it as permanent."""
    session = _NamedThenSearchSession({"object": "error"}, search_status=404)
    downloader = _downloader_with_session(session)

    with pytest.raises(RuntimeError, match="404"):
        downloader.fetch_card_by_name("Not A Real Card")


def test_pick_printed_name_match_prefers_a_printing_that_shows_the_name():
    """Search returns every printing; only some actually print the asked-for name."""
    picked = local_resolver_module._pick_printed_name_match(
        [_paper_record(), _omenpaths_record()], PRINTED_NAME, None
    )

    assert picked["id"] == "uuid-om1-140"


# ---------------------------------------------------------------------------
# Batch resolver fallback
# ---------------------------------------------------------------------------


class _CollectionMissSession:
    """A /cards/collection endpoint that never matches the printed name."""

    def __init__(self) -> None:
        self.posts: list[list[dict[str, str]]] = []

    def post(self, url, json, timeout):  # noqa: A002 - mirror requests' signature
        self.posts.append(json["identifiers"])
        return _Response(200, {"data": [_paper_record()], "not_found": [{"name": PRINTED_NAME}]})


def test_batch_window_retries_names_the_collection_lookup_missed():
    """not_found names go through the single-card path, which searches printed names."""
    session = _CollectionMissSession()
    fetched: list[str] = []

    def fetch_one(name: str, set_code: str | None) -> dict[str, Any]:
        fetched.append(name)
        if name != PRINTED_NAME:
            raise AssertionError(f"unexpected single-card lookup for {name}")
        return _omenpaths_record()

    resolver = ScryfallBatchResolver(session, fetch_one, debounce=0)
    batch = [_Entry(ORACLE_NAME, None, None), _Entry(PRINTED_NAME, None, None)]
    resolver._resolve_batch(batch)

    assert batch[0].result["id"] == "uuid-spm-155"
    assert batch[1].result["id"] == "uuid-om1-140"
    assert fetched == [PRINTED_NAME]


def test_batch_window_leaves_a_genuine_miss_unresolved():
    """A name nothing can resolve still ends as None (a permanent 404 upstream)."""
    session = _CollectionMissSession()

    def fetch_one(name: str, set_code: str | None) -> dict[str, Any]:
        raise RuntimeError("404 Client Error: Not Found")

    resolver = ScryfallBatchResolver(session, fetch_one, debounce=0)
    batch = [_Entry(ORACLE_NAME, None, None), _Entry("Nonexistent Card", None, None)]
    resolver._resolve_batch(batch)

    assert batch[1].result is None
    assert batch[1].error is None


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------


def _cache_with_image(tmp_path, **add_kwargs: Any):
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    image_file = cache.cache_dir / "normal" / "uuid-om1-140.jpg"
    image_file.parent.mkdir(parents=True, exist_ok=True)
    image_file.write_bytes(b"fake")
    cache.add_image(
        uuid="uuid-om1-140",
        name=ORACLE_NAME,
        set_code="om1",
        collector_number="140",
        image_size="normal",
        file_path=image_file,
        **add_kwargs,
    )
    cache._path_cache.clear()
    return cache, image_file


def test_cache_lookup_by_printed_name_finds_the_downloaded_file(tmp_path):
    """Otherwise the grid asks for the MTGO name forever and shows a placeholder."""
    cache, image_file = _cache_with_image(tmp_path, printed_name=PRINTED_NAME)

    assert cache.get_image_path(PRINTED_NAME, "normal") == image_file
    # The oracle name keeps working — the inspector still browses by it.
    assert cache.get_image_path(ORACLE_NAME, "normal") == image_file


def test_cache_printing_lookup_by_printed_name(tmp_path):
    """The download queue's cached check is set+collector qualified."""
    cache, image_file = _cache_with_image(tmp_path, printed_name=PRINTED_NAME)

    assert (
        cache.get_image_path_for_printing(PRINTED_NAME, "OM1", "normal", collector_number="140")
        == image_file
    )
    assert (
        cache.get_image_path_for_printing(ORACLE_NAME, "OM1", "normal", collector_number="140")
        == image_file
    )


def test_cache_lookup_without_printed_name_is_unchanged(tmp_path):
    """Rows written before the column existed still resolve by name."""
    cache, image_file = _cache_with_image(tmp_path)

    assert cache.get_image_path(ORACLE_NAME, "normal") == image_file
    assert cache.get_image_path(PRINTED_NAME, "normal") is None


def test_card_image_cache_migrates_printed_name_column(tmp_path):
    """A database created before #986 gains the column instead of erroring."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = cache_dir / "images.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE card_images (
                uuid TEXT NOT NULL,
                face_index INTEGER NOT NULL DEFAULT 0,
                name TEXT NOT NULL,
                set_code TEXT,
                collector_number TEXT,
                image_size TEXT NOT NULL,
                file_path TEXT NOT NULL,
                downloaded_at TEXT NOT NULL,
                scryfall_uri TEXT,
                artist TEXT,
                PRIMARY KEY (uuid, face_index, image_size)
            )
        """)
        conn.execute(
            "INSERT INTO card_images VALUES (?, 0, ?, 'spm', '155', 'normal', ?, '', NULL, NULL)",
            ("uuid-spm-155", ORACLE_NAME, str(cache_dir / "normal" / "uuid-spm-155.jpg")),
        )
        conn.commit()

    card_images.CardImageCache(cache_dir=cache_dir, db_path=db_path)

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(card_images)")}
        rows = conn.execute("SELECT name, printed_name FROM card_images").fetchall()
    assert "printed_name" in columns
    assert rows == [(ORACLE_NAME, None)]


def test_image_writer_records_the_printing_name_it_downloaded_under():
    """The cache row carries the MTGO name so the next lookup by it hits."""
    from services.image_service.image_writer import _printed_name

    assert _printed_name(_omenpaths_record()) == PRINTED_NAME
    assert _printed_name(_paper_record()) is None
    # Godzilla-style alternates use flavor_name for the same purpose.
    assert (
        _printed_name({"name": "Zilortha, Strength Incarnate", "flavor_name": "Godzilla"})
        == "Godzilla"
    )
