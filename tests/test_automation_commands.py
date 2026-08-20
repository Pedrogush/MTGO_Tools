"""Every automation command the client can send must exist on the server.

Why this file exists
====================
Review finding §5.3 (issue #962): ``AutomationClient.type_into_oracle`` sent a
``type_into_oracle`` command and ``AutomationServer._register_default_handlers``
had never registered a handler for it. The CLI advertised the subcommand in
``--help``, the client had a docstring describing what it did, and the running
app answered ``Unknown command: type_into_oracle``. It shipped that way and
stayed that way, because nothing anywhere connects the two halves of the wire
protocol -- the command name is a bare string on both sides.

The command was removed in phase 9 rather than implemented (see
:mod:`automation.client` for why). This guard is the part that outlives it: the
protocol has **three** independent lists of command names -- the client's
``_send_command`` literals, the server's handler dict, and the CLI's subparsers
plus its dispatch table -- and a name that appears in one and not the others is
dead code that presents as a working feature.

Everything here is static (``ast``), so it needs neither a running app nor a
display: the failure mode being guarded is a missing name, which is visible in
the source.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / "automation" / "client.py"
SERVER = ROOT / "automation" / "server" / "__init__.py"
CLI = ROOT / "automation" / "cli.py"


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _literal(node: ast.expr) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def client_commands() -> set[str]:
    """Command names the client sends, from ``self._send_command("name", ...)``."""
    found: set[str] = set()
    for node in ast.walk(_parse(CLIENT)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "_send_command"):
            continue
        assert node.args, "_send_command called with no command name"
        name = _literal(node.args[0])
        assert name is not None, (
            "_send_command's first argument is not a string literal; this guard "
            "reads it statically and cannot follow a computed name"
        )
        found.add(name)
    return found


def server_commands() -> dict[str, str]:
    """``{command name: handler attribute}`` from ``_register_default_handlers``."""
    for node in ast.walk(_parse(SERVER)):
        if isinstance(node, ast.FunctionDef) and node.name == "_register_default_handlers":
            for assign in ast.walk(node):
                if isinstance(assign, ast.Dict) and assign.keys:
                    out: dict[str, str] = {}
                    for key, value in zip(assign.keys, assign.values):
                        name = _literal(key) if key is not None else None
                        assert name is not None, "non-literal key in the handler dict"
                        kind = type(value).__name__
                        assert isinstance(value, ast.Attribute), f"{name}: {kind} handler"
                        out[name] = value.attr
                    return out
    raise AssertionError("_register_default_handlers or its handler dict not found")


def cli_subcommands() -> set[str]:
    """Subcommand names registered with ``subparsers.add_parser("name", ...)``."""
    found: set[str] = set()
    for node in ast.walk(_parse(CLI)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_parser"):
            continue
        name = _literal(node.args[0]) if node.args else None
        assert name is not None, "add_parser called without a literal subcommand name"
        found.add(name)
    return found


def cli_dispatch() -> set[str]:
    """Subcommand names in ``main()``'s ``handlers`` dict."""
    for node in ast.walk(_parse(CLI)):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            for assign in ast.walk(node):
                if (
                    isinstance(assign, ast.Assign)
                    and isinstance(assign.targets[0], ast.Name)
                    and assign.targets[0].id == "handlers"
                    and isinstance(assign.value, ast.Dict)
                ):
                    return {
                        name
                        for key in assign.value.keys
                        if key is not None and (name := _literal(key)) is not None
                    }
    raise AssertionError("main()'s handlers dict not found")


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def test_every_client_command_has_a_server_handler() -> None:
    """The §5.3 regression, in the direction it actually happened."""
    missing = sorted(client_commands() - set(server_commands()))
    assert not missing, (
        "AutomationClient sends commands the server never registered, so the app "
        f"answers 'Unknown command': {missing}. Register a handler in "
        "AutomationServer._register_default_handlers, or delete the client method."
    )


def test_every_registered_handler_exists_on_the_server() -> None:
    """A registration naming a method nobody wrote fails at call time, not import time."""
    from automation.server import AutomationServer

    missing = sorted(
        f"{command} -> {attr}"
        for command, attr in server_commands().items()
        if not hasattr(AutomationServer, attr)
    )
    assert not missing, f"handler dict references methods that do not exist: {missing}"


def test_cli_subcommands_and_dispatch_table_agree() -> None:
    """A subcommand in ``--help`` with no dispatch entry prints 'Unknown command'."""
    parsers, dispatch = cli_subcommands(), cli_dispatch()
    # open-app is handled before the dispatch table (it has no server to talk to).
    dispatch = dispatch | {"open-app"}
    undispatchable = sorted(parsers - dispatch)
    assert not undispatchable, f"CLI advertises subcommands it cannot run: {undispatchable}"
    unreachable = sorted(dispatch - parsers)
    assert not unreachable, f"CLI dispatches subcommands argparse rejects: {unreachable}"


@pytest.mark.parametrize("command", sorted(client_commands()))
def test_client_command_is_live(command: str) -> None:
    """Per-command view of the same invariant, so a failure names the command."""
    assert command in server_commands(), f"no server handler registered for {command!r}"


def test_the_dead_command_stays_dead() -> None:
    """``type_into_oracle`` specifically -- it was advertised in three places.

    Faithfully typing into the oracle field needs real Win32 input, not wx
    events: the ``ManaSymbolRichCtrl`` inserts plain characters from the native
    ``WM_CHAR`` that follows a keystroke, which a synthesised ``wx.KeyEvent``
    does not produce. If someone brings the command back, it has to come back
    with a handler -- which the first test in this module already enforces --
    and this one is the reminder that a wx-level implementation would look like
    it worked and set no text.
    """
    sources = "\n".join(p.read_text(encoding="utf-8") for p in (CLIENT, CLI))
    assert "type_into_oracle" not in sources
    assert "type-into-oracle" not in sources
