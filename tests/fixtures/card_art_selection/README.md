# Card Art Selection Fixture

Offline fixture for backend art-selection work. It contains one chosen card for each requested color-identity bucket, all Scryfall printings for those exact card names, cached local Scryfall images where available, and deterministic placeholder images for uncached variants.

Files:
- `manifest.json`: category-to-card mapping and fixture summary.
- `scryfall_cards.json`: complete selected Scryfall card records with `image_uris` rewritten to relative fixture files and `source_image_uris` preserving the original Scryfall URLs.
- `printings_index.json`: compact backend-friendly printings index, including `full_art`, treatment flags, collector numbers, and local image paths.
- `images/`: local images for every printing and image size. The generator copies cached `small`, `normal`, `large`, and `png` files when present; `art_crop` and `border_crop` are deterministic placeholders unless those caches exist locally.

Regenerate with `python scripts/generate_card_art_selection_fixture.py` after refreshing `cache/card_images/bulk_data.json`.
