"""Open a decoy window whose title makes the Opponent Deck Spy see a match.

The tracker detects opponents by scanning **every** Windows window title for the
substring ``vs.`` and taking whatever follows it
(:func:`utils.find_opponent_names.find_opponent_names`).  Nothing about that
path is MTGO-specific, so any window with the right title drives the real
feature end to end: the poll fires, MTGGoldfish is queried for the name, and the
radar and sideboard guide populate for whatever archetype comes back.

That makes this the way to look at the tracker without MTGO running -- for
reviewing a layout change, reproducing a report, or capturing a screenshot.

Usage (from the repo root, with the Windows venv)::

    .venv\\Scripts\\python.exe scripts/mock_opponent_window.py
    .venv\\Scripts\\python.exe scripts/mock_opponent_window.py connormc02
    .venv\\Scripts\\python.exe scripts/mock_opponent_window.py --title-only "Foo vs. bar"

Leave it running, open the tracker (Tools > Opponent Deck Spy), and wait for one
poll interval.  Close the window to stop pretending.

The name has to be a player MTGGoldfish actually knows, or the lookup returns
"Unknown" for every format and the panels stay empty -- which is exactly the
state that hides a layout bug.  The defaults below were checked against
``get_latest_deck`` when this script was written; MTGGoldfish only keeps recent
results, so if a default has gone stale, pass a name off any current decklist
page instead.

Run the app **without** ``--automation`` for this to work.  Detection is broken
in an automation-enabled process: importing the automation server sets
``argtypes`` on the process-wide ``ctypes.windll.user32``, which makes
``pygetwindow``'s own ``GetWindowRect`` call raise and
:func:`find_opponent_names` return nothing.  A one-line import flips it, so this
is a harness artefact and not something a user's install can hit.
"""

from __future__ import annotations

import argparse
import sys

import wx

#: Players that returned real archetypes when this script was written.  The
#: first is the interesting one for layout work: four formats, so the tracker
#: headline grows to five lines, which is the case that used to paint over the
#: panels below it (#1011).
KNOWN_PLAYERS = ("connormc02", "ziofrancone")

#: The tracker splits on this and keeps the tail, so the name has to be last.
TITLE_TEMPLATE = "Mock Match: You vs. {player}"

_EXPLANATION = (
    "This window exists only for its title.\n\n"
    "The Opponent Deck Spy scans window titles for 'vs.' and looks up\n"
    "whatever follows it on MTGGoldfish. Keep this open, open the tracker,\n"
    "and give it one poll interval (2s) to notice.\n\n"
    "Close this window to stop pretending."
)


def build_title(player: str) -> str:
    """Return the window title that makes the tracker detect ``player``."""
    return TITLE_TEMPLATE.format(player=player)


class MockMatchFrame(wx.Frame):
    """A small window that carries the decoy title and explains itself."""

    def __init__(self, title: str, detected: str) -> None:
        super().__init__(None, title=title, size=(460, 260))
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        heading = wx.StaticText(panel, label=f"Pretending to play against: {detected}")
        heading.SetFont(heading.GetFont().Bold())
        sizer.Add(heading, 0, wx.ALL, 12)

        sizer.Add(wx.StaticText(panel, label=f"Window title:\n{title}"), 0, wx.LEFT | wx.RIGHT, 12)
        sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.ALL, 12)
        sizer.Add(wx.StaticText(panel, label=_EXPLANATION), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.Centre()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open a decoy window so the Opponent Deck Spy detects a match.",
        epilog=f"Players known to resolve when this was written: {', '.join(KNOWN_PLAYERS)}",
    )
    parser.add_argument(
        "player",
        nargs="?",
        default=KNOWN_PLAYERS[0],
        help=f"MTGGoldfish player name to be detected as (default: {KNOWN_PLAYERS[0]})",
    )
    parser.add_argument(
        "--title-only",
        metavar="TITLE",
        help=(
            "Use this exact window title instead of building one. For testing the "
            "detection rule itself -- the tracker keeps whatever follows 'vs.'."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.title_only:
        title = args.title_only
        if "vs." not in title:
            print(
                f"Title {title!r} has no 'vs.' in it, so the tracker will never "
                "match it. Detection splits on that exact substring.",
                file=sys.stderr,
            )
            return 2
        detected = title.split("vs.")[-1].strip()
        if not detected:
            print(
                f"Title {title!r} ends at 'vs.', so the detected name would be "
                "empty and the tracker skips it. Put the player name last.",
                file=sys.stderr,
            )
            return 2
    else:
        title = build_title(args.player)
        detected = args.player

    print(f"Window title : {title}")
    print(f"Detected as  : {detected}")
    print("Open the tracker and wait ~2s for the next poll. Close the window to stop.")

    app = wx.App(False)
    MockMatchFrame(title, detected).Show()
    app.MainLoop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
