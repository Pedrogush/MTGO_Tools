"""Make this process's console streams able to carry the text the app produces.

The problem, measured
---------------------
On Windows, ``sys.stdout``/``sys.stderr`` are UTF-8 only while they are attached
to a real console. The moment either is **redirected** -- a pipe, a file, a WSL
shell capturing output, a CI log -- CPython falls back to the *locale* encoding,
which on a Brazilian or Western-European Windows is ``cp1252``::

    $ .venv/Scripts/python.exe -c "import sys; print(sys.stdout.encoding)" | cat
    cp1252

Writing a character cp1252 has no code point for then raises
``UnicodeEncodeError`` *from the write*, which is a crash in whatever was
printing rather than a mangled character.

Review finding §5.6 recorded one instance of this: ``automation/cli.py``'s
``list-widgets`` died on the settings button's ``⚙``. That glyph was deleted in
phase 4 and the symptom went with it, but nothing about the encoding changed --
the app still ships several strings outside cp1252 and any of them reaching a
redirected stream is the same crash:

* ``≥`` / ``≤`` (U+2265 / U+2264) -- the deck-research placement operators
* ``≈`` (U+2248) -- the builder's oracle-text match mode
* ``⋯`` (U+22EF) -- the pile-sort control
* ``—`` and every accented pt-BR label are cp1252-encodable, so the pt-BR UI
  survives this **by luck**, not by design. One `≥` in a widget dump is enough.

The fix
-------
Re-wrap the streams as UTF-8. ``errors="backslashreplace"`` is belt and braces
for a stream that refuses the reconfigure and stays on a narrow codec: an
unrepresentable character then prints as ``\\u22ef`` instead of raising, because
a diagnostic tool losing a glyph is a much better outcome than a diagnostic tool
raising inside ``print``.

This has to happen in the *process that writes*, so both entry points call it:
:func:`utils.logging_config.configure_logging` (the app, whose loguru console
sink is a stream sink) and ``automation.cli.main`` (the harness). It is a no-op
on a stream that is already UTF-8, and on platforms where the locale encoding
already is.
"""

from __future__ import annotations

import sys

__all__ = ["force_utf8_console"]


def force_utf8_console() -> None:
    """Reconfigure ``sys.stdout``/``sys.stderr`` to UTF-8, if they allow it.

    Safe to call more than once, and safe to call when the streams have been
    replaced by something without ``reconfigure`` (pytest's capture objects,
    a frozen windowed build's ``None`` streams, an ``io.StringIO`` in a test).
    Those cases are skipped rather than forced, because the alternative --
    wrapping an arbitrary stream in a new ``TextIOWrapper`` -- changes the
    buffering of a stream this module does not own.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError, AttributeError):
            # A detached or already-closed stream, or one whose underlying
            # buffer refuses re-encoding. Nothing to do but leave it alone.
            continue
