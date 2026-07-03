#!/usr/bin/env python3
"""Fetch the mana symbol assets when missing.

Assets are cloned from ``Pedrogush/mana`` — our fork of ``andrewgioia/mana``.
Pointing at the fork pins this dependency: upstream changes only reach us when
we deliberately sync the fork, so a maintainer edit can never alter what the
app or a build fetches out from under us.

This module is importable: :func:`ensure_mana_assets` detects the local state
and only clones when the assets are actually missing, so the application can
self-heal on startup instead of relying on a manual run.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess  # nosec B404 - needed to invoke git clone of a trusted repo
import sys
from pathlib import Path

# Our fork of andrewgioia/mana. Using the fork (rather than upstream) pins the
# asset source so maintainer changes never affect us until we sync the fork.
DEFAULT_MANA_REPO = "https://github.com/Pedrogush/mana.git"
# Retained for reference/provenance; the fork above is what we actually clone.
UPSTREAM_MANA_REPO = "https://github.com/andrewgioia/mana.git"

# Files/directories that must exist for the mana assets to be considered
# usable. A bare ``assets/mana`` directory (e.g. a half-finished clone) is not
# enough — these are the paths the mana icon factory actually reads.
_REQUIRED_ASSET_PATHS: tuple[Path, ...] = (
    Path("fonts") / "mana.ttf",
    Path("css") / "mana.min.css",
    Path("svg"),
)


def _project_root() -> Path:
    # In a PyInstaller bundle the assets live under ``sys._MEIPASS`` (mirrors
    # ManaIconFactory._assets_root); from source they sit next to the repo root.
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[1]


def mana_assets_dir() -> Path:
    """Return the directory where the mana assets live (``<repo>/assets/mana``)."""
    return _project_root() / "assets" / "mana"


def mana_assets_present(target_dir: Path | None = None) -> bool:
    """Return ``True`` when the required mana asset files are present locally."""
    target = target_dir or mana_assets_dir()
    if not target.is_dir():
        return False
    return all((target / rel).exists() for rel in _REQUIRED_ASSET_PATHS)


def _run_git_clone(url: str, target: Path, depth: int = 1) -> None:
    cmd = [
        "git",
        "clone",
        url,
        str(target),
        "--depth",
        str(depth),
    ]
    # URL is controlled via CLI/default; only a git clone without shell
    subprocess.check_call(cmd)  # nosec B603


def ensure_mana_assets(
    repo: str = DEFAULT_MANA_REPO,
    *,
    force: bool = False,
    quiet: bool = False,
) -> bool:
    """Ensure the mana assets exist locally, cloning ``repo`` if they are missing.

    Returns ``True`` when the assets are present afterwards. Cloning failures
    are surfaced to the caller (return value / raised errors are handled by
    :func:`main`); the application treats a missing asset set as non-fatal and
    falls back to placeholder glyphs.
    """

    def _log(message: str) -> None:
        if not quiet:
            print(message)

    target_dir = mana_assets_dir()

    if mana_assets_present(target_dir) and not force:
        _log(f"Mana assets already present at {target_dir}")
        return True

    # Remove any stale/partial directory so ``git clone`` has a clean target.
    if target_dir.exists():
        reason = "force requested" if force else "existing assets incomplete"
        _log(f"Removing directory {target_dir} ({reason})")
        shutil.rmtree(target_dir)

    target_dir.parent.mkdir(parents=True, exist_ok=True)

    try:
        _log(f"Cloning {repo} into {target_dir}…")
        _run_git_clone(repo, target_dir)
    except (subprocess.CalledProcessError, OSError) as exc:
        print(f"Failed to clone mana assets: {exc}", file=sys.stderr)
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        return False

    if not mana_assets_present(target_dir):
        print(
            f"Clone of {repo} did not produce the expected mana asset files.",
            file=sys.stderr,
        )
        return False

    _log("Mana assets downloaded successfully.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch assets even if the assets/mana directory already exists.",
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_MANA_REPO,
        help="Git repository to clone (default: %(default)s)",
    )
    args = parser.parse_args()

    ok = ensure_mana_assets(args.repo, force=args.force)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
