"""E2E tests: mouse-wheel scroll responsiveness in the grid and pile views.

Reproduces the reported input lag where the rendered card view trails behind
rapid wheel input. The harness fires bursts of whole wheel notches (x up then
x down, x = 1..10) through the real ``_on_wheel`` → ``Scroll`` → ``_on_paint``
path and reads back a per-event perf trace (see
``automation/server/scroll_perf.py``). For each burst it computes, for every
notch that actually moved the scroll origin, how long until a paint rendered
the view at-or-past that origin — i.e. how far the picture lagged the input —
and asserts the worst case stays under ``MAX_LAG_MS``.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from automation.client import AutomationClient

# A paint must catch up to a wheel notch within this budget, otherwise the
# scroll feels laggy. 100 ms is the threshold from the bug report.
MAX_LAG_MS = 100.0

# Spacing between injected notches — fast enough to model a rapid flick while
# still letting the natural paint pipeline interleave.
INTERVAL_MS = 4.0

# A deck big enough that both views have ample vertical travel for a 10-notch
# (600 px) burst without saturating at either end. Many distinct mana values
# keep the pile view's tallest pile and the grid's row count both large.
_BIG_DECK_LINES = [
    "4 Lightning Bolt",
    "4 Monastery Swiftspear",
    "4 Goblin Guide",
    "4 Eidolon of the Great Revel",
    "4 Lava Spike",
    "4 Rift Bolt",
    "4 Skullcrack",
    "4 Searing Blaze",
    "4 Light Up the Stage",
    "4 Boros Charm",
    "4 Lightning Helix",
    "4 Goblin Rabblemaster",
    "4 Hazoret the Fervent",
    "4 Glorybringer",
    "4 Inferno Titan",
    "4 Banefire",
    "4 Chandra, Torch of Defiance",
    "4 Bonecrusher Giant",
    "4 Mountain",
    "4 Sacred Foundry",
]
BIG_DECK_TEXT = "\n".join(_BIG_DECK_LINES) + "\n"


def _load_big_deck(client: AutomationClient) -> None:
    result = client.load_deck_text(BIG_DECK_TEXT)
    assert result.get("loaded"), f"load_deck_text failed: {result}"
    assert result["mainboard_count"] > 0, "Mainboard should have cards after loading"


def _worst_lag_ms(events: list[dict], direction: str) -> tuple[float, int]:
    """Return (worst input→frame lag in ms, number of moving notches measured).

    For each input that actually shifted the scroll origin (in ``direction``),
    find the first paint at-or-after it that rendered the view at-or-past that
    origin, and measure the gap. Inputs that didn't move the origin (e.g. the
    view saturated at an end) carry no new picture to wait for and are skipped.
    """
    inputs = [e for e in events if e["kind"] == "input"]
    paints = [e for e in events if e["kind"] == "paint"]

    worst = 0.0
    measured = 0
    last_y: int | None = None
    for inp in inputs:
        y = inp["y"]
        if last_y is not None and y == last_y:
            continue  # origin didn't move — nothing new to render
        moved_down = last_y is None or y > last_y
        last_y = y

        # First paint at-or-after this input that reached this scroll origin.
        reached = None
        for p in paints:
            if p["t_ms"] < inp["t_ms"]:
                continue
            caught_up = p["y"] >= y if (direction == "down" or moved_down) else p["y"] <= y
            if caught_up:
                reached = p
                break
        if reached is None:
            # No paint ever caught up — treat as a hard, maximal lag.
            return float("inf"), measured + 1
        worst = max(worst, reached["t_ms"] - inp["t_ms"])
        measured += 1
    return worst, measured


def _run_burst(
    client: AutomationClient, *, view: str, count: int, direction: str
) -> tuple[float, int]:
    """Fire one burst and return (worst lag ms, moving notches measured)."""
    started = client.wheel_scroll_start(
        zone="main", view=view, count=count, direction=direction, interval_ms=INTERVAL_MS
    )
    assert started.get("started"), f"wheel_scroll_start failed: {started}"
    # Wait for the burst to finish firing plus a generous settle for paints.
    time.sleep(count * INTERVAL_MS / 1000.0 + 0.4)
    events = client.get_scroll_perf(zone="main", view=view).get("events", [])
    # No paints at all means the window never composited (e.g. left minimized by
    # a prior screenshot) — that's an environment problem, not measured lag.
    if any(e["kind"] == "input" for e in events) and not any(e["kind"] == "paint" for e in events):
        raise AssertionError(
            f"{view} {direction} x{count}: scroll moved but no paint fired — the app "
            "window is not being composited (minimized/hidden?), so latency is "
            "unmeasurable. Ensure the app window is restored and visible."
        )
    return _worst_lag_ms(events, direction)


def _assert_view_keeps_up(client: AutomationClient, view: str) -> None:
    _load_big_deck(client)
    # Let the deck populate and the view lay out before measuring.
    time.sleep(0.5)
    # Warm up: switch to the view and let its first paint (which builds the
    # cached full-content image — a one-time render-on-open cost, not scroll
    # lag) settle, so it isn't charged to the first measured burst.
    client.wheel_scroll_start(
        zone="main", view=view, count=2, direction="down", interval_ms=INTERVAL_MS
    )
    time.sleep(0.6)

    worst_overall = 0.0
    total_measured = 0
    offenders: list[str] = []
    for count in range(1, 11):
        for direction in ("down", "up"):
            lag, measured = _run_burst(client, view=view, count=count, direction=direction)
            total_measured += measured
            worst_overall = max(worst_overall, lag if lag != float("inf") else 1e9)
            if lag > MAX_LAG_MS:
                offenders.append(
                    f"{view} {direction} x{count}: {lag:.1f}ms over {measured} notch(es)"
                )

    assert total_measured > 0, (
        f"{view} view never moved under wheel input — deck not scrollable, "
        "so the test measured nothing."
    )
    assert not offenders, (
        f"{view} view lagged wheel input by more than {MAX_LAG_MS:.0f}ms:\n  "
        + "\n  ".join(offenders)
        + f"\n(worst overall: {worst_overall:.1f}ms across {total_measured} notches)"
    )


def test_grid_view_wheel_latency(client: AutomationClient) -> None:
    """The grid view must render wheel scrolls within MAX_LAG_MS."""
    _assert_view_keeps_up(client, "grid")


def test_pile_view_wheel_latency(client: AutomationClient) -> None:
    """The pile view must render wheel scrolls within MAX_LAG_MS."""
    _assert_view_keeps_up(client, "pile")


# ---------------------------------------------------------------------------
# Test group registry
# ---------------------------------------------------------------------------

ALL_TESTS: list[tuple[str, str, Callable[[AutomationClient], None]]] = [
    ("wheel", "Grid view wheel-scroll latency under 100ms", test_grid_view_wheel_latency),
    ("wheel", "Pile view wheel-scroll latency under 100ms", test_pile_view_wheel_latency),
]
