"""CLI helper to print collection snapshot fetched via the bridge."""

from __future__ import annotations

from services import mtgo_bridge_service as mtgo_bridge


def dump_collection(limit_cards: int = 15) -> None:
    collection = mtgo_bridge.get_collection_snapshot()
    if not collection:
        print("No collection data returned.")
        return

    name = collection.get("name") or "Collection"
    items = collection.get("items") or []
    print(f"{name} — {len(items)} entries (max {collection.get('maxItems', 'unknown')})")
    for card in items[:limit_cards]:
        qty = card.get("quantity", "?")
        card_name = card.get("name", "Unknown")
        print(f"  {qty}x {card_name}")

    remaining = max(0, len(items) - limit_cards)
    if remaining:
        print(f"  …and {remaining} more")


def main() -> None:
    print("Collection snapshot:")
    dump_collection()


if __name__ == "__main__":
    main()
