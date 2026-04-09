#!/usr/bin/env bash
set -euo pipefail

# Launch MTGO Tools as a Windows wxPython process from this WSL repo checkout.
#
# Why this uses /init:
# - In this shell, plain `cmd.exe /c ...` can fail with:
#   `/mnt/c/WINDOWS/system32/cmd.exe: cannot execute binary file: Exec format error`
# - `/init` is the working WSL interop bridge for invoking Windows executables.
#
# Why this uses "$(command -v cmd.exe)" instead of bare "cmd.exe":
# - Bash can resolve cmd.exe to /mnt/c/WINDOWS/system32/cmd.exe.
# - `/init cmd.exe ...` does not perform that PATH lookup and fails with:
#   `cmd.exe: Invalid argument`
#
# The app must use the Windows virtualenv, not WSL Python, because wxPython is
# installed in env\Scripts\python.exe and the desktop UI must run on Windows.
#
# Usage:
#   automation/run_app_from_wsl.sh
#   AUTOMATION_PORT=19848 automation/run_app_from_wsl.sh
#
# CLI commands to run from another WSL shell while this stays attached:
#   /init "$(command -v cmd.exe)" /c "env\\Scripts\\python.exe -m automation.cli ping"
#   /init "$(command -v cmd.exe)" /c "env\\Scripts\\python.exe -m automation.cli --json window-info"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
CMD_EXE="$(command -v cmd.exe || true)"
AUTOMATION_PORT="${AUTOMATION_PORT:-19847}"

if [[ -z "$CMD_EXE" ]]; then
    echo "cmd.exe was not found on PATH. This script must run from WSL with Windows interop available." >&2
    exit 1
fi

if [[ ! -x /init ]]; then
    echo "/init is not executable. This script requires WSL's /init interop launcher." >&2
    exit 1
fi

if [[ ! "$AUTOMATION_PORT" =~ ^[0-9]+$ ]]; then
    echo "AUTOMATION_PORT must be numeric, got: $AUTOMATION_PORT" >&2
    exit 1
fi

cd "$REPO_ROOT"

exec /init "$CMD_EXE" /c "env\\Scripts\\python.exe main.py --automation --automation-port $AUTOMATION_PORT"
