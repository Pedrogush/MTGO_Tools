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


def dump_history(limit_items: int = 10) -> None:
    history = mtgo_bridge.get_match_history()
    if not history:
        print("No history data returned.")
        return

    items = history.get("items") or []
    print(f"History items loaded: {len(items)} (loaded={history.get('historyLoaded')})")
    for entry in items[:limit_items]:
        kind = entry.get("kind")
        identifier = entry.get("id")
        stamp = entry.get("startTime")
        print(f"- {kind} #{identifier} started {stamp}")


def main() -> None:
    print("Collection snapshot:")
    dump_collection()
    print()
    print("Match history overview:")
    dump_history()


if __name__ == "__main__":
    main()
