"""MongoDB CRUD operations for saved decks."""

from __future__ import annotations

from datetime import datetime

import pymongo
from loguru import logger


class DatabaseMixin:
    """MongoDB persistence for user-saved decks."""

    def _get_db(self):
        if self._db is None:
            if self._client is None:
                self._client = pymongo.MongoClient("mongodb://localhost:27017/")
            self._db = self._client.get_database("lm_scraper")
        return self._db

    def save_to_db(
        self,
        deck_name: str,
        deck_content: str,
        format_type: str | None = None,
        archetype: str | None = None,
        player: str | None = None,
        source: str = "manual",
        metadata: dict | None = None,
    ):
        db = self._get_db()

        deck_doc = {
            "name": deck_name,
            "content": deck_content,
            "format": format_type,
            "archetype": archetype,
            "player": player,
            "source": source,
            "date_saved": datetime.now(),
            "metadata": metadata or {},
        }

        result = db.decks.insert_one(deck_doc)
        logger.info(f"Saved deck '{deck_name}' to database with ID: {result.inserted_id}")
        return result.inserted_id

    def get_decks(
        self,
        format_type: str | None = None,
        archetype: str | None = None,
        sort_by: str = "date_saved",
    ) -> list[dict]:
        db = self._get_db()

        query = {}
        if format_type:
            query["format"] = format_type
        if archetype:
            query["archetype"] = archetype

        decks = list(db.decks.find(query).sort(sort_by, pymongo.DESCENDING))
        logger.debug(f"Retrieved {len(decks)} decks from database")
        return decks

    def load_from_db(self, deck_id):
        db = self._get_db()

        if isinstance(deck_id, str):
            from bson import ObjectId

            deck_id = ObjectId(deck_id)

        deck = db.decks.find_one({"_id": deck_id})
        if deck:
            logger.debug(f"Loaded deck: {deck['name']}")
        else:
            logger.warning(f"Deck with ID {deck_id} not found")

        return deck

    def delete_from_db(self, deck_id) -> bool:
        db = self._get_db()

        if isinstance(deck_id, str):
            from bson import ObjectId

            deck_id = ObjectId(deck_id)

        result = db.decks.delete_one({"_id": deck_id})

        if result.deleted_count > 0:
            logger.info(f"Deleted deck with ID: {deck_id}")
            return True
        else:
            logger.warning(f"Deck with ID {deck_id} not found for deletion")
            return False

    def update_in_db(
        self,
        deck_id,
        deck_content: str | None = None,
        deck_name: str | None = None,
        metadata: dict | None = None,
    ) -> bool:
        db = self._get_db()

        if isinstance(deck_id, str):
            from bson import ObjectId

            deck_id = ObjectId(deck_id)

        update_fields = {"date_modified": datetime.now()}

        if deck_content is not None:
            update_fields["content"] = deck_content
        if deck_name is not None:
            update_fields["name"] = deck_name
        if metadata is not None:
            existing_deck = db.decks.find_one({"_id": deck_id})
            if existing_deck:
                merged_metadata = existing_deck.get("metadata", {})
                merged_metadata.update(metadata)
                update_fields["metadata"] = merged_metadata

        result = db.decks.update_one({"_id": deck_id}, {"$set": update_fields})

        if result.modified_count > 0:
            logger.info(f"Updated deck with ID: {deck_id}")
            return True
        else:
            logger.warning(f"Deck with ID {deck_id} not found or no changes made")
            return False
