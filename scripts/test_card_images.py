#!/usr/bin/env python3
"""Test script for card image downloader backend.

Usage:
    # Download bulk metadata only
    python scripts/test_card_images.py --metadata-only

    # Download first 100 cards (test mode)
    python scripts/test_card_images.py --test

    # Download all normal-sized images
    python scripts/test_card_images.py --size normal

    # Download all small thumbnails
    python scripts/test_card_images.py --size small

    # Show cache statistics
    python scripts/test_card_images.py --stats
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from services.image_service import (
    BulkImageDownloader,
    download_bulk_images,
    get_cache,
    get_cache_stats,
    get_card_image,
)


def run_metadata_download():
    """Test downloading bulk metadata."""
    print("=" * 60)
    print("Testing Bulk Metadata Download")
    print("=" * 60)

    cache = get_cache()
    downloader = BulkImageDownloader(cache)

    success, msg = downloader.download_bulk_metadata(force=True)
    print(f"\nResult: {'✓ SUCCESS' if success else '✗ FAILED'}")
    print(f"Message: {msg}\n")

    if success:
        stats = get_cache_stats()
        print(f"Total cards in bulk data: {stats.get('bulk_total_cards', 0)}")
        print(f"Bulk data date: {stats.get('bulk_data_date', 'N/A')}")

    return success


def run_image_download(size: str = "normal", max_cards: int = 100):
    """Test downloading a limited number of images."""
    print("=" * 60)
    print(f"Testing Image Download ({max_cards} cards, {size} size)")
    print("=" * 60)

    def progress(completed, total, message):
        percent = (completed / total) * 100
        print(f"\rProgress: {completed}/{total} ({percent:.1f}%) - {message}", end="", flush=True)

    result = download_bulk_images(size=size, max_cards=max_cards, progress_callback=progress)

    print("\n")  # New line after progress
    print(f"\nResult: {'✓ SUCCESS' if result.get('success') else '✗ FAILED'}")

    if result.get("success"):
        print(f"Total processed: {result.get('total', 0)}")
        print(f"Downloaded: {result.get('downloaded', 0)}")
        print(f"Skipped (cached): {result.get('skipped', 0)}")
        print(f"Failed: {result.get('failed', 0)}")
    else:
        print(f"Error: {result.get('error', 'Unknown')}")

    return result.get("success", False)


def download_full_database(size: str = "normal"):
    """Download the entire card image database."""
    print("=" * 60)
    print(f"Downloading Full Card Image Database ({size} size)")
    print("=" * 60)
    print("\n⚠️  WARNING: This will download ~80,000 images!")
    print("This may take 30-60 minutes depending on your connection.")
    print("Images from cards.scryfall.io have no rate limits.\n")

    confirm = input("Continue? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        return False

    def progress(completed, total, message):
        percent = (completed / total) * 100
        elapsed_str = ""
        if completed > 0:
            # Estimate remaining time
            rate = completed / (completed * 0.1)  # Rough estimate
            remaining = (total - completed) / rate if rate > 0 else 0
            elapsed_str = f" - ETA: {remaining:.0f}s"

        print(
            f"\rProgress: {completed}/{total} ({percent:.1f}%){elapsed_str} - {message}",
            end="",
            flush=True,
        )

    result = download_bulk_images(
        size=size,
        max_cards=None,
        progress_callback=progress,  # Download all
    )

    print("\n")  # New line after progress
    print("\n" + "=" * 60)
    print(f"Result: {'✓ SUCCESS' if result.get('success') else '✗ FAILED'}")

    if result.get("success"):
        print(f"\nTotal processed: {result.get('total', 0)}")
        print(f"Downloaded: {result.get('downloaded', 0)}")
        print(f"Skipped (cached): {result.get('skipped', 0)}")
        print(f"Failed: {result.get('failed', 0)}")
        print("\n✓ Full database download complete!")
    else:
        print(f"Error: {result.get('error', 'Unknown')}")

    return result.get("success", False)


def show_stats():
    """Show cache statistics."""
    print("=" * 60)
    print("Card Image Cache Statistics")
    print("=" * 60)

    stats = get_cache_stats()

    print(f"\nUnique cards cached: {stats.get('unique_cards', 0)}")
    print(f"Bulk data date: {stats.get('bulk_data_date', 'Not downloaded')}")
    print(f"Total cards in bulk data: {stats.get('bulk_total_cards', 'N/A')}")

    print("\nImages by size:")
    for size, count in stats.get("by_size", {}).items():
        print(f"  {size:8s}: {count:6d} images")

    # Test lookup
    print("\n" + "-" * 60)
    print("Testing card lookup:")
    test_cards = ["Lightning Bolt", "Counterspell", "Black Lotus"]

    for card_name in test_cards:
        path = get_card_image(card_name, "normal")
        status = "✓ Found" if path else "✗ Not cached"
        print(f"  {card_name:20s}: {status}")
        if path:
            print(f"    → {path}")


def main():
    parser = argparse.ArgumentParser(description="Test card image downloader backend")
    parser.add_argument(
        "--metadata-only", action="store_true", help="Only download bulk metadata JSON"
    )
    parser.add_argument("--test", action="store_true", help="Test mode: download first 100 cards")
    parser.add_argument(
        "--size",
        choices=["small", "normal", "large", "png"],
        default="normal",
        help="Image size to download",
    )
    parser.add_argument("--full", action="store_true", help="Download the entire card database")
    parser.add_argument("--stats", action="store_true", help="Show cache statistics")
    parser.add_argument("--max-cards", type=int, help="Maximum number of cards to download")

    args = parser.parse_args()

    # Configure logger
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    try:
        if args.stats:
            show_stats()
        elif args.metadata_only:
            run_metadata_download()
        elif args.test:
            # Download metadata first
            run_metadata_download()
            # Then download 100 images
            run_image_download(size=args.size, max_cards=100)
            # Show stats
            show_stats()
        elif args.full:
            # Download metadata first
            cache = get_cache()
            downloader = BulkImageDownloader(cache)
            success, msg = downloader.download_bulk_metadata()
            if not success:
                print(f"Failed to download metadata: {msg}")
                return 1
            # Download all images
            download_full_database(size=args.size)
            # Show final stats
            show_stats()
        elif args.max_cards:
            # Custom number of cards
            cache = get_cache()
            downloader = BulkImageDownloader(cache)
            success, msg = downloader.download_bulk_metadata()
            if not success:
                print(f"Failed to download metadata: {msg}")
                return 1
            run_image_download(size=args.size, max_cards=args.max_cards)
            show_stats()
        else:
            parser.print_help()
            return 1

        return 0

    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        return 130
    except Exception as exc:
        logger.exception("Test failed")
        print(f"\n✗ Error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
