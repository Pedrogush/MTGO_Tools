"""Continuously monitor MTGO Event Tickets / Play Points / Treasure Chests via the bridge watch feed."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from datetime import datetime
from typing import Any

try:
    from datetime import UTC
except ImportError:  # pragma: no cover - Python 3.10 fallback
    UTC = UTC

from services import mtgo_bridge_service as mtgo_bridge


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value, 10)
        except ValueError:
            return None
    return None


def _extract_currency_counts(
    snapshot: Mapping[str, Any] | None,
) -> tuple[int | None, int | None, int | None, str | None]:
    if not isinstance(snapshot, Mapping):
        return None, None, None, None
    tickets = _coerce_int(snapshot.get("eventTickets"))
    play_points = _coerce_int(snapshot.get("playPoints"))
    treasure_chests = _coerce_int(snapshot.get("treasureChests"))
    error = snapshot.get("error")
    if error is not None:
        error = str(error)
    return tickets, play_points, treasure_chests, error


def _format_timestamp(raw: Any) -> str:
    if isinstance(raw, str) and raw:
        return raw
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw, tz=UTC).isoformat()
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def monitor_currency(
    *,
    bridge_path: str | None,
    interval_ms: int,
    once: bool,
) -> int:
    ready, error = mtgo_bridge.ensure_runtime_ready(bridge_path)
    if not ready:
        print(f"MTGO bridge is unavailable: {error or 'unknown error'}", file=sys.stderr)
        return 1

    timeout = max(1.0, interval_ms / 1000.0 * 2.0)
    last_report: tuple[int | None, int | None, int | None, str | None] | None = None

    print("Monitoring Event Tickets / Play Points (Ctrl+C to stop)…")

    try:
        with mtgo_bridge.start_watch(bridge_path=bridge_path, interval_ms=interval_ms) as watcher:
            while True:
                payload = watcher.latest(block=True, timeout=timeout)
                if not isinstance(payload, Mapping):
                    continue

                currency = payload.get("currency")
                tickets, play_points, treasure_chests, currency_error = _extract_currency_counts(
                    currency
                )
                current = (tickets, play_points, treasure_chests, currency_error)

                if last_report != current:
                    timestamp = _format_timestamp(payload.get("timestamp"))
                    pieces = [
                        f"[{timestamp}]",
                        f"tickets={tickets if tickets is not None else '?'}",
                        f"play_points={play_points if play_points is not None else '?'}",
                        f"treasure_chests={treasure_chests if treasure_chests is not None else '?'}",
                    ]
                    if currency_error:
                        pieces.append(f"(currency error: {currency_error})")
                    print(" ".join(pieces))
                    last_report = current

                    if once:
                        return 0
    except KeyboardInterrupt:
        print("\nStopped by user.")
        return 0

    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch MTGO Event Tickets / Play Points via the MTGOBridge watch feed."
    )
    parser.add_argument(
        "--interval-ms",
        type=int,
        default=1000,
        help="Polling interval (milliseconds) to request from the bridge watch loop.",
    )
    parser.add_argument(
        "--bridge-path",
        type=str,
        default=None,
        help="Explicit path to MTGOBridge.exe (falls back to auto-detection if omitted).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Exit after printing the first currency snapshot instead of streaming updates.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    return monitor_currency(
        bridge_path=args.bridge_path,
        interval_ms=max(100, args.interval_ms),
        once=args.once,
    )


if __name__ == "__main__":
    raise SystemExit(main())
