r"""Write mock MTGO game logs so the Match History window has something to show.

Match History is driven entirely by ``Match_GameLog_*.dat`` files that MTGO
writes into its ClickOnce AppData tree
(:func:`services.gamelog_service.find_all_gamelog_dirs`). A developer who has
never played on this machine -- or who has game-log saving switched off -- opens
the window to "No match data available." and cannot review a layout change, a
metric, or a filter. This script fills that gap by writing the same files MTGO
would, in the same text shape the parser reads.

**The decklists are real.** Every card name comes from an actual MTGGoldfish
decklist pulled through the app's own metagame repository and deck-text cache --
the same path the deck browser uses. That is not politeness about data hygiene,
it is the point: the Pauper half of format detection asks whether *every* card
in the match has a printing at common
(:func:`services.gamelog_service.formats.deck_is_pauper`), so a made-up card
name is skipped as unrecognised and an invented "Pauper" list built from
plausible-sounding commons proves nothing. Real lists exercise the rule the way
a real match does.

Six formats are covered -- Modern, Legacy, Pauper, Standard, Pioneer, Vintage --
because the point of the mock is to make the per-format and per-archetype
filters do something. The decks are paired off so both filters have several
distinct values to offer.

Usage (from the repo root, with the Windows venv)::

    .venv\Scripts\python.exe scripts/mock_match_history.py
    .venv\Scripts\python.exe scripts/mock_match_history.py --formats Modern Pauper
    .venv\Scripts\python.exe scripts/mock_match_history.py --matches-per-format 6
    .venv\Scripts\python.exe scripts/mock_match_history.py --keep
    .venv\Scripts\python.exe scripts/mock_match_history.py --clean

By default the logs are written, the script waits, and it deletes them again
when you press Enter or Ctrl-C. That default is deliberate: while these files
are on disk they are indistinguishable from real ones, and
``tests/test_gamelog_parser.py::TestGamelogParserVsScreenshots`` un-skips and
runs against them -- cross-referencing mock matches with a ground-truth fixture
recorded from someone's real MTGO history, which fails for reasons that have
nothing to do with the code under test. Run the suite with the mocks gone.
``--keep`` opts out; ``--clean`` removes whatever an earlier ``--keep`` left.

The generated files are named ``Match_GameLog_MOCK-*.dat`` so cleanup can find
its own output and never touches a real log.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from loguru import logger  # noqa: E402

from repositories.metagame_repository import get_metagame_repository  # noqa: E402
from repositories.scrapers.mtggoldfish import fetch_deck_text  # noqa: E402
from services.gamelog_service import find_all_gamelog_dirs  # noqa: E402

#: Only the files this script wrote are ever deleted by ``--clean``.
MOCK_PREFIX = "Match_GameLog_MOCK-"

#: The formats the detector can actually name, which is what makes them worth
#: mocking. Pauper is first because it is the one the rarity rule exists for.
DEFAULT_FORMATS = ("Pauper", "Modern", "Legacy", "Standard", "Pioneer", "Vintage")

#: Stand-ins for the two seats. The first appears in every match, which is what
#: ``infer_username_from_matches`` needs to decide who "we" are (it wants one
#: player in at least 80% of matches).
LOCAL_PLAYER = "MockPilot"
OPPONENT_NAMES = (
    "Adept_Aardvark",
    "BasaltMonolith",
    "CabalCoffers",
    "DarkRitualist",
    "EmryEnjoyer",
    "FblthpLost",
    "GoblinLackey",
    "HighTideHero",
)


def _card_ref(name: str) -> str:
    """Render a card reference the way MTGO's game log does."""
    return f"@[{name}@:0,0:@]"


def parse_deck_cards(deck_text: str) -> list[str]:
    """Return the distinct maindeck card names of an MTGGoldfish deck text."""
    cards: list[str] = []
    seen: set[str] = set()
    for line in deck_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("sideboard"):
            break
        count, _, name = line.partition(" ")
        name = name.strip()
        if not count.isdigit() or not name or name in seen:
            continue
        seen.add(name)
        cards.append(name)
    return cards


def build_gamelog(
    *,
    timestamp: datetime,
    local_player: str,
    opponent: str,
    local_cards: list[str],
    opponent_cards: list[str],
    local_wins: int,
    opponent_wins: int,
    rng: random.Random,
) -> str:
    """Render one match as the ``@P``-delimited text the parser reads.

    Only the lines the parser looks for are emitted -- joins, play/draw choices,
    mulligans, ``plays``/``casts`` card references, game results and the closing
    match score. A real log carries binary framing around all of this that the
    parser skips, so the text shape is what matters.
    """
    lines = [timestamp.strftime("%a %b %d %H:%M:%S PST %Y")]
    lines.append(f"@P{local_player} joined the game")
    lines.append(f"@P{opponent} joined the game")

    results = [local_player] * local_wins + [opponent] * opponent_wins
    rng.shuffle(results)
    for winner in results:
        on_the_play = rng.choice((local_player, opponent))
        lines.append(f"@P{on_the_play} chooses to play first")
        for player in (local_player, opponent):
            kept = rng.choices(("seven", "six", "five"), weights=(78, 18, 4))[0]
            if kept != "seven":
                lines.append(f"@P{player} mulligans to {kept} cards")
        # Enough distinct cards that the format detector has real evidence:
        # a match where two spells were cast tells it almost nothing, which is
        # exactly the case the Pauper rule's minimum-card floor guards against.
        for player, pool in ((local_player, local_cards), (opponent, opponent_cards)):
            played = rng.sample(pool, min(len(pool), rng.randint(8, 14)))
            for card in played:
                verb = rng.choice(("plays", "casts"))
                lines.append(f"@P{player} {verb} {_card_ref(card)}")
        lines.append(f"@P{winner} wins the game")

    if local_wins > opponent_wins:
        lines.append(f"@P{local_player} wins the match {local_wins}-{opponent_wins}")
    else:
        lines.append(f"@P{opponent} wins the match {opponent_wins}-{local_wins}")
    return "\n".join(lines)


def load_format_decks(mtg_format: str, count: int) -> list[tuple[str, list[str]]]:
    """Return ``(archetype name, card names)`` for *count* real MTGGoldfish decks.

    Goes through the app's own repository so the archetype list and the deck
    texts come from (and land in) the caches the app already keeps -- a second
    run is offline.
    """
    repo = get_metagame_repository()
    archetypes = repo.get_archetypes_for_format(mtg_format)
    if not archetypes:
        logger.warning(f"No archetypes returned for {mtg_format}; skipping it")
        return []

    decks: list[tuple[str, list[str]]] = []
    for archetype in archetypes:
        if len(decks) >= count:
            break
        name = archetype.get("name") or "Unknown"
        try:
            entries = repo.get_decks_for_archetype(archetype)
        except Exception as exc:  # noqa: BLE001 - one dead archetype must not stop the run
            logger.debug(f"{mtg_format}/{name}: no decks ({exc})")
            continue
        for entry in entries[:3]:
            number = str(entry.get("number") or "")
            if not number:
                continue
            try:
                cards = parse_deck_cards(fetch_deck_text(number))
            except Exception as exc:  # noqa: BLE001 - unavailable decks are common
                logger.debug(f"{mtg_format}/{name}: deck {number} unavailable ({exc})")
                continue
            if len(cards) >= 12:
                decks.append((name, cards))
                logger.info(f"{mtg_format}: {name} (deck {number}, {len(cards)} distinct cards)")
                break
    return decks


def write_mock_logs(
    target_dir: Path,
    formats: list[str],
    matches_per_format: int,
    seed: int,
) -> list[Path]:
    """Write one mock game log per match and return the paths written."""
    rng = random.Random(seed)
    written: list[Path] = []
    # Newest last, so Match History's date column spans a readable range.
    when = datetime.now() - timedelta(days=len(formats) * matches_per_format)

    for mtg_format in formats:
        decks = load_format_decks(mtg_format, count=max(2, matches_per_format // 2))
        if len(decks) < 2:
            logger.warning(f"{mtg_format}: fewer than two usable decks, skipping")
            continue
        for index in range(matches_per_format):
            our_archetype, our_cards = decks[index % len(decks)]
            their_archetype, their_cards = decks[(index + 1) % len(decks)]
            local_wins, opponent_wins = rng.choice(((2, 0), (2, 1), (0, 2), (1, 2)))
            when += timedelta(hours=rng.randint(3, 20))
            body = build_gamelog(
                timestamp=when,
                local_player=LOCAL_PLAYER,
                opponent=rng.choice(OPPONENT_NAMES),
                local_cards=our_cards,
                opponent_cards=their_cards,
                local_wins=local_wins,
                opponent_wins=opponent_wins,
                rng=rng,
            )
            path = target_dir / f"{MOCK_PREFIX}{mtg_format.lower()}-{index}.dat"
            path.write_text(body, encoding="latin1")
            written.append(path)
            logger.debug(f"wrote {path.name}: {our_archetype} vs {their_archetype}")
    return written


def find_mock_logs(target_dir: Path) -> list[Path]:
    """Return the mock logs previously written into *target_dir*."""
    return sorted(target_dir.glob(f"{MOCK_PREFIX}*.dat"))


def remove_mock_logs(target_dir: Path) -> int:
    """Delete this script's own output and return how many files went."""
    removed = 0
    for path in find_mock_logs(target_dir):
        try:
            path.unlink()
            removed += 1
        except OSError as exc:  # noqa: PERF203 - report and keep going
            logger.warning(f"Could not remove {path}: {exc}")
    return removed


def resolve_target_dir(explicit: str | None) -> Path | None:
    """Return where the logs go: the requested dir, or MTGO's own log folder."""
    if explicit:
        path = Path(explicit)
        path.mkdir(parents=True, exist_ok=True)
        return path
    dirs = find_all_gamelog_dirs()
    if dirs:
        return Path(dirs[0])

    # Chicken-and-egg: production discovery only accepts a folder that *already*
    # contains a ``Match_GameLog_*.dat``, so on a machine that has never saved
    # one there is nothing for it to return and nothing for the app to find
    # afterwards either. Seeding therefore has to locate the same ClickOnce
    # folder by shape rather than by content -- the identical glob, minus the
    # "has logs in it" test -- so that the very first mock written makes the
    # folder discoverable.
    seeded = _empty_clickonce_appfiles_dirs()
    if seeded:
        logger.info(f"No game logs yet; seeding MTGO's own folder at {seeded[0]}")
        return seeded[0]

    logger.error(
        "No MTGO GameLog directory found and no MTGO ClickOnce install to seed. "
        "Pass --out-dir with any folder if you only want the files."
    )
    return None


def _empty_clickonce_appfiles_dirs() -> list[Path]:
    """Return MTGO's per-install AppFiles folders, log-bearing or not."""
    import os

    bases: list[Path] = []
    wsl_users = Path("/mnt/c/Users")
    if wsl_users.is_dir():
        bases.extend(
            user / "AppData" / "Local" / "Apps" / "2.0" / "Data" for user in wsl_users.iterdir()
        )
    username = os.environ.get("USERNAME", "")
    if username:
        bases.append(Path(rf"C:\Users\{username}\AppData\Local\Apps\2.0\Data"))

    found: list[Path] = []
    for base in bases:
        if not base.is_dir():
            continue
        found.extend(
            candidate for candidate in base.glob("*/*/mtgo*/Data/AppFiles/*/") if candidate.is_dir()
        )
    # Newest install first: MTGO leaves the previous version's tree behind after
    # an update, and only the current one is the folder it will write to.
    found.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return found


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--formats",
        nargs="+",
        default=list(DEFAULT_FORMATS),
        help=f"Formats to mock (default: {' '.join(DEFAULT_FORMATS)})",
    )
    parser.add_argument(
        "--matches-per-format",
        type=int,
        default=4,
        help="How many matches to invent per format (default: 4)",
    )
    parser.add_argument("--out-dir", default=None, help="Write here instead of MTGO's log folder")
    parser.add_argument("--seed", type=int, default=20260822, help="Seed for reproducible mocks")
    parser.add_argument(
        "--keep", action="store_true", help="Write and exit, leaving the logs in place"
    )
    parser.add_argument(
        "--clean", action="store_true", help="Delete previously written mock logs and exit"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target_dir = resolve_target_dir(args.out_dir)
    if target_dir is None:
        return 1

    if args.clean:
        logger.info(f"Removed {remove_mock_logs(target_dir)} mock log(s) from {target_dir}")
        return 0

    written = write_mock_logs(target_dir, args.formats, args.matches_per_format, args.seed)
    if not written:
        logger.error("No mock logs were written -- MTGGoldfish returned no usable decks")
        return 1
    logger.info(f"Wrote {len(written)} mock game log(s) to {target_dir}")

    if args.keep:
        logger.info(
            "Left in place. Remember to run with --clean before the test suite: "
            "TestGamelogParserVsScreenshots un-skips while they exist."
        )
        return 0

    print("\nOpen Match History (Tools > Match History) and hit Refresh.")
    print("Press Enter here when you are done and the mock logs will be removed.")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        print()
    logger.info(f"Removed {remove_mock_logs(target_dir)} mock log(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
