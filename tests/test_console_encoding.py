"""The console must be able to carry every string the app can print.

Review finding §5.6 (issue #962): the automation CLI raised
``UnicodeEncodeError`` on the settings button's ``⚙`` unless Python was started
with ``-X utf8``. Phase 4 deleted that glyph and the *symptom* went away, but the
cause did not: a redirected stdout on Windows carries the **locale** encoding
(``cp1252`` here), and the app still ships several characters cp1252 has no code
point for. The pt-BR catalogue survives only because every accented character it
uses happens to be in Latin-1 -- one ``≥`` in a widget dump is enough to crash a
harness run.

These tests drive a real child process, because the defect only exists when
stdout is a pipe: in-process, pytest's capture object is a ``StringIO`` and
encodes anything.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from utils.console import force_utf8_console

#: Characters the app puts on screen that cp1252 cannot encode, each with the
#: control it belongs to. Anything printing a widget dump can hit these.
NON_CP1252_UI_CHARS = {
    "≥": "deck-research placement operator (>=)",
    "≤": "deck-research placement operator (<=)",
    "≈": "builder oracle-text match mode (approx)",
    "⋯": "pile-sort control",
}

_CHILD = "; ".join(
    [
        "import sys",
        "sys.path.insert(0, {root!r})",
        "{setup}sys.stdout.write({text!r})",
        "sys.stdout.flush()",
    ]
)


def _run(text: str, *, fixed: bool) -> subprocess.CompletedProcess[bytes]:
    """Print *text* from a child whose stdout is a cp1252 pipe."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    setup = "from utils.console import force_utf8_console; force_utf8_console(); " if fixed else ""
    env = dict(os.environ)
    # Pin the child's stream encoding so the test is deterministic on machines
    # (and CI images) whose locale is not cp1252, and clear UTF-8 mode so it
    # cannot quietly win instead.
    env["PYTHONIOENCODING"] = "cp1252"
    env["PYTHONUTF8"] = "0"
    return subprocess.run(
        [sys.executable, "-c", _CHILD.format(root=root, setup=setup, text=text)],
        capture_output=True,
        env=env,
        check=False,
    )


@pytest.mark.parametrize("char,control", sorted(NON_CP1252_UI_CHARS.items()))
def test_cp1252_console_raises_without_the_fix(char: str, control: str) -> None:
    """Pin the defect: this is what §5.6 was, and it is still latent."""
    result = _run(char, fixed=False)
    assert result.returncode != 0, f"expected {control} to be unencodable in cp1252"
    assert b"UnicodeEncodeError" in result.stderr


@pytest.mark.parametrize("char,control", sorted(NON_CP1252_UI_CHARS.items()))
def test_force_utf8_console_lets_the_character_through(char: str, control: str) -> None:
    result = _run(char, fixed=True)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert result.stdout.decode("utf-8") == char, control


def test_pt_br_catalogue_round_trips_through_a_utf8_pipe() -> None:
    """Every pt-BR string, not just the ones that happen to be Latin-1."""
    from utils.i18n import MESSAGES

    # Newlines are excluded, not because they are safe but because Windows text
    # mode rewrites "\n" to "\r\n" on the way out and this test is about the
    # codec, not about line endings.
    sample = "".join(
        sorted({c for text in MESSAGES["pt-BR"].values() for c in text if not c.isspace()})
    )
    assert any(ord(c) > 0x7F for c in sample), "sample carries no non-ASCII text"
    result = _run(sample, fixed=True)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert result.stdout.decode("utf-8") == sample


def test_force_utf8_console_is_idempotent_and_tolerates_odd_streams() -> None:
    """Called from two entry points and from tests; must never raise."""
    import io

    force_utf8_console()
    force_utf8_console()

    real_out, real_err = sys.stdout, sys.stderr
    try:
        # A stream with no reconfigure() at all -- e.g. a frozen build's stub.
        sys.stdout = object()  # type: ignore[assignment]
        sys.stderr = io.StringIO()
        force_utf8_console()
    finally:
        sys.stdout, sys.stderr = real_out, real_err


def test_both_entry_points_force_the_console() -> None:
    """The fix is only real where output is produced."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    for path in (root / "automation" / "cli.py", root / "utils" / "logging_config.py"):
        source = path.read_text(encoding="utf-8")
        assert "force_utf8_console()" in source, f"{path.name} no longer forces UTF-8 output"
